import asyncio
import logging

_LOGGER = logging.getLogger(__name__)

# FIXME: subclass DatagramAbstractProtocol instead?
# https://github.com/python/asyncio/pull/321#issuecomment-187022000
# https://docs.python.org/3/library/asyncio-protocol.html#asyncio.DatagramTransport
# https://docs.python.org/3/library/asyncio-protocol.html#datagram-transports
# https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.create_datagram_endpoint


async def sock_sendto(sock, data, address):
    """async UDP helper"""
    loop = asyncio.get_event_loop()
    blocking = asyncio.Event()
    blocking.set()

    def blocking_cb():
        _LOGGER.debug("Can send now")
        loop.remove_writer(sock)
        blocking.set()

    while True:
        _LOGGER.debug("Sending to sock %s %s:%d", sock, *address)
        await blocking.wait()
        try:
            _LOGGER.debug("Sending packet to %s:%d", *address)
            res = sock.sendto(data, address)
            _LOGGER.debug("Wrote data to sock %s: %s", sock, data)
            return res
        except BlockingIOError:
            _LOGGER.debug("Can not send data yet")
            blocking.clear()
            loop.add_writer(sock, blocking_cb)


async def sock_recvfrom(sock, size):
    """async UDP helper"""
    loop = asyncio.get_event_loop()
    blocking = asyncio.Event()
    blocking.set()

    def blocking_cb():
        _LOGGER.debug("Data available on socket")
        loop.remove_reader(sock)
        blocking.set()

    while True:
        await blocking.wait()
        try:
            _LOGGER.debug("Reading from %s", sock)
            res = sock.recvfrom(size)
            _LOGGER.debug("Got data from sock %s: %s", sock, res)
            return res
        except BlockingIOError:
            _LOGGER.debug("No data available on socket yet")
            blocking.clear()
            loop.add_reader(sock, blocking_cb)
