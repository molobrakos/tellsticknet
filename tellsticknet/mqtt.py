#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

import logging
from json import dumps as dump_json
from os import environ as env
from os.path import join, expanduser
from time import time
from requests import certs
from threading import current_thread
import paho.mqtt.client as paho
from paho.mqtt.client import MQTT_ERR_SUCCESS
import tellsticknet.const as const
from tellsticknet.controller import discover
from threading import RLock, Event
from platform import node as hostname
import string

# FIXME: A command can correspond to multiple entities (e.g. switches/lights)

_LOGGER = logging.getLogger(__name__)


DISCOVERY_PREFIX = 'homeassistant'
STATE_PREFIX = 'tellsticknet'

STATE_ONLINE = 'online'
STATE_OFFLINE = 'offline'

STATES = {
    const.TURNON: 'turnon',
    const.TURNOFF: 'turnoff',
    const.BELL: 'bell',
    const.TOGGLE: 'toggle',
    const.DIM: 'dim',
    const.UP: 'up',
    const.DOWN: 'down',
    const.STOP: 'stop',
    const.RGBW: 'rgbw',
}

STATE_ON = STATES[const.TURNON]
STATE_OFF = STATES[const.TURNOFF]

SENSOR_ICONS = {
    const.TEMPERATURE: 'mdi:thermometer',
    const.HUMIDITY: 'mdi:water',
    const.RAINRATE: 'mdi:water',
    const.RAINTOTAL: 'mdi:water',
    const.DEW_POINT: 'mdi:thermometer'
}

SENSOR_NAMES = {
    const.TEMPERATURE: 'Temperature',
    const.HUMIDITY: 'Humidity',
    const.RAINRATE: 'Rain rate',
    const.RAINTOTAL: 'Rain total',
    const.WINDDIRECTION: 'Wind direction',
    const.WINDAVERAGE: 'Wind average',
    const.WINDGUST: 'Wind gust',
    const.UV: 'UV',
    const.POWER: 'Power',
    const.LUMINANCE: 'Luminance',
    const.DEW_POINT: 'Dew Point',
    const.BAROMETRIC_PRESSURE: 'Barometric Pressure'
}

SENSOR_UNITS = {
    const.TEMPERATURE: '°C',
    const.HUMIDITY: '%',
    const.RAINRATE: 'mm/h',
    const.RAINTOTAL: 'mm',
    const.WINDDIRECTION: '',
    const.WINDAVERAGE: 'm/s',
    const.WINDGUST: 'm/s',
    const.UV: 'UV',
    const.POWER: 'W',
    const.LUMINANCE: 'lx',
    const.DEW_POINT: '°C',
    const.BAROMETRIC_PRESSURE: 'kPa',
}

DEVICE_PROPERTIES = ['protocol',
                     'model',
                     'unit',
                     'house',
                     'sensorId']


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
    """Map 'turnon' -> TURNON=1 etc.

    >>> method_for_str('turnon')
    1

    >>> method_for_str('turnoff')
    2

    >>> method_for_str('foobar')

    """
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


def whitelisted(s,
                whitelist='_-' + string.ascii_letters + string.digits,
                substitute='_'):
    """
    >>> whitelisted("ab/cd#ef(gh")
    'ab_cd_ef_gh'

    >>> whitelisted("ab/cd#ef(gh", substitute='')
    'abcdefgh'
   """
    return ''.join(c if c in whitelist else substitute for c in s)


def make_valid_hass_single_topic_level(s):
    """Transform a multi level topic to a single level.

    >>> make_valid_hass_single_topic_level('foo/bar/baz')
    'foo_bar_baz'

    >>> make_valid_hass_single_topic_level('hello å ä ö')
    'hello______'
    """
    return whitelisted(s)


def make_topic(*levels):
    """Create a valid topic.

    >>> make_topic('foo', 'bar')
    'foo/bar'

    >>> make_topic(('foo', 'bar'))
    'foo/bar'
    """
    if len(levels) == 1 and isinstance(levels[0], tuple):
        return make_topic(*levels[0])
    return '/'.join(levels)


