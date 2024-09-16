#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

import logging
from json import dumps as dump_json
from os import environ as env
from os.path import join, expanduser
from time import time
import tellsticknet.const as const
from platform import node as hostname
import string
from amqtt.client import MQTTClient, ConnectException, ClientException
import asyncio


# FIXME: A command can correspond to multiple entities (e.g. switches/lights)

_LOGGER = logging.getLogger(__name__)


DISCOVERY_PREFIX = "homeassistant"
STATE_PREFIX = "tellsticknet"

STATE_ONLINE = "online"
STATE_OFFLINE = "offline"

STATES = {
    const.TURNON: "turnon",
    const.TURNOFF: "turnoff",
    const.BELL: "bell",
    const.TOGGLE: "toggle",
    const.DIM: "dim",
    const.UP: "up",
    const.DOWN: "down",
    const.STOP: "stop",
    const.RGBW: "rgbw",
}

STATE_ON = STATES[const.TURNON]
STATE_OFF = STATES[const.TURNOFF]

SENSOR_ICONS = {
    const.TEMPERATURE: "mdi:thermometer",
    const.HUMIDITY: "mdi:water",
    const.RAINRATE: "mdi:water",
    const.RAINTOTAL: "mdi:water",
    const.DEW_POINT: "mdi:thermometer",
}

SENSOR_NAMES = {
    const.TEMPERATURE: "Temperature",
    const.HUMIDITY: "Humidity",
    const.RAINRATE: "Rain rate",
    const.RAINTOTAL: "Rain total",
    const.WINDDIRECTION: "Wind direction",
    const.WINDAVERAGE: "Wind average",
    const.WINDGUST: "Wind gust",
    const.UV: "UV",
    const.POWER: "Power",
    const.LUMINANCE: "Luminance",
    const.DEW_POINT: "Dew Point",
    const.BAROMETRIC_PRESSURE: "Barometric Pressure",
}

SENSOR_UNITS = {
    const.TEMPERATURE: "°C",
    const.HUMIDITY: "%",
    const.RAINRATE: "mm/h",
    const.RAINTOTAL: "mm",
    const.WINDDIRECTION: "",
    const.WINDAVERAGE: "m/s",
    const.WINDGUST: "m/s",
    const.UV: "UV",
    const.POWER: "W",
    const.LUMINANCE: "lx",
    const.DEW_POINT: "°C",
    const.BAROMETRIC_PRESSURE: "kPa",
}

DEVICE_PROPERTIES = ["protocol", "model", "unit", "house", "sensorId"]


def method_for_str(s):
    """Map 'turnon' -> TURNON=1 etc.

    >>> method_for_str('turnon')
    1

    >>> method_for_str('turnoff')
    2

    >>> method_for_str('foobar')

    """
    return next((k for k, v in STATES.items() if s == v), None)


def get_mqtt_url():
    """Reads MQTT configuration from $MQTT_URL or ~/.config/mosquitto_pub."""

    ENV_KEY = "MQTT_URL"

    if ENV_KEY in env:
        _LOGGER.debug("%s found in env, using it", ENV_KEY)
        return env[ENV_KEY]

    try:
        with open(
            join(
                env.get("XDG_CONFIG_HOME", join(expanduser("~"), ".config")),
                "mosquitto_pub",
            )
        ) as f:
            config = dict(
                line.replace("-", "").split() for line in f.read().splitlines()
            )
            username = config["username"]
            password = config["pw"]
            host = config["h"]
            port = int(config["p"])
            protocol = "mqtt" if port == 1883 else "mqtts"
            _LOGGER.debug("MQTT credentials loaded from %s", f.name)
            return f"{protocol}://{username}:{password}@{host}:{port}"
    except (OSError, KeyError):
        return None


def whitelisted(
    s, whitelist="_-" + string.ascii_letters + string.digits, substitute="_"
):
    """
    >>> whitelisted("ab/cd#ef(gh")
    'ab_cd_ef_gh'

    >>> whitelisted("ab/cd#ef(gh", substitute='')
    'abcdefgh'
   """
    return "".join(c if c in whitelist else substitute for c in s)


