#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

# FIXME: Send commands via crontab
# FIXME: Common config

import logging
from json import dumps as dump_json
from os import environ as env
from os.path import join, expanduser
from requests import certs
from threading import current_thread
import paho.mqtt.client as paho
from tellsticknet import (
    # FIXME: Namespace
    # Methods
    TURNON,
    TURNOFF,
    BELL,
    TOGGLE,
    DIM,
    UP,
    DOWN,
    STOP,
    RGBW,
    # Sensors
    TEMPERATURE,
    HUMIDITY,
    RAINRATE,
    RAINTOTAL,
    WINDDIRECTION,
    WINDAVERAGE,
    WINDGUST,
    UV,
    POWER,
    LUMINANCE,
    DEW_POINT,
    BAROMETRIC_PRESSURE)
from tellsticknet.controller import discover
from threading import Lock


_LOGGER = logging.getLogger(__name__)

DISCOVERY_PREFIX = 'homeassistant'
STATE_PREFIX = 'tellsticknet'

STATE_ONLINE = 'online'
STATE_OFFLINE = 'offline'

STATES = {
    TURNON: 'turnon',
    TURNOFF: 'turnoff',
    BELL: 'bell',
    TOGGLE: 'toggle',
    DIM: 'dim',
    UP: 'up',
    DOWN: 'down',
    STOP: 'stop',
    RGBW: 'rgbw',
}

SENSOR_ICONS = {
    TEMPERATURE: 'mdi:thermometer',
    HUMIDITY: 'mdi:water',
    RAINRATE: 'mdi:water',
    RAINTOTAL: 'mdi:water',
    DEW_POINT: 'mdi:thermometer'
}

SENSOR_NAMES = {
    TEMPERATURE: 'Temperature',
    HUMIDITY: 'Humidity',
    RAINRATE: 'Rain rate',
    RAINTOTAL: 'Rain total',
    WINDDIRECTION: 'Wind direction',
    WINDAVERAGE: 'Wind average',
    WINDGUST: 'Wind gust',
    UV: 'UV',
    POWER: 'Power',
    LUMINANCE: 'Luminance',
    DEW_POINT: 'Dew Point',
    BAROMETRIC_PRESSURE: 'Barometric Pressure'
}

SENSOR_UNITS = {
    TEMPERATURE: '°C',
    HUMIDITY: '%',
    RAINRATE: 'mm/h',
    RAINTOTAL: 'mm',
    WINDDIRECTION: '',
    WINDAVERAGE: 'm/s',
    WINDGUST: 'm/s',
    UV: 'UV',
    POWER: 'W',
    LUMINANCE: 'lx',
    DEW_POINT: '°C',
    BAROMETRIC_PRESSURE: 'kPa',
}


def threadsafe(function):
    """ Synchronization decorator.
    The paho MQTT library runs the on_subscribe etc callbacks
    in its own thread and since we keep track of subscriptions etc
    in Device.subscriptions, we need to synchronize threads."""
    def wrapper(*args, **kw):
        with Device.lock:
            return function(*args, **kw)
    return wrapper


def method_for_str(s):
    """Map 'turnon' -> TURNON=1, 'turnoff' -> TURNOFF=2, etc."""
    return next((k for k, v in STATES.items()
                 if s == v),
                None)


def read_credentials():
    """Read credentials from ~/.config/mosquitto_pub."""
    with open(join(env.get('XDG_CONFIG_HOME',
                           join(expanduser('~'), '.config')),
                   'mosquitto_pub')) as f:
        d = dict(line.replace('-', '').split()
                 for line in f.read().splitlines())
        return dict(host=d['h'],
                    port=d['p'],
                    username=d['username'],
                    password=d['pw'])


@threadsafe
def on_connect(client, userdata, flags, rc):
    current_thread().setName('MQTTThread')
    _LOGGER.info('Connected')


@threadsafe
def on_publish(client, userdata, mid):
    _LOGGER.debug('Successfully published on %s',
                  Device.subscriptions.pop(mid))


@threadsafe
def on_disconnect(client, userdata, rc):
    _LOGGER.warning('Disconnected')