@threadsafe
def on_connect(client, userdata, flags, rc):
    current_thread().setName('MQTTThread')
    if rc != MQTT_ERR_SUCCESS:
        _LOGGER.error('Failure to connect: %d', rc)
        return

    _LOGGER.info('Connected')
    if flags.get('session present', False):
        _LOGGER.debug('Session present')
    else:
        _LOGGER.debug('Session not present, resubscribe to topics')
        for device in Device.devices:
            if device.is_command:
                # Commands are visible directly, sensors when data available
                device.publish_discovery()

    # Go on
    Device.connected.set()


@threadsafe
def on_publish(client, userdata, mid):
    _LOGGER.debug('Successfully published on %s: %s',
                  *Device.pending.pop(mid))


def on_disconnect(client, userdata, rc):
    if rc == MQTT_ERR_SUCCESS:
        # we called disconnect ourselves
        _LOGGER.info('Disconnect successful')
    else:
        _LOGGER.warning('Disconnected, automatically reconnecting')
        Device.connected.clear()


@threadsafe
def on_subscribe(client, userdata, mid, qos):
    topic, device = Device.pending.pop(mid)
    _LOGGER.debug(f'Successfully subscribed to %s', topic)
    client.message_callback_add(topic, device.on_mqtt_message)


@threadsafe
def on_message(client, userdata, message):
    _LOGGER.warning('Got unhandled message on '
                    f'{message.topic}: {message.payload}')


