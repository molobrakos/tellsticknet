#!/usr/bin/env python3
""" device manager """
# pylint:disable=invalid-name
import logging
import threading
from time import sleep
from sys import stdout
from .device import Device
from .discovery import discover
from .controller import Controller


class Tellstick(object):
    """ main object fo tellsick device manager """
    # pylint: disable=too-many-instance-attributes
    def __init__(self, config=None, logger=None, host=None):
        """
        Adds controllers and  devices
        """
        self._LOGGER = logger or logging.getLogger(__name__)
        self._LOGGER.debug("tellstik initiated")
        self._config = config
        self._LOGGER.debug("config = %s", self._config)
        self._callback = None
        self._devices = []
        self._controllers = []
        self._newdevices = [[], [], []]

        if self._config is None:
            self._config = {"controllers": {}, 'devices': {}}
        elif not self._config.get("controllers"):
            self._config.update({"controllers": {}})
        elif not self._config.get("devices"):
            self._config.update({"devices": {}})
        ids = []
        for typ, value in self._config.items():
            if typ == "controllers":
                for controller_lab in value.keys():
                    settings = value[controller_lab]
                    ids.append(int(settings.get('id')))
        ids = [0] if not ids else ids
        idx = max(ids)+1
        if host:
            for h in host.split(','):
                controllers = list(self._config.get('controllers'))
                for controller in controllers:
                        if self._config.get('controllers'
                                            ).get(controller, {}
                                                  ).get('address') == h:
                            break
                else:
                    self._config.get('controllers'
                                     ).update({"Controller {}".format(idx):
                                              {'name':
                                               "Controller {}".format(idx),
                                               'id': idx, 'address': h}})
                    idx = + 1

        if self._config.get('controllers') == {}:
            self._LOGGER.debug("No configured controller, autodiscover")
            for rhost, entry in discover():
                self._config.get('controllers'
                                 ).update({entry[1]:
                                          {'name': "{} {}".format(entry[0],
                                                                  entry[1]),
                                           'id': idx, 'address': rhost}})
                idx = + 1

        for typ, value in self._config.items():
            if typ == "controllers":
                for controller_lab in value.keys():
                    settings = value[controller_lab]
                    self._addcontroller(settings)

        for typ, value in self._config.items():
            if typ == "devices":
                for device_lab in value.keys():
                    settings = value[device_lab]
                    self._adddevice(settings)

    def async_listen(self, callback):
        self._threads = []
        self._callback = callback
        for controller in self._controllers:
            t = threading.Thread(target=self.listner, args=(controller,))
            self._threads.append(t)
            t.start()
        self._sleept = threading.Thread(target=self._emptynewdevices,
                                        args=(0,))
        self._threads.append(self._sleept)
        self._sleept.start()

    def _emptynewdevices(self, time):
        if time < 1:
            pass
        else:
            self._LOGGER.debug("Starting timer to empty newdevices")
            sleep(time)
            self._newdevices = [[], [], []]
            self._LOGGER.debug("empty newdevices")

    def _getnewid(self):
        ids = []
        for device in self._devices:
            ids.append(int(device.id()))
        ids = [0] if not ids else ids
        return max(ids)+1

    def _addcontroller(self, settings):
        """ adds cotroller to devicemanager """
        self._LOGGER.debug("controller settings %s", settings)
        self._controllers.append(Controller(settings['address'],
                                 logger=self._LOGGER))
        self._controllers[-1].load(settings)

    def _adddevice(self, settings):
        """ adds device til devicemanager """
        self._LOGGER.debug("device settings %s", settings)
        self._devices.append(Device(logger=self._LOGGER))
        self._devices[-1].load(settings, self._controllers)

    def device(self, deviceId):
        """Retrieves a device.
        Returns:
          the device specified by `deviceId` or None of no device was found
        """
        for d in self._devices:
            if d.id() == deviceId:
                return d

    def listdevices(self):
        """ lists devices """
        devices = []
        for d in self._devices:
            if d.isDevice():
                self._LOGGER.debug("Device %s: ", d)
                self._LOGGER.debug(d.deviceDict())
                devices.append(d.deviceDict())
        return devices

    def listsensors(self):
        """ lists senosors """
        sensors = []
        for d in self._devices:
            if d.isSensor():
                self._LOGGER.debug("Sensor %s: ", d)
                self._LOGGER.debug(d.deviceDict())
                sensors.append(d.deviceDict())
        return sensors

    def controller(self, controllerId):
        """
        Retrieves a controller.
        Returns:
        the controller specified by `controllerId`
        or None of no controller was found
        """
        for c in self._controllers:
            if c.id() == controllerId:
                return c

    def listner(self, controller):
        """ sets up listener for a controller """
        stream = self._events(controller)
        for packet in stream:
            try:
                stdout.flush()
            except IOError:
                pass

    def _sensorhandler(self, packet, controller):
        """ hadels if  event i  from sensor """
        new = True
        for s in self._devices:
            if s.sensorId() == packet["sensorId"]:
                self._LOGGER.debug("Updating state for sensor %s",
                                   s.sensorId())
                updated = s.setSensorValues(packet["data"],
                                            packet['lastUpdated'])
                self._LOGGER.debug("Updated state for sensor %s",
                                   s.name())
                self._LOGGER.debug("To: %s", s.deviceDict())
                new = False
                sensor = s
                break
        if new:
            self._LOGGER.info("Discovered new sensor %s", packet)
            newid = self._getnewid()
            self._LOGGER.info("newid %s", newid)
            name = "(No name)"
            self._adddevice({'name': name,
                             'id': newid,
                             'sensorId': packet["sensorId"],
                             'protocol': packet["protocol"],
                             'model': packet["model"],
                             'controller': controller.id()})
            for s in self._devices:
                if s.sensorId() == packet["sensorId"]:
                    self._LOGGER.debug("Updating state for sensor %s",
                                       s.sensorId())
                    updated = s.setSensorValues(packet["data"],
                                                packet['lastUpdated'])
                    self._LOGGER.debug("Updated state for sensor %s",
                                       s.name())
                    self._LOGGER.debug("To: %s", s.deviceDict())
                    new = False
                    sensor = s
                    break
            updated = True
        if updated:
            return sensor.deviceDict()

    def _switchhandler(self, packet, controller):
        """ hadels if event is from switch """
        controller_id = frozenset(  # combine "house" and "unit" as id
            {key: value for key, value in packet.items()
             if key in ("house", "unit")}.items()
        )
        new = True
        device = None
        for d in self._devices:
            if d.params() is not None:
                controllerid = frozenset(  # combine "house" and "unit" as id
                    {key: value for key, value in d.params().items()
                     if key in ("house", "unit")}.items()
                )

                if controller_id == controllerid:
                    d.setState(packet)
                    self._LOGGER.debug("Updated state for contoller %s",
                                       d.name())
                    new = False
                    device = d
                    break
        if new:
            if not self._sleept.isAlive():
                self._sleept = threading.Thread(target=self._emptynewdevices,
                                                args=(1, ))
                self._threads.append(self._sleept)
                self._sleept.start()
            if controller_id in self._newdevices[0]:
                if controller_id in self._newdevices[1]:
                    if controller_id in self._newdevices[2]:
                        self._LOGGER.info("Discovered new controller %s",
                                          controller_id)
                        self._LOGGER.info("newid %s", self._getnewid())
                        name = "Unknown switch"
                        newid = self._getnewid()
                        from .protocol import Protocol
                        methods = Protocol(protocol=packet["protocol"]
                                           ).methods(
                                                    packet['model'])
                        self._adddevice({'name': name,
                                         'id': newid,
                                         'parameters': {'house':  packet[
                                                                        "house"
                                                                        ],
                                                        'unit': packet[
                                                                      'unit'
                                                                      ]
                                                        },
                                         'protocol': packet["protocol"],
                                         'model': packet["model"],
                                         'metods': methods,
                                         'controller': controller.id()})
                        device = self.device(newid)
                    else:
                        self._newdevices[2].append(controller_id)
                else:
                    self._newdevices[1].append(controller_id)
            else:
                self._newdevices[0].append(controller_id)
        if device is None:
            self._LOGGER.debug("No valid device: %s", packet)
        else:
            self._LOGGER.debug("Valid device found: %s", device)
            self._LOGGER.debug("Valid device found: %s", device.deviceDict())
            return device.deviceDict()

    def _events(self, controller):
        """ listens for events from telstick net """
        for packet in controller.events():

            if packet is None:
                continue  # timeout

            self._LOGGER.debug("Got packet %s", packet)

            if "sensorId" in packet:
                device = self._sensorhandler(packet, controller)
            elif "house" and "unit" in packet:
                device = self._switchhandler(packet, controller)

            if device is not None:
                self._LOGGER.info("Async update of device: %s",
                                  device.get('sensorId'))
                self._callback(device)
            self._LOGGER.debug("Returning packet %s", packet)
            yield packet
