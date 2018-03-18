#!/usr/bin/env python3
# -*- mode: python; coding: utf-8 -*-
"""
Gateway to Home Assistant using MQTT

Usage: 
  hass_mqtt_gw [-v|-vv] [options]
  hass_mqtt_gw (-h | --help)
  hass_mqtt_gw --version

Options:
  -h --help             Show this message
  -v,-vv                Increase verbosity
  --version             Show version
"""

# FIXME: Send commands via crontab
# FIXME: Common config

import docopt
import logging
from time import time
from json import dumps as dump_json
from base64 import b64encode
from collections import OrderedDict
from os.path import join, expanduser
from os import environ as env
from os.path import join, dirname, expanduser
from requests import certs
from threading import current_thread
from time import sleep
from types import SimpleNamespace as ns
from math import floor
from sys import stderr, argv
from itertools import product
from yaml import safe_load as load_yaml
import paho.mqtt.client as paho
from tellsticknet import __version__
from tellsticknet.controller import discover

_LOGGER = logging.getLogger(__name__)

LOGFMT = "%(asctime)s %(levelname)5s (%(threadName)s) [%(name)s] %(message)s"
DATEFMT = "%y-%m-%d %H:%M.%S"


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
        d = dict(line.replace('-', '').split() for line in f.read().splitlines())
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

def on_message(client, userdata, message):
    _LOGGER.info('Got %s', message)
    
class Entity:
    def __init__(self, entity, packet):
        self.entity = entity
        self.packet = packet
        self.controller = None

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
    def visible_name(self):
        return self.name or self.unique_id
        
    @property
    def unique_id(self):
        return '{protocol}_{model}_{house}_{unit}'.format(**self.packet)
                
    @property
    def discovery_prefix(self): 
        return 'homeassistant'
    
    @property
    def topic(self):
        node_id = f'tellsticknet_{self.controller._mac}'
        return f'{self.discovery_prefix}/{self.component}/{node_id}/{self.unique_id}'

    @property
    def discovery_payload(self):
        res = dict(name=self.visible_name,
                   state_topic=self.state_topic,
                   availability_topic=self.availability_topic)
        if self.command_topic:
            res.update(command_topic=self.command_topic)
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
        if self.packet['method'] == 'turnon':
            return 'ON'
        elif self.packet['method'] == 'turnoff':
            return 'OFF'
        else:
            return None

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
        return f'{self.topic}/cmd' if self.component in ['switch', 'lock'] else None

    def publish_discovery(self, mqtt):
        self.publish(mqtt, self.discovery_topic, self.discovery_payload)
        if self.command_topic:
            mqtt.subscribe(self.command_topic)
        
    def publish_availability(self, mqtt):
        self.publish(mqtt, self.availability_topic, 'online')

    def publish_state(self, mqtt):
        if self.state:
            _LOGGER.debug(f'State for {self}: {self.state}')
            self.publish(mqtt, self.state_topic, self.state)
        else:
            _LOGGER.warning(f'No state available for {self}')


def main():
    """Command line interface."""
    args = docopt.docopt(__doc__,
                         version=__version__)

    if args['-v'] == 2:
        log_level=logging.DEBUG
    elif args['-v']:
        log_level=logging.INFO
    else:
        log_level=logging.ERROR

    try:
        import coloredlogs
        coloredlogs.install(level=log_level,
                            stream=stderr,
                            datefmt=DATEFMT,
                            fmt=LOGFMT)
    except ImportError:
        _LOGGER.debug("no colored logs. pip install coloredlogs?")
        logging.basicConfig(level=log_level,
                            stream=stderr,
                            datefmt=DATEFMT,
                            format=LOGFMT)

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
            print('entity', entity)
            publish(Entity(entity, packet))
            
    # FIXXE: Mark as unavailable if not heard from in time t (24 hours?)
    # FIXME: Use config expire in config (like 6 hours?)

if __name__ == '__main__':
   main()
