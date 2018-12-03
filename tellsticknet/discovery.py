import socket
import logging
from datetime import timedelta
from pprint import pprint
import asyncio

from .util import sock_sendto, sock_recvfrom

DISCOVERY_PORT = 30303
DISCOVERY_ADDRESS = "<broadcast>"
DISCOVERY_PAYLOAD = b"D"
DISCOVERY_TIMEOUT = timedelta(seconds=5)
SUPPORTED_PRODUCTS = ["TellStickNet", "TellstickNetV2", "TellstickZnet"]

MIN_TELLSTICKNET_FIRMWARE_VERSION = 17

_LOGGER = logging.getLogger(__name__)


def parse_discovery_packet(data):
    """
    parse a discovery packet

    >>> parse_discovery_packet(b'TellStickNet:mac:code:17')
    ('mac', 'TellStickNet', '17')

    >>> parse_discovery_packet(b'TellstickNetV2:mac:code:1.1.0:uid')
    ('mac', 'TellstickNetV2', '1.1.0')

    >>> parse_discovery_packet(b'')
    Traceback (most recent call last):
    ...
    ValueError

    # Unsupported version
    >>> parse_discovery_packet(b'TellstickNet:mac:code:1:uid')
    Traceback (most recent call last):
    ...
    ValueError

    # Unsupported product
    >>> parse_discovery_packet(b'TellstickNetV99:mac:code:1.1.0:uid')
    Traceback (most recent call last):
    ...
    ValueError

    # Too many items
    >>> parse_discovery_packet(b'TellStickNet:mac:code:a:b:c:d')
    Traceback (most recent call last):
    ...
    ValueError

    # Too few items
    >>> parse_discovery_packet(b'TellStickNet:mac:code')
    Traceback (most recent call last):
    ...
    ValueError

    """
    entry = data.decode("ascii").split(":")
    if not len(entry) in (4, 5):
        _LOGGER.info("Malformed reply: %s", data)
        raise ValueError

    (product, mac, code, firmware, *uid) = entry

    if not any(device in product for device in SUPPORTED_PRODUCTS):
        _LOGGER.info("Unsupported product %s", product)
        raise ValueError
    elif (
        product == "TellStickNet"
        and int(firmware) < MIN_TELLSTICKNET_FIRMWARE_VERSION
    ):
        _LOGGER.info("Unsupported firmware version: %s", firmware)
        raise ValueError
    else:
        return mac, product, firmware


async def discover(
    ip=DISCOVERY_ADDRESS, timeout=DISCOVERY_TIMEOUT, discover_all=False
):
    """Scan network for Tellstick Net devices"""
    _LOGGER.info("Discovering tellstick devices ...")
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(0)
            ip = ip or DISCOVERY_ADDRESS
            address = (ip, DISCOVERY_PORT)
            await sock_sendto(sock, DISCOVERY_PAYLOAD, address)

            while True:
                try:
                    data, (address, port) = await asyncio.wait_for(
                        sock_recvfrom(sock, 1024), timeout.seconds
                    )
                    _LOGGER.debug("Got %s from %s:%d", data, address, port)
                    mac, product, firmware = parse_discovery_packet(data)
                    _LOGGER.info(
                        "Found %s device with firmware %s at %s",
                        product,
                        firmware,
                        address,
                    )
                    yield (address, mac)
                    if not discover_all:
                        return
                except asyncio.TimeoutError:
                    _LOGGER.debug("Discovery timeout")
                    break
                except ValueError:
                    continue
    except OSError:
        return


def mock():
    """Mock a Tellstick Net device listening for discovery requests."""
    _LOGGER.info("Mocking a Tellstick device")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((DISCOVERY_ADDRESS, DISCOVERY_PORT))
        while True:
            data, address = sock.recvfrom(1024)
            if data == DISCOVERY_PAYLOAD:
                _LOGGER.info("Got discovery request, replying")
                response = "%s:MAC:CODE:%d" % (
                    "TellstickNet",
                    MIN_TELLSTICKNET_FIRMWARE_VERSION,
                )
                sock_sendto(sock, response.encode("ascii"), address)


if __name__ == "__main__":
    from sys import argv

    if argv[-1] == "mock":
        mock()
    elif len(argv) == 2 and argv[1] is not None:
        controllers = list(discover(argv[-1]))
        pprint(controllers)
    else:
        controllers = list(discover())
        pprint(controllers)
