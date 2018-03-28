#!/usr/bin/env python3
"""
Interact with Tellstick Net device on local network

Usage:
  tellsticknet (-h | --help)
  tellsticknet --version
  tellsticknet [-v|-vv] [options] discover
  tellsticknet [-v|-vv] [options] listen [--raw]
  tellsticknet [-v|-vv] [options] send <name> <cmd>
  tellsticknet [-v|-vv] [options] send <protocol> <model> <house> <unit> <cmd>
  tellsticknet [-v|-vv] [options] mqtt
  tellsticknet [-v|-vv] [options] mock
  tellsticknet [-v|-vv] [options] parse

Options:
  -H <ip>               IP of Tellstick Net device
  --raw                 Print raw packets instead of parsed data
  -h --help             Show this message
  -v,-vv                Increase verbosity
  --version             Show version
"""

import docopt
import logging
import re
from datetime import datetime
from sys import argv, stdout, stderr, stdin
from os.path import join, dirname, expanduser
from os import environ as env
from itertools import product
from yaml import safe_load_all as load_yaml

from tellsticknet import __version__, const
from tellsticknet.protocol import decode_packet
from tellsticknet.controller import discover

from json import dumps as to_json

LOGFMT = "%(asctime)s %(levelname)5s (%(threadName)s) [%(name)s] %(message)s"
DATEFMT = "%y-%m-%d %H:%M.%S"
LOG_LEVEL = logging.DEBUG
_LOGGER = logging.getLogger(__name__)


def parse_isoformat(s):
    """Parse string with date in ISO 8601 format as datetime

    >>> parse_isoformat("2016-01-15T11:39:15")
    datetime.datetime(2016, 1, 15, 11, 39, 15)
    """
    return datetime(*map(int, re.split("[-:T]", s)))


def parse_stdin():
    """Parse protocol data passed on stdin, previously captured

    example to print all captured sensor id:s
    script/listen > /tmp/packets.log
    cat /tmp/packets.log  | ./script/parse | jq ".sensorId" | sort | uniq
    """
    for line in stdin.readlines():
        line = line.strip()
        if " " in line:
            # assume we have date + raw data separated by space
            timestamp, line = line.split(' ', 1)
            timestamp = parse_isoformat(timestamp)
            lastUpdated = int(timestamp.timestamp())
            packet = decode_packet(line)
            if packet is None:
                continue
            packet.update(lastUpdated=lastUpdated, time=timestamp.isoformat())
            print(to_json(packet))
        else:
            print(to_json(decode_packet(line)))


def prepend_timestamp(line):
    """Add ISO 8601 timestamp to line"""
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    return "{} {}".format(timestamp, line)


def print_event_stream(raw=False):
    """Print event stream"""
    controllers = discover()

    # for now only care about one controller
    controller = next(controllers, None) or exit('no tellstick devices found')

    if raw:
        stream = map(prepend_timestamp, controller.packets())
    else:
        stream = (to_json(event) for event in controller.events())

    for packet in stream:
        print(packet)
        try:
            stdout.flush()
        except IOError:
            # broken pipe
            pass


CONFIG_DIRECTORIES = [
    dirname(argv[0]),
    expanduser('~'),
    env.get('XDG_CONFIG_HOME',
            join(expanduser('~'), '.config'))]

CONFIG_FILES = [
    'tellsticknet.conf',
    '.tellsticknet.conf']


def read_config():
    for directory, filename in (
            product(CONFIG_DIRECTORIES,
                    CONFIG_FILES)):
        try:
            config = join(directory, filename)
            _LOGGER.debug('checking for config file %s', config)
            with open(config) as config:
                return list(load_yaml(config))
        except (IOError, OSError):
            continue
    return {}


if __name__ == "__main__":
    args = docopt.docopt(__doc__,
                         version=__version__)

    log_level = [logging.ERROR, logging.INFO, logging.DEBUG][args['-v']]

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

    if args['parse'] and not stdin.isatty():
        parse_stdin()
    elif args['mock']:
        from tellsticknet.discovery import mock
        mock()
    elif args['discover']:
        for c in discover():
            print(c)
    elif args['listen']:
        print_event_stream(raw=args['--raw'])
    elif args['send']:
        controller = (next(discover(), None)
                      or exit('No tellstick devices found'))
        config = [e for x in read_config().values() for e in x]

        cmd = args['<cmd>']
        METHODS = dict(
            on=const.TURNON,
            turnon=const.TURNON,
            off=const.TURNOFF,
            turnoff=const.TURNOFF,
            up=const.UP,
            down=const.DOWN,
            stop=const.STOP)
        method = METHODS.get(cmd.lower()) or exit('method not found')

        name = args['<name>']
        protocol = args['<protocol>']
        model = args['<model>']
        house = args['<house>']
        unit = args['<unit>']

        if name:
            devices = (e for e in config
                       if e['name'].lower().startswith(name.lower()))
            if not devices:
                exit(f'Device with name {name} not found')
        elif protocol and model and house and unit:
            pass  # FIXME
        for device in devices:
            controller.execute(device, method)
    elif args['mqtt']:
        from tellsticknet.mqtt import run
        config = read_config()
        host = args['-H']
        run(config, host=host)
