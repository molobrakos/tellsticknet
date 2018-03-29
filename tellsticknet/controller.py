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


def discover(host=None):
    """
    Return all found controllers on the local network
    N.b this method blocks
    """
    return (Controller(*controller[:2])
            for controller in discovery.discover(host))


class Controller:

    def __init__(self, ip, mac):
        _LOGGER.debug("creating controller with address %s (%s)", ip, mac)
        self._ip = ip
        self._mac = mac
        self._last_registration = None
        self._stop = False

    def __repr__(self):
        return f'Controller@{self._ip} ({self._mac})'

    def stop(self):
        self._stop = True

    def _send(self, sock, command, **args):
        """Send a command to the controller
        Available commands documented in
        https://github.com/telldus/tellstick-net/blob/master/
            firmware/tellsticknet.c"""
        packet = encode_packet(command, **args)
        _LOGGER.debug("Sending packet to controller %s:%d <%s>",
                      self._ip, COMMAND_PORT, packet)
        sock.sendto(packet, (self._ip, COMMAND_PORT))

    def _register_if_needed(self, sock):
        """ register self at controller """

        if self._last_registration:
            since_last_check = datetime.now() - self._last_registration
            if since_last_check < REGISTRATION_INTERVAL:
                return

        _LOGGER.info("Registering self as listener for device at %s",
                     self._ip)

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
            _LOGGER.debug("Listening for signals from %s", self._ip)
            while not self._stop:
                self._register_if_needed(sock)
                try:
                    response, (ip, port) = sock.recvfrom(1024)
                    if ip != self._ip:
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

    def execute(self, device, method):
        from collections import OrderedDict
        device = OrderedDict(protocol=device['protocol'],
                             model=device['model'],
                             house=device['house'],
                             unit=device['unit']-1)  # huh, why?
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(1)
            self._send(sock, 'send', **device, method=method)
