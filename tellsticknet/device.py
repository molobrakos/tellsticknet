# -*- coding: utf-8 -*-
""" device module """
import socket
import logging
import time
from .protocol import Protocol
# pylint:disable=invalid-name
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
GENRIC_METER = 4096

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


class Device(object):
    """
    A base class for a device.
    """
    FAILED_STATUS_RETRIES_FAILED = 1
    FAILED_STATUS_NO_REPLY = 2
    FAILED_STATUS_TIMEDOUT = 3
    FAILED_STATUS_NOT_CONFIRMED = 4

    BATTERY_LOW = 255  # Battery status, if not percent value
    BATTERY_UNKNOWN = 254  # Battery status, if not percent value
    BATTERY_OK = 253  # Battery status, if not percent value

    # pylint: disable=too-many-instance-attributes
    def __init__(self, logger=None):
        super(Device, self).__init__()
        self._LOGGER = logger or logging.getLogger(__name__)
        self._controllerobj = None
        self._controllername = None
        self._id = ''
        self._ignored = None
        self._loadCount = 0
        self._name = None
        self._protocol = None
        self._params = None
        self._manager = None
        self._model = None
        self._state = TURNOFF
        self._stateValue = 'unde'
        self._sensorValues = None
        self._scale = None
        self._sensorId = None
        self._confirmed = True
        self._controller = None
        self._controllerid = None
        self._client = None
        self._is_sensor = None
        self._methods = None
        self._battery = self.BATTERY_UNKNOWN
        self.online = 1
        self.valueChangedTime = {}
        self.lastUpdated = None
        self.lastUpdatedLive = {}

    def __str__(self):
        if self._is_sensor:
            return 'Sensor #{id_:>08} {name:<20} '.format(
                id_=self._id,
                name=self._name or "UNNAMED_DEVICE")
        else:
            return ('Device #{id_} \'{name}\' '
                    '({state}:{value}) [{methods}]').format(
                        id_=self._id,
                        name=self._name or "UNNAMED_DEVICE",
                        state=self._str_methods(self._state),
                        value=self._stateValue,
                        methods=self._methods)

    def load(self, settings, controllers):
        """ loads values from config file """
        if 'id' in settings:
            self._id = str(settings['id'])
        if 'name' in settings:
            self._name = settings['name']
        if 'parameters' in settings:
            self._params = settings['parameters']
        if 'sensorId' in settings:
            self._sensorId = settings['sensorId']
            self._is_sensor = True
            if 'scale' in settings:
                self._scale = settings['scale']
            else:
                self._scale = 1
        if 'protocol' in settings:
            self._protocol = Protocol(protocol=settings['protocol'])
            if not self._is_sensor:
                self._methods = self._protocol.methods(settings['model'])
        if 'model' in settings:
            self._model = settings['model'].split("-")[0]
        if 'controller_id' in settings:
            self._controller = str(settings['controller_id'])
            for c in controllers:
                if c.id() == self._controller:
                    self._controllername = c.name()
                if c.id() == self._controller:
                    self._controllerobj = c

    def deviceDict(self):
        """ retruns dict reprecenting device """
        if self.isDevice():
            return {'id': self._id,
                    'client': self._client,
                    'online': '1',
                    'statevalue': self._stateValue,
                    'name': self._name,
                    'type': 'device',
                    'clientName': self._controllername,
                    'methods': self._int_methods(self._methods),
                    'editable': 0,
                    'clientDeviceId': self._controller,
                    'ignored': 0,
                    'state': self._state}

        elif self.isSensor():
            return {'id': self._id,
                    'name': self._name,
                    'lastUpdated': self.lastUpdated,
                    'ignored': 0,
                    'client': self._client,
                    'clientName': self._controllername,
                    'online': '1',
                    'editable': 0,
                    'battery': self._battery,
                    'keepHistry': 0,
                    'protocol': str(self._protocol),
                    'model': self._model,
                    'sensorId': self._sensorId,
                    'miscValues': 'null',
                    "data": self._sensorValues}
        else:
            return {}

    @staticmethod
    def _str_methods(val):
        """String representation of methods or state."""
        res = []
        for method in METHODSI:
            if val & method:
                res.append(METHODSI[method].upper())
        return "|".join(res)

    @staticmethod
    def _int_methods(val):
        """Int representation of methods or state."""
        res = 0
        for method in val.split("|"):
            res += METHODS[method]
        return res

    def id(self):
        """ returns id """
        return self._id

    def params(self):
        """ retruns ditct of pramameters """
        return self._params

    def battery(self):
        """
        Returns the current battery value
        """
        return self._battery

    def command(self, action, value=None, ignore=None):
        """This method executes a method with the device."""
        # Prevent loops from groups and similar
        if ignore is None:
            ignore = []
        if self.id() in ignore:
            return
        ignore.append(self.id())
        method = action
        if method == DIM:
            if value is None:
                value = 0  # this is an error, but at least won't crash now
            else:
                value = int(value)
        elif method == RGBW:
            if isinstance(value) == str:
                value = int(value, 16)
            elif isinstance(value) is not int:
                value = 0
        elif method == THERMOSTAT:
            pass
        else:
            value = None

        if method == 0:
            return
        try:
            self._command(method, value)
        # pylint: disable=broad-except
        except Exception as e:
            logging.exception(e)
        # pylint: enable=broad-except

    def _command(self, action, value):
        """ sends command to tellstick """
        self._LOGGER.debug("action: %s, value: %s", action, value)
        controller = self._controllerobj
        protocol = self._protocol
        if not protocol:
            self._LOGGER.warning("Unknown protocol %s", self._protocol)
            return
        protocol.setModel(self._model)
        protocol.setParameters(self._params)
        protocol.setMethod(action)
        msg = protocol.encode('send')
        self._LOGGER.debug("msg: %s", msg)
        self._LOGGER.debug("controller._address: %s", controller.address())
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setblocking(1)
                sock.settimeout(3)
                sock.sendto(msg, (controller.address(), controller.port()))
        except OSError as msg:  # e.g. Network is unreachable
            # just retry
            self._LOGGER.debug("Exception: %s", msg)

    def ignored(self):
        """ retrus ignored """
        return self._ignored

    def isDevice(self):
        """
        Return True if this is a device.
        """
        return False if self._sensorId else True

    def isSensor(self):
        """
        Return True if this is a sensor.
        """
        return True if self._sensorId else False

    def sensorId(self):
        """ returns sensor id """
        return self._sensorId

    def methods(self):
        """
        Return the methods this supports.
        This is an or-ed in of device method flags.

        Example:
        return TURNON | TURNOFF
        """
        return self._methods or 0

    def name(self):
        """ returns name """
        return self._name if self._name is not None else 'Device %i' % self._id

    def protocol(self):
        """ returns protocol """
        return self._protocol

    def model(self):
        """ retruns model """
        return self._model

    def sensorValue(self, valueType, scale):
        """
        Returns a sensor value of a the specified
        valueType and scale. Returns None
        is no such value exists
        """
        if valueType not in self._sensorValues:
            return None
        for sensorType in self._sensorValues[valueType]:
            if sensorType['scale'] == scale:
                return float(sensorType['value'])
        return None

    def sensorValues(self):
        """
        Returns a list of all sensor values this device has received.
        """
        return self._sensorValues

    def setId(self, id_):
        """ set id """
        self._id = id_

    def setIgnored(self, ignored):
        """ sets ignored """
        self._ignored = ignored
        if self._manager:
            self._manager.save()

    def setName(self, name):
        """ sets name """
        self._name = name

    def setParams(self, params):
        """ sets params """
        self._params = params

    def setSensorValues(self, sensorValues, lastUpdated):
        # this method just fills cached values, no signals or reports are sent
        if lastUpdated == self.lastUpdated:
            self._LOGGER.debug("lastUpdated %s is the same" +
                               "as self.lastUpdated %s",
                               lastUpdated, self.lastUpdated)
            return False  # return false if same timestamp
        else:
            self._LOGGER.debug("lastUpdated %s is not self.lastUpdated" +
                               "%s updating sensor",
                               lastUpdated, self.lastUpdated)
            self._sensorValues = []
            for i, valueTypeFetch in enumerate(sensorValues):
                self._sensorValues.append({
                    'value': valueTypeFetch['value'],
                    'scale': self._scale,
                    'lastUpdated': lastUpdated,
                    'name': valueTypeFetch['name']})
            self.lastUpdated = lastUpdated
            return True

    def setSensorValue(self, valueType, value, scale):
        """ sets sensor value """
        if valueType not in self._sensorValues:
            self._sensorValues[valueType] = []
        found = False
        for sensorType in self._sensorValues[valueType]:
            if sensorType['scale'] == scale:
                if (sensorType['value'] != str(value) or
                   valueType not in self.valueChangedTime):
                    # value has changed
                    self.valueChangedTime[valueType] = int(time.time())
                else:
                    if sensorType['lastUpdated'] > int(time.time() - 1):
                        """
                        same value and less than a second ago,
                        most probably just the same value being resent,
                        ignore
                        """
                        return
                sensorType['value'] = str(value)
                sensorType['lastUpdated'] = int(time.time())
                found = True
                break
        if not found:
            self._sensorValues[valueType].append({'value': str(value),
                                                  'scale': scale,
                                                  'name': valueType,
                                                  'lastUpdated': int(time.time(
                                                                    ))
                                                  })
            self.valueChangedTime[valueType] = int(time.time())

    def setState(self, state):
        """  sets device state """
        self._LOGGER.debug("state: %s", state)
        if self.lastUpdated and self.lastUpdated > int(time.time() - 1):
            """same state/statevalue and less than one second ago,
               most probably just the same value being resent, ignore"""
            return
        self.lastUpdated = time.time()
        self._state = METHODS[state['method'].upper()]
        self._stateValue = state.get('value', 'unde')

    def state(self):
        """
        Returns a tuple of the device state and state value

        Example:
        state, stateValue = device.state()
        """
        return (self._state, self._stateValue)

    @staticmethod
    def methodStrToInt(method):
        """Convenience method to convert method string to constants.

        Example:
        "turnon" => TURNON
        """
        if method == 'turnon':
            return TURNON
        if method == 'turnoff':
            return TURNOFF
        if method == 'dim':
            return DIM
        if method == 'bell':
            return BELL
        if method == 'learn':
            return LEARN
        if method == 'up':
            return UP
        if method == 'down':
            return DOWN
        if method == 'stop':
            return STOP
        if method == 'rgbw':
            return RGBW
        if method == 'thermostat':
            return THERMOSTAT
        logging.warning('Did not understand device method %s', method)
        return 0

    @staticmethod
    def maskUnsupportedMethods(methods, supportedMethods):
        """ masks unsupported methods """
        # Up -> Off
        if methods & UP and not supportedMethods & UP:
            methods = methods | TURNOFF

        # Down -> On
        if methods & DOWN and not supportedMethods & DOWN:
            methods = methods | TURNON

        """
        Cut of the rest of the unsupported methods
        we don't have a fallback for
        """
        return methods & supportedMethods

    @staticmethod
    def sensorTypeIntToStr(sensorType):
        """ converts sensortype values to strings """
        types = {
            TEMPERATURE: 'temp',
            HUMIDITY: 'humidity',
            RAINRATE: 'rrate',
            RAINTOTAL: 'rtot',
            WINDDIRECTION: 'wdir',
            WINDAVERAGE: 'wavg',
            WINDGUST: 'wgust',
            UV: 'uv',
            WATT: 'watt',
            LUMINANCE: 'lum',
            DEW_POINT: 'dewp',
            BAROMETRIC_PRESSURE: 'barpress',
            GENRIC_METER: 'genmeter'
        }
        return types.get(sensorType, 'unknown')


class Sensor(Device):
    """A convenience class for sensors."""
    def isDevice(self):
        return False

    def isSensor(self):
        return True

    def name(self):
        return self._name if self._name is not None else 'Sensor %i' % self._id
