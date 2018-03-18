""" """

import sys
import logging

assert sys.version_info >= (3, 0)

_LOGGER = logging.getLogger(__name__)


__version__ = '0.0.1'


def async_listen(host, callback):

    from .discovery import discover
    from .controller import Controller

    def listener():
        h = host or next(discover(), [None])[0]

        if not h:
            _LOGGER.warning('No host to listen no')
            return

        _LOGGER.debug('Listening to host %s', h)

        controller = Controller(*h[:2])

        for packet in controller.events():
            callback(packet)

    from threading import Thread
    Thread(target=listener).start()
