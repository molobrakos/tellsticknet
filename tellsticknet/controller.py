import socket
import logging
from datetime import datetime, timedelta
from time import time, sleep
from threading import Thread
from queue import Queue, Empty
from . import discovery
from .protocol import encode_packet, decode_packet, encode

COMMAND_PORT = 42314
TIMEOUT = timedelta(seconds=5)

# re-register ourselves at the device at regular intervals.
# shouldn't really be neccessary byt sometimes the connections seems
# to get lost
REGISTRATION_INTERVAL = timedelta(minutes=10)

COMMAND_REPEAT_TIMES = 2
COMMAND_REPEAT_DELAY = timedelta(seconds=1)

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
        self._mac = mac.lower()
        self._last_registration = None
        self._commands = None

    def __repr__(self):
        return f'Controller@{self._ip} ({self._mac})'

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

    def packets(self, timeout=None):
        """Listen forever for network events, yield stream of packets"""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(1)
            sock.settimeout(timeout)
            while True:
                self._register_if_needed(sock)
                try:
                    _LOGGER.debug("Listening for signals from %s", self._ip)
                    response, (ip, port) = sock.recvfrom(1024)
                    _LOGGER.debug("Got packet from %s:%d", ip, port)
                    if ip != self._ip:
                        continue
                    yield response.decode("ascii")
                except socket.timeout:
                    return None
                except OSError:
                    pass

    def events(self, timeout=None):
        for packet in self.packets(timeout):

            packet = decode_packet(packet)
            if not packet:
                return None  # timeout

            packet.update(lastUpdated=int(time()))
            _LOGGER.debug("Got packet %s", packet)

            yield packet

    def _start_sender_thread(self):
        if self._commands:
            return
        self._commands = Queue()
        Thread(target=self._async_executor,
               name='SenderThread',
               daemon=True).start()

    def _execute(self, device, method, param=None):
        """arctech on/off implemented in firmware here:
         https://github.com/telldus/tellstick-net/blob/master/firmware/tellsticknet.c#L58
         https://github.com/telldus/tellstick-net/blob/master/firmware/transmit_arctech.c
        """

        packet = encode(**device, method=method, param=param)

        if isinstance(packet, bytes):
            packet = dict(S=packet)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(1)
            self._send(sock, 'send', **packet)

    def execute(self, device, method,
                param=None,
                repeat=COMMAND_REPEAT_TIMES,
                async=False):
        self._start_sender_thread()
        if async:
            self._commands.put((device, method, param, repeat))
        else:
            for i in range(0, repeat):
                sleep(COMMAND_REPEAT_DELAY.seconds if i else 0)
                _LOGGER.debug('Sending time %d', i+1)
                self._execute(device, method, param)

    def _async_executor(self):
        pending_commands = {}

        def defer(device, method, param, repeat):
            key = tuple(device.values())
            if repeat:
                pending_commands[key] = (device, method, param, repeat)
            else:
                pending_commands.pop(key)

        while True:
            try:
                timeout = (COMMAND_REPEAT_DELAY.seconds
                           if pending_commands else None)
                _LOGGER.debug('Waiting for command %s',
                              ('for %d seconds' % timeout)
                              if timeout else 'forever')
                defer(*self._commands.get(block=True, timeout=timeout))
            except Empty:
                _LOGGER.debug('Queue was empty')
                pass

            for (device, method, param, repeat) in list(
                    pending_commands.values()):
                _LOGGER.debug('Sending time %d', repeat)
                self._execute(device, method, param)
                defer(device, method, param, repeat-1)
