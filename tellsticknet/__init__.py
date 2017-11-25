""" """

import sys
assert sys.version_info >= (3, 0)

import logging

from .discovery import discover
from .controller import Controller

_LOGGER = logging.getLogger(__name__)

def async_listen(host, callback):

    def listener():
        nonlocal host
        host = host or next(discover(), [None])[0]

        if not host:
            _LOGGER.warning('No host to listen no')
            return

        _LOGGER.debug('Listening to host %s', host)

        controller = Controller(host)

        for packet in controller.events():
            event_callback(packet)

    from threading import Thread
    Thread(target=listener).run()
