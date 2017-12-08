import socket
import logging
from datetime import datetime, timedelta
from time import time
from . import discovery
from .protocol import encode_packet, decode_packet

COMMAND_PORT = 42314
TIMEOUT = timedelta(seconds=5)

# re-register ourselves at the device at regular intervals.
# shouldn't really be neccessary byt sometimes the connections seems
# to get lost
REGISTRATION_INTERVAL = timedelta(minutes=10)

_LOGGER = logging.getLogger(__name__)


def discover():
    """
    Return all found controllers on the local network
    N.b this method blocks
    """
    return (Controller(controller[0]) for controller in discovery.discover())


class Controller:

    def __init__(self, address, logger=None):
        _LOGGER.debug("creating controller with address %s", address)
        super(Controller, self).__init__()
        self._address = address
        self._last_registration = None
        self._stop = False
        self._LOGGER = logger or logging.getLogger(__name__)
        self._id = 0
        self._ignored = None
        self._devices = None
        self._name = None
        self._port = COMMAND_PORT
        self._stop = False
        self._last_registration = None
        self._iscontroller = True

    def id(self):
        """ returns controller id """
        return self._id


    def address(self):
        """ retruns address """
        return self._address


    def port(self):
        """ return controller port """
        return self._port


    def load(self, settings):
        """ loads settnigs from config to contoller object """
        if 'id' in settings:
            self._id = str(settings['id'])
        if 'name' in settings:
            self._name = settings['name']
        if 'port' in settings:
            self._port = str(settings['port'])
        if 'address' in settings:
            self._address = settings['address']
        self._LOGGER.debug("loaded controller: %s, id: %s, address: %s, port: %s",
                           self._name, self._id, self._address, self._port)

    def ignored(self):
        """ retrun ignored """
        return self._ignored


    def iscontroller(self):
        """
        Return True if this is a device.
        """
        return self._iscontroller


    def name(self):
        """ retruns name of controller """
        return self._name if self._name is not None else 'Controller %i' % self._id



    def stop(self):
        self._stop = True


    def _send(self, sock, command, **args):
        """Send a command to the controller
        Available commands documented in
        https://github.com/telldus/tellstick-net/blob/master/
            firmware/tellsticknet.c"""
        packet = encode_packet(command, **args)
        _LOGGER.debug("Sending packet to controller %s:%d <%s>",
                      self._address, COMMAND_PORT, packet)
        sock.sendto(packet, (self._address, COMMAND_PORT))

    def _register_if_needed(self, sock):
        """ register self at controller """

        if self._last_registration:
            since_last_check = datetime.now() - self._last_registration
            if since_last_check < REGISTRATION_INTERVAL:
                return

        _LOGGER.info("Registering self as listener for device at %s",
                     self._address)

        try:
            self._send(sock, "reglistener")
            self._last_registration = datetime.now()
        except OSError:  # e.g. Network is unreachable
            # just retry
            pass


    def packets(self):
        """Listen forever for network events, yield stream of packets"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(1)
            sock.settimeout(TIMEOUT.seconds)
            _LOGGER.debug("Listening for signals from %s", self._address)
            while not self._stop:
                self._register_if_needed(sock)
                try:
                    response, (address, port) = sock.recvfrom(1024)
                    if address != self._address:
                        continue
                    yield response.decode("ascii")
                except (socket.timeout, OSError):
                    pass


    def events(self):
        for packet in self.packets():

            packet = decode_packet(packet)
            if not packet:
                continue  # timeout

            packet.update(lastUpdated=int(time()))
            _LOGGER.debug("Got packet %s", packet)

            yield packet