def make_topic(*levels):
    """Create a valid topic.

    >>> make_topic('foo', 'bar')
    'foo/bar'

    """
    return "/".join(whitelisted(level) for level in levels)


class Device:

    subscriptions = {}

    def __init__(self, entity, mqtt, controller, sensor=None):
        self.entity = entity
        self.controller = controller
        self.mqtt = mqtt
        self.sensors = None  # dict containing sub-items
        self.sensor = sensor  # str for sensor item

        if not self.name:
            _LOGGER.error("Name is missing for entity %s", entity)
            exit()

        if "class" not in self.entity:
            # optional in config file, since it can be
            # derrived from presence of the sensorId property
            self.entity["class"] = ("sensor", "command")[self.is_command]

    def __str__(self):
        return self.visible_name

    @property
    def aliases(self):
        return self.entity.get("aliases", [])

    @property
    def commands(self):
        return [self.command] + self.aliases

    @property
    def command(self):
        return dict((k, self.entity.get(k)) for k in DEVICE_PROPERTIES)

    def is_recipient(self, packet, entity=None):
        def is_recipient(cmd):
            properties = DEVICE_PROPERTIES
            if packet.get("group"):
                properties = (prop for prop in properties if prop != "unit")

            return all(
                cmd.get(prop) == packet.get(prop) for prop in properties
            )

        return any(is_recipient(command) for command in self.commands)

    @classmethod
    async def route_message(cls, topic, payload):
        device = Device.subscriptions.get(topic)
        if device:
            await device.receive_message(topic, payload)
        else:
            _LOGGER.warning("No subscriber to message on topic %s", topic)

    async def receive_message(self, topic, payload):
        """Receive a packet from MQTT, e.g. from Home Assistant."""
        _LOGGER.debug("Received payload %s on topic %s", payload, topic)
        if topic == self.command_topic:
            method = method_for_str(payload)
            if not method:
                _LOGGER.warning("Unknown method: %s", payload)
                return
            await self.publish_state(payload)  # republish as new state
            self.execute(method)
        elif topic == self.brightness_command_topic:
            await self.publish(
                self.brightness_state_topic, payload, retain=True
            )
            self.execute(const.DIM, param=payload)
        else:
            _LOGGER.warning("Unknown topic: %s", topic)

    async def receive_local(self, packet):
        """Receive a packet form the controller / local network / UDP."""
        if not self.is_recipient(packet):
            return False

        if self.is_binary_sensor or self.sensor is not None:
            await self.publish_discovery()

        if self.is_command or self.is_binary_sensor:
            method = method_for_str(packet["method"])
            state = STATES[method]
            await self.publish_availability()
            await self.publish_state(state)

            if method == const.TURNON and self.auto_off:
                #  FIXME: wait 10 seconds?
                _LOGGER.debug("Turning off automatically")
                await self.publish_state(STATE_OFF)

        elif self.sensor is not None:
            state = next(
                item["value"]
                for item in packet["data"]
                if item["name"] == self.sensor
            )
            await self.publish_state(state)
        else:
            # Delegate to aggregate of sensors
            if not self.sensors:
                self.sensors = {
                    item["name"]: Device(
                        self.entity, self.mqtt, self.controller, item["name"]
                    )
                    for item in packet["data"]
                }
            for sensor in self.sensors.values():
                await sensor.receive_local(packet)

        return True

    @property
    def component(self):
        return self.entity.get("component", "sensor")

    @property
    def name(self):
        return self.entity.get("name")

    @property
    def device_class(self):
        """Return safety, etc."""
        return self.entity.get("device_class")

    @property
    def icon(self):
        return self.entity.get("icon") or self.default_icon

    @property
    def optimistic(self):
        return self.entity.get("optimistic", True)

    @property
    def invert(self):
        return self.entity.get("invert", False)

    @property
    def auto_off(self):
        return self.entity.get("auto_off", False)

    @property
    def visible_name(self):
        if self.is_sensor:
            return f"{self.name} {self.quantity_name}"
        return self.name

    @property
    def is_binary_sensor(self):
        return self.component == "binary_sensor"

    @property
    def is_sensor(self):
        return self.component == "sensor"

    @property
    def is_command(self):
        return self.component in ["switch", "light", "lock"]

    @property
    def is_binary(self):
        return self.component in ["binary_sensor", "switch", "light"]

    @property
    def is_light(self):
        return self.component == "light"

    @property
    def is_dimmer(self):
        return self.entity.get("dimmer", False) or "dimmer" in self.entity.get(
            "model", ""
        )

    @property
    def unique_id(self):
        if self.is_command:
            return ("command", self.component, self.name.lower())
        elif self.is_binary_sensor:
            return (self.component, self.name.lower())
        elif self.is_sensor:
            return ("sensor", self.name.lower(), self.quantity_name.lower())
        _LOGGER.error("Should not happen")

    @property
    def controller_id(self):
        return (STATE_PREFIX, self.controller._mac)

    @property
    def discovery_object_id(self):
        """e.g. sensor_bedroom_temperature
                light_kitchen
        object_id should be [a-zA-Z0-9_-+]"""
        return whitelisted("_".join(self.unique_id))

    @property
    def discovery_node_id(self):
        """e.g. tellsticknet_ABC123
        homeassistant node_id should be [a-zA-Z0-9_-+]"""
        return whitelisted("_".join(self.controller_id))

    @property
    def discovery_topic(self):
        """e.g. homeassistant/sensor/tellsticknet_ABC123/
                command_light_bedroom/config"""
        return make_topic(
            DISCOVERY_PREFIX,
            self.component,
            self.discovery_node_id,
            self.discovery_object_id,
            "config",
        )

    def make_topic(self, *levels):
        """e.g. tellsticknet/ABC123/command/light/bedroom/set"""
        return make_topic(*self.controller_id, *self.unique_id, *levels)

    @property
    def state_topic(self):
        return self.make_topic("state")

    @property
    def availability_topic(self):
        return self.make_topic("avail")

    @property
    def command_topic(self):
        return self.make_topic("set")

    @property
    def brightness_command_topic(self):
        return self.make_topic("brightness", "set")

    @property
    def brightness_state_topic(self):
        return self.make_topic("brightness", "state")

    @property
    def discovery_payload(self):
        res = dict(
            name=self.visible_name,
            state_topic=self.state_topic,
            availability_topic=self.availability_topic,
            payload_available=STATE_ONLINE,
            payload_not_available=STATE_OFFLINE,
        )
        if self.is_command and self.command_topic:
            res.update(command_topic=self.command_topic)
        if self.device_class:
            res.update(device_class=self.device_class)
        if self.icon:
            res.update(icon=self.icon)
        if self.is_sensor:
            res.update(unit_of_measurement=self.unit)
        if self.is_command:
            res.update(optimistic=self.optimistic, retain=True)
        if self.is_binary:
            res.update(payload_on=STATE_ON, payload_off=STATE_OFF)
        if self.is_light:
            res.update(optimistic=True)
        if self.is_dimmer:
            res.update(
                brightness_command_topic=self.brightness_command_topic,
                brightness_state_topic=self.brightness_state_topic,
                brightness_scale=255,
            )
        # FIXME: Missing components: cover etc
        return res

    async def publish(self, topic, payload, retain=False):
        payload = (
            dump_json(payload) if isinstance(payload, dict) else str(payload)
        )
        _LOGGER.debug(f"Publishing on {topic}: {payload}")
        await self.mqtt.publish(topic, payload.encode("utf-8"), retain=retain)
        _LOGGER.debug(f"Published on {topic}: {payload}")

    async def subscribe_to(self, topic):
        _LOGGER.debug("Subscribing to %s", topic)
        from hbmqtt.mqtt.constants import QOS_1

        await self.mqtt.subscribe([(topic, QOS_1)])
        _LOGGER.debug("Subscribed to %s", topic)
        Device.subscriptions[topic] = self

    async def subscribe(self):
        if self.is_command:
            await self.subscribe_to(self.command_topic)
        if self.is_dimmer:
            await self.subscribe_to(self.brightness_command_topic)

    def execute(self, command, param=None):
        self.controller.execute(self.command, command, param=param)

    async def publish_discovery(self, items=None):
        await self.publish(
            self.discovery_topic, self.discovery_payload, retain=True
        )
        await self.publish_availability()
        await self.subscribe()

    async def publish_availability(self):
        await self.publish(
            self.availability_topic, STATE_ONLINE, retain=self.is_command
        )

    def maybe_invert(self, state):
        if self.invert and state in [STATE_ON, STATE_OFF]:
            _LOGGER.debug(f"Inverting {state}")
        if self.invert and state == STATE_ON:
            return STATE_OFF
        elif self.invert and state == STATE_OFF:
            return STATE_ON
        return state

    async def publish_state(self, state):
        # FIXME: Better to invert payload_foo in config?
        state = self.maybe_invert(state)
        if not state:
            _LOGGER.warning(f"No state available for {self}")
            return
        _LOGGER.debug(f"Publishing state for {self}: {state}")
        await self.publish(self.state_topic, state, retain=self.is_command)

    @property
    def unit(self):
        return SENSOR_UNITS.get(self.sensor)

    @property
    def default_icon(self):
        return SENSOR_ICONS.get(self.sensor)

    @property
    def quantity_name(self):
        return SENSOR_NAMES.get(self.sensor)