@threadsafe
def on_subscribe(client, userdata, mid, qos):
    _LOGGER.debug(f'Successfully subscribed to %s',
                  Device.subscriptions.pop(mid))


@threadsafe
def on_message(client, userdata, message):
    _LOGGER.info(f'Got message on {message.topic}: {message.payload}')
    # FIXME: Other entities representing same device
    # FIXME: Command topic does not make sense for all devices

    device = Device.subscriptions.get(message.topic)

    if not device:
        _LOGGER.warning(f'Unknown recipient for {message.topic}')
        return

    payload = message.payload.decode()

    # FIXME; mapping between
    #  1) raw packet methods (integers, 1,2, etc)
    #  2) command decoded methods (string, turnon etc)
    #  3) MQTT states/methods (string, ON, OFF etc)

    method = method_for_str(payload)

    if method:
        device.command(method)
        device.publish_state(payload)  # republish as new state
    else:
        _LOGGER.warning('Unknown method')


class Device:

    subscriptions = {}
    lock = Lock()

    def __init__(self, entity, mqtt, controller, sensor=None):
        self.entity = entity
        self.controller = controller
        self.mqtt = mqtt

        self.sensors = None  # dict containing sub-items
        self.sensor = sensor  # str for sensor item

    def __str__(self):
        return self.visible_name

    def is_recipient(self, packet):
        return all(self.entity.get(prop) == packet.get(prop)
                   for prop in ['class',
                                'protocol',
                                'model',
                                'unit',
                                'house',
                                'sensorId'])

    def receive(self, packet):
        if not self.is_recipient(packet):
            return False

        _LOGGER.debug('%s receives %s', self, packet)

        if self.is_command:
            method = method_for_str(packet['method'])
            state = STATES[method]
            self.publish_availability()
            self.publish_state(state)
        elif self.is_sensor:
            print(packet['data'])
            state = next(item['value']
                         for item in packet['data']
                         if item['name'] == self.sensor)
            self.publish_discovery()
            self.publish_availability()
            self.publish_state(state)
        else:
            # Delegate to aggregate of sensors
            self.sensors = {
                item['name']: Device(
                    self.entity,
                    self.mqtt,
                    self.controller,
                    item['name'])
                for item in packet['data']}
            for sensor in self.sensors.values():
                sensor.receive(packet)

        return True

    @property
    def component(self):
        return self.entity.get('component', 'sensor')

    @property
    def name(self):
        if self.is_sensor:
            return '{name} {quantity}'.format(name=self.entity.get('name'),
                                              quantity=self.quantity_name)
        return self.entity.get('name')

    @property
    def device_class(self):
        """Return safety, etc."""
        return self.entity.get('device_class')

    @property
    def icon(self):
        return self.entity.get('icon') or self.default_icon

    @property
    def optimistic(self):
        return self.entity.get('optimistic')

    @property
    def invert(self):
        return self.entity.get('invert')

    @property
    def visible_name(self):
        return self.name or self.unique_id

    @property
    def device_kind(self):
        """Return command or sensor."""
        return self.entity['class']

    @property
    def is_sensor(self):
        return self.device_kind == 'sensor' and self.sensor

    @property
    def is_command(self):
        return self.device_kind == 'command'

    @property
    def unique_id(self):
        return ('{class}_{protocol}_{model}_{house}_{unit}'
                if self.is_command else
                '{class}_{protocol}_{model}_{sensorId}_{sensor}').format(
                    sensor=self.sensor, **self.entity)

    @property
    def node_id(self):
        return f'{STATE_PREFIX}_{self.controller._mac}'

    @property
    def discovery_topic(self):
        return (f'{DISCOVERY_PREFIX}/{self.component}/'
                f'{self.node_id}/{self.unique_id}/config')

    @property
    def topic(self):
        return f'{STATE_PREFIX}/{self.controller._mac}/{self.unique_id}'

    @property
    def state_topic(self):
        return f'{self.topic}/state'

    @property
    def availability_topic(self):
        return f'{self.topic}/avail'

    @property
    def command_topic(self):
        return f'{self.topic}/set'

    @property
    def discovery_payload(self):
        res = dict(name=self.visible_name,
                   state_topic=self.state_topic,
                   availability_topic=self.availability_topic,
                   payload_available=STATE_ONLINE,
                   payload_not_available=STATE_OFFLINE)
        if self.command_topic:
            res.update(command_topic=self.command_topic)
        if self.optimistic:
            res.update(optimistic=self.optimistic)
        if self.device_class:
            res.update(device_class=self.device_class)
        if self.icon:
            res.update(icon=self.icon)
        if self.is_sensor:
            res.update(unit_of_measurement=self.unit)
        if self.component in ['binary_sensor', 'switch', 'light']:
            res.update(payload_on=STATES[TURNON],
                       payload_off=STATES[TURNOFF])
        return res

    @threadsafe
    def publish(self, topic, payload, retain=False):
        payload = dump_json(payload) if isinstance(payload, dict) else payload
        _LOGGER.debug(f'Publishing on {topic} (retain={retain}): {payload}')
        res, mid = self.mqtt.publish(topic, payload, retain=retain)
        if res == paho.MQTT_ERR_SUCCESS:
            Device.subscriptions[mid] = self.topic
        else:
            _LOGGER.warning('Failure to publish on %s', topic)

    @threadsafe
    def subscribe(self):
        _LOGGER.debug('Subscribing to %s', self.command_topic)
        res, mid = self.mqtt.subscribe(self.command_topic)
        if res == paho.MQTT_ERR_SUCCESS:
            Device.subscriptions[mid] = self.command_topic
            Device.subscriptions[self.command_topic] = self
        else:
            _LOGGER.warning('Failure to subscribe to %s', self.command_topic)

    def command(self, command):
        self.controller.execute(self.entity, command)

    def publish_discovery(self, items=None):
        self.publish(self.discovery_topic,
                     self.discovery_payload, retain=True)
        self.publish_availability()
        if self.is_command:
            self.subscribe()

    def publish_availability(self):
        self.publish(self.availability_topic, STATE_ONLINE,
                     retain=self.is_command)

    def maybe_invert(self, state):
        if self.invert and state == TURNON:
            return TURNOFF
        elif self.invert and state == TURNOFF:
            return TURNON
        return state

    def publish_state(self, state):
        state = self.maybe_invert(state)
        if state:
            _LOGGER.debug(f'State for {self}: {state}')
            self.publish(self.state_topic, state)
        else:
            _LOGGER.warning(f'No state available for {self}')

    @property
    def unit(self):
        return SENSOR_UNITS.get(self.sensor)

    @property
    def default_icon(self):
        return SENSOR_ICONS.get(self.sensor)

    @property
    def quantity_name(self):
        return SENSOR_NAMES.get(self.sensor)


