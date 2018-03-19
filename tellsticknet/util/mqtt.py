#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-

# FIXME: Send commands via crontab
# FIXME: Common config

import logging
from json import dumps as dump_json
from os import environ as env
from os.path import join, dirname, expanduser
from requests import certs
from threading import current_thread
from sys import stderr, argv
from itertools import product
from yaml import safe_load as load_yaml
import paho.mqtt.client as paho
from tellsticknet import __version__
from tellsticknet.controller import discover

_LOGGER = logging.getLogger(__name__)


def make_key(item):
    """Return a unique key for the switch/sensor."""
    FMT_SWITCH = '{class}/{protocol}/{model}/{unit}/{house}'
    FMT_SENSOR = '{class}/{protocol}/{model}/{sensorId}'
    template = FMT_SWITCH if 'unit' in item else FMT_SENSOR
    return template.format(**item)


CONFIG_DIRECTORIES = [
    dirname(argv[0]),
    expanduser('~'),
    env.get('XDG_CONFIG_HOME',
            join(expanduser('~'), '.config'))]

CONFIG_FILES = [
    'tellsticknet.conf',
    '.tellsticknet.conf']


def read_tellsticknet_config():
    for directory, filename in (
            product(CONFIG_DIRECTORIES,
                    CONFIG_FILES)):
        try:
            config = join(directory, filename)
            _LOGGER.debug('checking for config file %s', config)
            with open(config) as config:
                e = load_yaml(config)
                return {
                    make_key(key): [
                        proto
                        for proto in e
                        if make_key(proto) == make_key(key)]
                    for key in e}
        except (IOError, OSError):
            continue
    return {}


def read_mqtt_config():
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


entities = read_tellsticknet_config()


def on_connect(client, userdata, flags, rc):
    current_thread().setName('MQTTThread')
    _LOGGER.info('Connected')


def on_publish(client, userdata, mid):
    _LOGGER.info('Published')


def on_disconnect(client, userdata, rc):
    _LOGGER.warning('Disconnected')


def on_subscribe(client, userdata, mid, qos):
    _LOGGER.debug(f'Subscribed')


def on_message(client, userdata, message):
    _LOGGER.info(f'Got message on {message.topic}: {message.payload}')
    controller, device = Entity.subscriptions(message.topic)
    command = message.payload
    controller.execute(device, command)


COMMANDS = {
    'turnon': 'ON',
    'turnoff': 'OFF'
}


class Entity:

    subscriptions = {}

    def __init__(self, entity, packet):
        self.entity = entity
        self.packet = packet
        self.controller = None

    def __str__(self):
        return self.visible_name

    @property
    def component(self):
        return self.entity.get('component')

    @property
    def name(self):
        return self.entity.get('name')

    @property
    def device_class(self):
        return self.entity.get('device_class')

    @property
    def icon(self):
        return self.entity.get('icon')

    @property
    def unit(self):
        return self.entity.get('unit')

    @property
    def optimistic(self):
        return self.entity.get('optimistic')

    @property
    def visible_name(self):
        return self.name or self.unique_id

    @property
    def unique_id(self):
        return '{protocol}_{model}_{house}_{unit}'.format(**self.device)

    @property
    def discovery_prefix(self):
        return 'homeassistant'

    @property
    def topic(self):
        node_id = f'tellsticknet_{self.controller._mac}'  # noqa: F841
        return (f'{self.discovery_prefix}/{self.component}/'
                f'{node_id}/{self.unique_id}')

    @property
    def discovery_payload(self):
        res = dict(name=self.visible_name,
                   state_topic=self.state_topic,
                   availability_topic=self.availability_topic)
        if self.command_topic:
            res.update(command_topic=self.command_topic)
        if self.optimistic:
            res.update(optimistic=self.optimistic)
        if self.device_class:
            res.update(device_class=self.device_class)
        if self.icon:
            res.update(icon=self.icon)
        if self.unit:
            res.update(unit_of_measurement=self.unit)
        return res

    def publish(self, mqtt, topic, payload, retain=False):
        payload = dump_json(payload) if isinstance(payload, dict) else payload
        _LOGGER.debug(f'Publishing on {topic}: {payload}')
        mqtt.publish(topic, payload)

    @property
    def state(self):
        return COMMANDS.get(self.packet['method'])

    @property
    def _has_command_topic(self):
        return self.component in ['switch', 'light', 'lock']

    @property
    def state_topic(self):
        return f'{self.topic}/state'

    @property
    def discovery_topic(self):
        return f'{self.topic}/config'

    @property
    def availability_topic(self):
        return f'{self.topic}/avail'

    @property
    def command_topic(self):
        return f'{self.topic}/set' if self._has_command_topic else None

    @property
    def device(self):
        return {k:v
                for k,v in self.entity.items()
                if k in ['protocol', 'model', 'house', 'unit']}

    def subscribe(self, mqtt):
        if not self.command_topic:
            return
        mqtt.subscribe(self.command_topic)
        Entity.subscriptions[self.command_topic] = (
            self.controller, self.device)
        from pprint import pprint
        pprint(Entity.subscriptions)

    def publish_discovery(self, mqtt):
        self.publish(mqtt, self.discovery_topic,
                     self.discovery_payload, retain=True)
        self.subscribe(mqtt)

    def publish_availability(self, mqtt):
        self.publish(mqtt, self.availability_topic, 'online')

    def publish_state(self, mqtt):
        if self.state:
            _LOGGER.debug(f'State for {self}: {self.state}')
            self.publish(mqtt, self.state_topic, self.state)
        else:
            _LOGGER.warning(f'No state available for {self}')


def run():
    config = read_mqtt_config()
    mqtt = paho.Client()
    mqtt.username_pw_set(username=config['username'],
                         password=config['password'])
    mqtt.tls_set(certs.where())

    mqtt.on_connect = on_connect
    mqtt.on_disconnect = on_disconnect
    mqtt.on_publish = on_publish
    mqtt.on_message = on_message

    mqtt.connect(host=config['host'],
                 port=int(config['port']))
    mqtt.loop_start()

    controllers = discover()
    controller = next(controllers, None) or exit('no tellstick devices found')

    def publish(entity):
        entity.controller = controller
        entity.publish_discovery(mqtt)
        entity.publish_availability(mqtt)
        entity.publish_state(mqtt)

    for packet in controller.events():
        match = entities.get(make_key(packet))
        if not match:
            _LOGGER.warning('Skipping packet %s', packet)
            continue
        for entity in match:
            publish(Entity(entity, packet))

    # FIXXE: Mark as unavailable if not heard from in time t (24 hours?)
    # FIXME: Use config expire in config (like 6 hours?)

