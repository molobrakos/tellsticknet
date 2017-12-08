#!/usr/bin/env python3
""" device manager """
# pylint:disable=invalid-name
import logging
import threading
import yaml
from time import sleep
from sys import stdout
from .device import Device
from .controller import Controller


class Tellstick(object):
    """ main object fo tellsick device manager """
    # pylint: disable=too-many-instance-attributes
    def __init__(self, config_file=None, logger=None):
        """
        Adds controllers and  devices
        """
        self._LOGGER = logger or logging.getLogger(__name__)
        self._LOGGER.debug("tellstik initiated")
        self._LOGGER.debug("tellstik config file = %s", config_file)
        with open(config_file, 'r') as stream:
            try:
                self._config = yaml.load(stream)
            except yaml.YAMLError as exc:
                print(exc)
        self._LOGGER.debug("config = %s", self._config)
        self._devices = []
        self._controllers = []
        self._newdevices = [[], [], []]
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

        self._threads = []
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
                s.setSensorValues(packet["data"])
                self._LOGGER.debug("Updated state for sensor %s",
                                   s.name())
                self._LOGGER.debug("To: %s", s.deviceDict())
                new = False
        if new:
            self._LOGGER.info("Discovered new sensor %s", packet)
            self._LOGGER.info("newid %s", self._getnewid())
            name = "Dinamicly added sensor"+str(self._getnewid())
            self._adddevice({'name': name,
                             'id': self._getnewid(),
                             'sensorId': packet["sensorId"],
                             'protocol': packet["protocol"],
                             'model': packet["model"],
                             'controller': controller.id()})

    def _switchhandler(self, packet, controller):
        """ hadels if event is from switch """
        controller_id = frozenset(  # combine "house" and "unit" as id
            {key: value for key, value in packet.items()
             if key in ("house", "unit")}.items()
        )
        new = True
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
        if new:
            if not self._sleept.isAlive():
                self._sleept = threading.Thread(target=self._emptynewdevices,
                                                args=(3, ))
                self._threads.append(self._sleept)
                self._sleept.start()
            if controller_id in self._newdevices[0]:
                if controller_id in self._newdevices[1]:
                    if controller_id in self._newdevices[2]:
                        self._LOGGER.info("Discovered new controller %s",
                                          controller_id)
                        self._LOGGER.info("newid %s", self._getnewid())
                        name = "Dinamicly added swich"+str(self._getnewid())
                        self._adddevice({'name': name,
                                         'id': self._getnewid(),
                                         'parameters': {'house':  packet[
                                                                        "house"
                                                                        ],
                                                        'unit': packet[
                                                                      'unit'
                                                                      ]
                                                        },
                                         'protocol': packet["protocol"],
                                         'model': packet["model"],
                                         'controller': controller.id()})
                    else:
                        self._newdevices[2].append(controller_id)
                else:
                    self._newdevices[1].append(controller_id)
            else:
                self._newdevices[0].append(controller_id)

    def _events(self, controller):
        """ listens for events from telstick net """
        for packet in controller.events():

            if packet is None:
                continue  # timeout

            self._LOGGER.debug("Got packet %s", packet)

            if "sensorId" in packet:
                self._sensorhandler(packet, controller)
            elif "house" and "unit" in packet:
                self._switchhandler(packet, controller)
            self._LOGGER.debug("Returning packet %s", packet)
            yield packet
