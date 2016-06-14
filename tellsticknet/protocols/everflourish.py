import logging
_LOGGER = logging.getLogger(__name__)


def decode(data, args):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """

    house = data & 0xFFFC00
    house >>= 10

    unit = data & 0x300
    unit >>= 8
    unit += 1

    method = data & 0xF

    if house > 16383 or unit < 1 or unit > 4:
        # not everflourish
        return None

    if method == 0:
        method = "turnoff"
    elif method == 15:
        method = "turnon"
    elif method == 10:
        method = "learn"
    else:
        raise RuntimeError("invalid method", method)

    return dict(_class="command",
                model="selflearning",
                house=house,
                unit=unit,
                method=method)


def encode(method):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """
    raise NotImplementedError()