async def run(discover, config):
    _LOGGER.debug("Found %d devices in config", len(config))

    logging.getLogger("hbmqtt.client.plugins.packet_logger_plugin").setLevel(
        logging.WARNING
    )

    client_id = "tellsticknet_{hostname}_{time}".format(
        hostname=hostname(), time=time()
    )

    _LOGGER.debug("Client id is %s", client_id)

    mqtt = MQTTClient(client_id=client_id)

    mqtt_url = get_mqtt_url()

    devices_setup = asyncio.Event()

    async def mqtt_task():
        try:
            _LOGGER.info("Connecting")
            await mqtt.connect(uri=mqtt_url, cleansession=False)
            _LOGGER.info("Connected to MQTT server")
        except ConnectException as e:
            exit("Could not connect to MQTT server: %s" % e)

        await devices_setup.wait()
        while True:
            _LOGGER.debug("Waiting for MQTT messages")
            try:
                message = await mqtt.deliver_message()
                packet = message.publish_packet
                topic = packet.variable_header.topic_name
                payload = packet.payload.data.decode("ascii")
                _LOGGER.debug("got message on %s: %s", topic, payload)
                await Device.route_message(topic, payload)
            except ClientException as e:
                _LOGGER.error("MQTT Client exception: %s", e)

    loop = asyncio.get_event_loop()
    loop.create_task(mqtt_task())
    controller = await discover()

    if not controller:
        await mqtt._connected_state.wait()
        await mqtt.disconnect()
        exit("No tellstick device found")

    _LOGGER.info("Controller found")
    await mqtt._connected_state.wait()
    _LOGGER.info("Connected to MQTT server")

    # FIXME: Make it possible to have more components with same component
    # type but different device_class_etc

    _LOGGER.debug("Setting up devices")
    devices = [
        Device(e, mqtt, controller)
        for e in config
        if e.get("controller", controller.mac_address).lower()
        in (controller.ip_address, controller.mac_address)
    ]
    _LOGGER.debug("Configured %d devices", len(devices))
    devices_setup.set()

    # Commands are visible directly,
    # sensors only when data becomes available
    await asyncio.gather(
        *[
            device.publish_discovery()
            for device in devices
            if device.is_command
        ]
    )

    _LOGGER.info("Waiting for packets")
    async for packet in controller.events():
        if not packet:  # timeout
            continue
        received = [await d.receive_local(packet) for d in devices]
        if not any(received):
            _LOGGER.warning("Skipped packet %s", packet)
        # FIXME: Mark as unavailable if not heard from in time t (24 hours?)
        # FIXME: Use config expire in config (like 6 hours?)