def run(config):
    credentials = read_credentials()
    mqtt = paho.Client()
    mqtt.username_pw_set(username=credentials['username'],
                         password=credentials['password'])
    mqtt.tls_set(certs.where())

    mqtt.on_connect = on_connect
    mqtt.on_disconnect = on_disconnect
    mqtt.on_publish = on_publish
    mqtt.on_message = on_message
    mqtt.on_subscribe = on_subscribe

    mqtt.connect(host=credentials['host'],
                 port=int(credentials['port']))
    mqtt.loop_start()

    controllers = discover()
    controller = next(controllers, None) or exit('no tellstick devices found')

    devices = [Device(e, mqtt, controller) for e in config]
    for device in devices:
        if device.is_command:
            # Commands are visible directly, sensors when data available
            device.publish_discovery()

    from sys import stdin
    from tellsticknet.protocol import decode_packet
    if not stdin.isatty():
        for line in stdin.readlines():
            line = line.strip()
            timestamp, line = line.split(' ', 1)
            packet = decode_packet(line)
            if packet is None:
                continue
            if not any(d.receive(packet) for d in devices):
                _LOGGER.warning('Skipped packet %s', packet)
            print(packet)
        exit(0)

    for packet in controller.events():
        if not any(d.receive(packet) for d in devices):
            _LOGGER.warning('Skipped packet %s', packet)

    # FIXXE: Mark as unavailable if not heard from in time t (24 hours?)
    # FIXME: Use config expire in config (like 6 hours?)
