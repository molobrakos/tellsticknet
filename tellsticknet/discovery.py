import socket
import logging
from datetime import timedelta

DISCOVERY_PORT = 30303
DISCOVERY_ADDRESS = '<broadcast>'
DISCOVERY_PAYLOAD = b"D"
DISCOVERY_TIMEOUT = timedelta(seconds=5)
SUPPORTED_PRODUCTS = ['TellStickNet',
                      'TellstickZnetLite',
                      'TellstickZnetLiteV2',
                      'TellstickZnet',
                      'TellstickNetV2']
MIN_TELLSTICKNET_FIRMWARE_VERSION = 17

_LOGGER = logging.getLogger(__name__)


def discover(timeout=DISCOVERY_TIMEOUT):
    """Scan network for Tellstick Net devices"""
    _LOGGER.info("Discovering tellstick devices ...")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout.seconds)

        sock.sendto(DISCOVERY_PAYLOAD, (DISCOVERY_ADDRESS, DISCOVERY_PORT))

        while True:
            try:
                data, (address, port) = sock.recvfrom(1024)
                entry = data.decode("ascii").split(":")
                if len(entry) != 4:
                    _LOGGER.info("Malformed reply")
                    continue

                (product, mac, code, firmware) = entry

                _LOGGER.info("Found %s device with firmware %s at %s",
                             product, firmware, address)

                if not any(product in device
                           for device in SUPPORTED_PRODUCTS):
                    _LOGGER.info("Unsupported product %s", product)
                elif (product == 'TellStickNet' and
                      int(firmware) < MIN_TELLSTICK_FIRMWARE_VERSION):
                    _LOGGER.info("Unsupported firmware version: %s", firmware)
                else:
                    yield address, entry

            except socket.timeout:
                break


def mock():
    """Mock a Tellstick Net device listening for discovery requests."""
    _LOGGER.info("Mocking a Tellstick device")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((DISCOVERY_ADDRESS, DISCOVERY_PORT))
        while True:
            data, (address, port) = sock.recvfrom(1024)
            if data == DISCOVERY_PAYLOAD:
                _LOGGER.info("Got discovery request, replying")
                response = "%s:MAC:CODE:%d" % (PRODUCT_TELLSTICK_NET,
                                               MIN_FIRMWARE_VERSION)
                sock.sendto(response.encode("ascii"),
                            (address, port))


if __name__ == '__main__':
    from sys import argv
    if argv[-1] == "mock":
        mock()
    else:
        controllers = list(discover())
        from pprint import pprint
        pprint(controllers)
