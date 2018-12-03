import logging

_LOGGER = logging.getLogger(__name__)


def decode(packet):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """
    data = packet["data"]

    house = data & 0xFFFC00
    house >>= 10

    unit = data & 0x300
    unit >>= 8
    unit += 1

    method = data & 0xF

    # _LOGGER.debug("Everflourish (data=%x, house=%d, "
    # "unit=%d, method=%d)",
    # data, house, unit, method)

    if house > 16383 or unit < 1 or unit > 4:
        # not everflourish
        return

    if method == 0:
        method = "turnoff"
    elif method == 15:
        method = "turnon"
    elif method == 10:
        method = "learn"
    else:
        # not everflourish
        return

    return dict(
        packet,
        _class="command",
        model="selflearning",
        house=house,
        unit=unit,
        method=method,
    )


def encode(method):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """
    raise NotImplementedError()
