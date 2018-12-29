import socket
import logging
from datetime import timedelta
from time import time
from . import discovery
from .protocol import encode_packet, decode_packet, encode
import asyncio
from .util import sock_recvfrom, sock_sendto

COMMAND_PORT = 42314
TIMEOUT = timedelta(seconds=30)

# re-register ourselves at the device at regular intervals.
# shouldn't really be neccessary byt sometimes the connections seems
# to get lost
REGISTRATION_INTERVAL = timedelta(minutes=10)

COMMAND_REPEAT_TIMES = 2
COMMAND_REPEAT_DELAY = timedelta(seconds=1)

_LOGGER = logging.getLogger(__name__)


async def discover(ip=None, discover_all=False):
    """
    Return all found controllers on the local network
    """

    def make_controller(discovery_data):
        return Controller(*discovery_data[:2])

    discoverer = discovery.discover(
        ip=ip, discover_all=discover_all
    )  # pylint: disable=not-an-iterable
    if discover_all:
        return (
            make_controller(discovery_data)
            async for discovery_data in discoverer
        )  # pylint: disable=not-an-iterable
    try:
        return make_controller(
            await discoverer.__anext__()
        )  # pylint: disable=no-member
    except StopAsyncIteration:
        return None


class Controller:
    def __init__(self, ip, mac):
        self._address = (ip, COMMAND_PORT)
        self._mac = mac
        self._last_registration = None
        self._commands = None
        _LOGGER.debug("Created controller: %s", self)

    @property
    def ip_address(self):
        return self._address[0]

    @property
    def mac_address(self):
        return self._mac.lower()

    def __repr__(self):
        return f"Controller@{self.ip_address} ({self.mac_address})"

    async def _send(self, sock, command, **args):
        """Send a command to the controller
        Available commands documented in
        https://github.com/telldus/tellstick-net/blob/master/
            firmware/tellsticknet.c"""
        packet = encode_packet(command, **args)
        _LOGGER.debug(
            "Sending packet to controller %s <%s>", self._address, packet
        )
        res = await sock_sendto(sock, packet, self._address)
        if res != len(packet):
            raise OSError("Could not send all of packet")

    async def packets(self):
        """Listen forever for network events, yield stream of packets"""

        async def registrator_task(sock):
            while True:
                try:
                    await self._send(sock, "reglistener")
                    _LOGGER.info(
                        "Registered self as listener for device at %s",
                        self._address,
                    )
                except OSError:  # e.g. Network is unreachable
                    # just retry
                    _LOGGER.warning("Could not send registration packet")
                    pass
                await asyncio.sleep(REGISTRATION_INTERVAL.seconds)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", COMMAND_PORT))
            sock.setblocking(0)
            loop = asyncio.get_event_loop()
            loop.create_task(registrator_task(sock))
            while True:
                try:
                    response, address = await sock_recvfrom(sock, 1024)
                    _LOGGER.debug("Got packet from %s", address)
                    if address == self._address:
                        yield response.decode("ascii")
                    else:
                        _LOGGER.warning(
                            "Got unknown response from %s: %s",
                            address,
                            response,
                        )
                except OSError as e:
                    _LOGGER.warning("Could not receive from socket: %s", e)

    async def events(self):
        async for packet in self.packets():  # pylint: disable=not-an-iterable

            if not packet:
                yield None
                continue

            try:
                packet = decode_packet(packet)
            except NotImplementedError:
                _LOGGER.warning(
                    "failed to decode packet, skipping: %s", packet
                )
                continue

            packet.update(lastUpdated=int(time()))
            _LOGGER.debug("Got packet %s", packet)

            yield packet

    async def _execute(self, device, method, param):
        """arctech on/off implemented in firmware here:
         https://github.com/telldus/tellstick-net/blob/master/firmware/tellsticknet.c#L58
         https://github.com/telldus/tellstick-net/blob/master/firmware/transmit_arctech.c
        """

        packet = encode(**device, method=method, param=param)

        if isinstance(packet, bytes):
            packet = dict(S=packet)

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(0)
            try:
                await self._send(sock, "send", **packet)
            except OSError as e:
                _LOGGER.warning("Could not send to socket: %s", e)

    def execute(self, device, method, param=None, repeat=COMMAND_REPEAT_TIMES):
        # FIXME: encode packet once
        # FIXME: Don't create new socket, reuse
        async def task():
            for i in range(0, repeat):
                _LOGGER.debug("Sending time %d of %d", i + 1, repeat)
                await self._execute(device, method, param)
                if i < repeat - 1:
                    _LOGGER.debug(
                        "Waiting %d seconds", COMMAND_REPEAT_DELAY.seconds
                    )
                await asyncio.sleep(COMMAND_REPEAT_DELAY.seconds if i else 0)

        loop = asyncio.get_event_loop()
        return loop.create_task(task())
