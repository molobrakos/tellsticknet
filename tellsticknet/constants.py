from datetime import datetime, timedelta
TURNON = 1
TURNOFF = 2
BELL = 4
TOGGLE = 8
DIM = 16
LEARN = 32
UP = 128
DOWN = 256
STOP = 512
RGBW = 1024
THERMOSTAT = 2048
COMMAND_PORT = 42314
TIMEOUT = timedelta(seconds=5)
REGISTRATION_INTERVAL = timedelta(minutes=10)
TAG_INTEGER = "i"
TAG_DICT = "h"
TAG_LIST = "l"
TAG_END = "s"
TAG_SEP = ":"
SUPPORTED_METHODS = (
    TURNON |
    TURNOFF |
    DIM |
    UP |
    DOWN |
    STOP)

METHODSI = {
    TURNON: 'turnOn',
    TURNOFF: 'turnOff',
    BELL: 'bell',
    TOGGLE: 'toggle',
    DIM: 'dim',
    LEARN: 'learn',
    UP: 'up',
    DOWN: 'down',
    STOP: 'stop',
    RGBW: 'rgbw',
    THERMOSTAT: 'thermostat'
}

METHODS = {
    'TURNON': TURNON,
    'TURNOFF': TURNOFF,
    'BELL': BELL,
    'TOGGLE': TOGGLE,
    'DIM': DIM,
    'LEARN': LEARN,
    'UP': UP,
    'DOWN': DOWN,
    'STOP': STOP,
    'RGBW': RGBW,
    'THERMOSTAT': THERMOSTAT
}




TEMPERATURE = 'temperature'
HUMIDITY = 'humidity'
RAINRATE = 'rrate'
RAINTOTAL = 'rtot'
WINDDIRECTION = 'wdir'
WINDAVERAGE = 'wavg'
WINDGUST = 'wgust'
UV = 'uv'
WATT = 'watt'
LUMINANCE = 'lum'
DEW_POINT = 'dewp'
BAROMETRIC_PRESSURE = 'barpress'

BATTERY_LOW = 255
BATTERY_UNKNOWN = 254
BATTERY_OK = 253