class Device:

    devices = []
    pending = {}

    lock = RLock()
    connected = Event()

    def __init__(self, entity, mqtt, controller, sensor=None):
        self.entity = entity
        self.controller = controller
        self.mqtt = mqtt
        self.sensors = None  # dict containing sub-items
        self.sensor = sensor  # str for sensor item

        if 'class' not in self.entity:
            # optional in config file, since it can be
            # derrived from presence of the sensorId property
            self.entity['class'] = ('sensor', 'command')[self.is_command]

    def __str__(self):
        return self.visible_name

    @property
    def aliases(self):
        return self.entity.get('aliases', [])

    @property
    def commands(self):
        return [self.command] + self.aliases

    @property
    def command(self):
        return dict((k, self.entity.get(k)) for k in DEVICE_PROPERTIES)

    def is_recipient(self, packet, entity=None):

        def is_recipient(cmd):
            properties = DEVICE_PROPERTIES
            if packet.get('group'):
                properties = (prop for prop in properties if prop != 'unit')

            return all(cmd.get(prop) == packet.get(prop)
                       for prop in properties)

        return any(is_recipient(command)
                   for command in self.commands)

    def on_mqtt_message(self, client, userdata, message):
        """Receive a packet from MQTT, e.g. from Home Assistant."""
        topic = message.topic
        payload = message.payload.decode()
        _LOGGER.debug('Received payload %s on topic %s', payload, topic)
        if topic == self.command_topic:
            method = method_for_str(payload)
            if not method:
                _LOGGER.warning('Unknown method: %s', payload)
                return
            self.publish_state(payload)  # republish as new state
            self.execute(method)
        elif topic == self.brightness_command_topic:
            self.publish(self.brightness_state_topic, payload, retain=True)
            self.execute(const.DIM, param=payload)

    def receive_local(self, packet):
        """Receive a packet form the controller / local network / UDP."""
        if not self.is_recipient(packet):
            return False

        _LOGGER.debug('%s receives %s', self, packet)

        if self.is_command:
            method = method_for_str(packet['method'])
            state = STATES[method]
            self.publish_availability()
            self.publish_state(state)

            if method == const.TURNON and self.auto_off:
                _LOGGER.debug('Turning off automatically') # FIXME: wait 10 seconds?
                self.publish_state(STATE_OFF)

        elif self.is_sensor:
            state = next(item['value']
                         for item in packet['data']
                         if item['name'] == self.sensor)
            self.publish_discovery()  # imples availability
            self.publish_state(state)
        else:
            # Delegate to aggregate of sensors
            if not self.sensors:
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
            return '{name} {quantity}'.format(
                name=self.entity.get('name'),
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
        return self.entity.get('optimistic', True)

    @property
    def invert(self):
        return self.entity.get('invert', False)

    @property
    def auto_off(self):
        return self.entity.get('auto_off', False)

    @property
    def visible_name(self):
        return self.name or self.unique_id

    @property
    def is_sensor(self):
        return 'sensorId' in self.entity

    @property
    def is_command(self):
        return not self.is_sensor

    @property
    def is_binary(self):
        return self.component in ['binary_sensor', 'switch', 'light']

    @property
    def is_light(self):
        return self.component == 'light'

    @property
    def is_dimmer(self):
        return (self.entity.get('dimmer', False) or
                'dimmer' in self.entity.get('model', ''))

    @property
    def unique_id(self):
        name = self.name.lower()
        if self.is_command:
            return ('command', self.component, name)
        elif self.is_sensor:
            return ('sensor', name)
        _LOGGER.error('Should not happen')

    @property
    def controller_topic(self):
        return make_topic(STATE_PREFIX,
                          self.controller._mac)

    @property
    def discovery_object_id(self):
        """object_id should be [a-zA-Z0-9_-+]"""
        return make_valid_hass_single_topic_level(make_topic(self.unique_id))

    @property
    def discovery_node_id(self):
        """node_id should be [a-zA-Z0-9_-+]"""
        return make_valid_hass_single_topic_level(self.controller_topic)

    @property
    def discovery_topic(self):
        return make_topic(DISCOVERY_PREFIX,
                          self.component,
                          self.discovery_node_id,
                          self.discovery_object_id,
                          'config')

    @property
    def topic(self):
        return make_topic(self.controller_topic,
                          *self.unique_id)

    def make_topic(self, *levels):
        return make_topic(self.topic, *levels)

    @property
    def state_topic(self):
        return self.make_topic('state')

    @property
    def availability_topic(self):
        return self.make_topic('avail')

    @property
    def command_topic(self):
        return self.make_topic('set')

    @property
    def brightness_command_topic(self):
        return self.make_topic('brightness', 'set')

    @property
    def brightness_state_topic(self):
        return self.make_topic('brightness', 'state')

    @property
    def discovery_payload(self):
        res = dict(name=self.visible_name,
                   state_topic=self.state_topic,
                   retain=True,
                   availability_topic=self.availability_topic,
                   payload_available=STATE_ONLINE,
                   payload_not_available=STATE_OFFLINE)
        if self.command_topic:
            res.update(command_topic=self.command_topic)
        if self.device_class:
            res.update(device_class=self.device_class)
        if self.icon:
            res.update(icon=self.icon)
        if self.is_sensor:
            res.update(unit_of_measurement=self.unit)
        if self.is_command:
            res.update(optimistic=self.optimistic)
        if self.is_binary:
            res.update(payload_on=STATE_ON,
                       payload_off=STATE_OFF)
        if self.is_light:
            res.update(optimistic=True)
        if self.is_dimmer:
            res.update(brightness_command_topic=self.brightness_command_topic,
                       brightness_state_topic=self.brightness_state_topic,
                       brightness_scale=255)
        # FIXME: Missing components: cover etc
        return res

    @threadsafe
    def publish(self, topic, payload, retain=False):
        payload = dump_json(payload) if isinstance(payload, dict) else payload
        _LOGGER.debug(f'Publishing on {topic} (retain={retain}): {payload}')
        res, mid = self.mqtt.publish(topic, payload, retain=retain)
        if res == MQTT_ERR_SUCCESS:
            Device.pending[mid] = (topic, payload)
        else:
            _LOGGER.warning('Failure to publish on %s', topic)

    @threadsafe
    def subscribe_to(self, topic):
        _LOGGER.debug('Subscribing to %s', topic)
        res, mid = self.mqtt.subscribe(topic)
        if res == MQTT_ERR_SUCCESS:
            Device.pending[mid] = (topic, self)
        else:
            _LOGGER.warning('Failure to subscribe to %s', self.topic)

    def subscribe(self):
        if self.is_command:
            self.subscribe_to(self.command_topic)
        if self.is_dimmer:
            self.subscribe_to(self.brightness_command_topic)

    def execute(self, command, param=None):
        self.controller.execute(self.command, command, param=param, async=True)

    def publish_discovery(self, items=None):
        self.publish(self.discovery_topic,
                     self.discovery_payload, retain=True)
        self.publish_availability()
        self.subscribe()

    def publish_availability(self):
        self.publish(self.availability_topic, STATE_ONLINE,
                     retain=self.is_command)

    def maybe_invert(self, state):
        if self.invert and state in [STATE_ON, STATE_OFF]:
            _LOGGER.debug(f'Inverting {state}')
        if self.invert and state == STATE_ON:
            return STATE_OFF
        elif self.invert and state == STATE_OFF:
            return STATE_ON
        return state

    def publish_state(self, state):
        # FIXME: Better to invert payload_foo in config?
        state = self.maybe_invert(state)
        if not state:
            _LOGGER.warning(f'No state available for {self}')
            return
        _LOGGER.debug(f'Publishing state for {self}: {state}')
        self.publish(self.state_topic, state, retain=self.is_command)

    @property
    def unit(self):
        return SENSOR_UNITS.get(self.sensor)

    @property
    def default_icon(self):
        return SENSOR_ICONS.get(self.sensor)

    @property
    def quantity_name(self):
        return SENSOR_NAMES.get(self.sensor)


def run(config, host):

    _LOGGER.debug('Reading credentials')
    credentials = read_credentials()

    _LOGGER.debug('Discovering Tellstick')
    # FIXME: Allow multiple controllers on same network (just loop in init)
    controllers = discover(host)
    controller = next(controllers, None) or exit('no tellstick devices found')

    client_id = 'tellsticknet_{hostname}_{time}'.format(
        hostname=hostname(),
        time=time())

    _LOGGER.debug('Client id is %s', client_id)

    mqtt = paho.Client(client_id=client_id,
                       clean_session=False)
    mqtt.username_pw_set(username=credentials['username'],
                         password=credentials['password'])
    mqtt.tls_set(certs.where())

    _LOGGER.debug('Setting up devices')
    # FIXME: Make it possible to have more components with same component
    # type but different device_class_etc

    _LOGGER.debug('Found %d devices in config', len(config))
    Device.devices = [Device(e, mqtt, controller)
                      for e in config
                      if e.get('controller',
                               controller._mac).lower() in (
                                   controller._ip,
                                   controller._mac)]

    _LOGGER.debug('Configured %d devices', len(Device.devices))

    mqtt.on_connect = on_connect
    mqtt.on_disconnect = on_disconnect
    mqtt.on_publish = on_publish
    mqtt.on_message = on_message
    mqtt.on_subscribe = on_subscribe

    _LOGGER.debug('Connecting')
    mqtt.connect(host=credentials['host'],
                 port=int(credentials['port']))
    mqtt.loop_start()

    #  For debugging, allow pipe a previous packet capture to stdin
    #  FIXME: flag instead
    #  from sys import stdin
    #  from tellsticknet.protocol import decode_packet
    #  if not stdin.isatty():
    #      for line in stdin.readlines():
    #          line = line.strip()
    #          timestamp, line = line.split(' ', 1)
    #          packet = decode_packet(line)
    #          if packet is None:
    #              continue
    #          if not any(d.receive(packet) for d in devices):
    #              _LOGGER.warning('Skipped packet %s', packet)
    #          print(packet)
    #      exit(0)

    from datetime import timedelta
    for packet in controller.events(timedelta(seconds=5)):

        if not packet:  # timeout
            continue

        if not Device.connected.is_set():
            _LOGGER.debug('Waiting for connection')
            Device.connected.wait()
            _LOGGER.debug('Connected, start listening for Tellstick packets')

        # print('%15s %15s %2s %2s' % (packet['protocol'],
        #       packet['house'], packet['unit'], packet.get('group', '-')))
        received = [d.receive_local(packet) for d in Device.devices]
        if not any(received):
            _LOGGER.warning('Skipped packet %s', packet)

    # FIXME: Mark as unavailable if not heard from in time t (24 hours?)
    # FIXME: Use config expire in config (like 6 hours?)
