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
from tellsticknet import TURNON, TURNOFF, UP, DOWN, STOP
from tellsticknet.controller import discover

_LOGGER = logging.getLogger(__name__)


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
    # FIXME: Command topic does not make sense for all devices
    print(message.topic, message.payload)
    print(Entity.subscriptions.keys())
    entity = Entity.subscriptions.get(message.topic)

    if not entity:
        _LOGGER.warning(f'Unknown recipient for {message.topic}')
        return

    payload = message.payload.decode().lower()

    # FIXME; mapping between
    #  1) raw packet methods (integers, 1,2, etc)
    #  2) command decoded methods (string, turnon etc)
    #  3) MQTT states/methods (string, ON, OFF etc)
    
    METHODS = dict(
        on=TURNON,
        off=TURNOFF)

    method = METHODS.get(payload)

    if method:
        entity.command(method)
        entity.publish_state(client)
    else:
        _LOGGER.warning('Unknown method')


class Entity:

    subscriptions = {}

    def __init__(self, entity, mqtt, controller):
        self.entity = entity
        self.controller = controller
        self.mqtt = mqtt
        
    def __str__(self):
        return self.visible_name

    def is_recipient(self, packet):
        return all(self.entity[prop] == packet[prop]
                   for prop in ['class',
                                'protocol',
                                'model',
                                'unit',
                                'house',
                                'sensorId'])

    def recieve(self, packet):
        if not self.is_recipient(packet):
            return False

        COMMANDS = dict(turnon='ON',
                        turnoff='OFF')
        method = packet.method
        if self.invert:
            if method == 'turnon':
                method = 'turnoff'
            elif method == 'turnoff':
                method = 'turnon'
        state = COMMANDS.get(method)
       
        self.publish_availability()
        self.publish_state(state)

        return True

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
    def invert(self):
        return self.entity.get('invert')

    @property
    def visible_name(self):
        return self.name or self.unique_id

    @property
    def entity_class(self):
        return self.entity['class']
    
    @property
    def is_sensor(self):
        return self.entity_class == 'sensor'
    
    @property
    def unique_id(self):
        if self.is_sensor:
            return '{class}_{protocol}_{model}_{sensorId}'.format(**self.entity)
        return '{class}_{protocol}_{model}_{house}_{unit}'.format(**self.entity)

    @property
    def method(self):
        return self.packet['method']
    
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

    def publish(self, topic, payload, retain=False):
        payload = dump_json(payload) if isinstance(payload, dict) else payload
        _LOGGER.debug(f'Publishing on {topic}: {payload}')
        self.mqtt.publish(topic, payload, retain=retain)

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
        return f'{self.topic}/set'

    @property
    def device(self):
        return {k: v
                for k, v in self.entity.items()
                if k in ['protocol', 'model', 'house', 'unit']}

    def subscribe(self):
        self.mqtt.subscribe(self.command_topic)
        Entity.subscriptions[self.command_topic] = self

    def command(self, command):
        self.controller.execute(self.entity, command)
        
    def publish_discovery(self):
        self.publish(self.discovery_topic,
                     self.discovery_payload, retain=True)
        self.subscribe()

    def publish_availability(self):
        self.publish(self.availability_topic, 'online')

    def publish_state(self, state):
        if self.state:
            _LOGGER.debug(f'State for {self}: {self.state}')
            self.publish(self.state_topic, self.state)
        else:
            _LOGGER.warning(f'No state available for {self}')


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

    mqtt.connect(host=credentials['host'],
                 port=int(credentials['port']))
    mqtt.loop_start()
    
    controllers = discover()
    controller = next(controllers, None) or exit('no tellstick devices found')

    entities = [Entity(e, mqtt, controller) for e in config]
    for entity in entities:
        entity.publish_discovery()

    for packet in controller.events():
        if not any(e.recieve(packet) for e in entities):
            _LOGGER.warning('Skipped packet %s', packet)        

    # FIXXE: Mark as unavailable if not heard from in time t (24 hours?)
    # FIXME: Use config expire in config (like 6 hours?)
