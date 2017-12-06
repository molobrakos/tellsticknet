# pylint: skip-file
import logging
_LOGGER = logging.getLogger(__name__)

def methods(model):
    _LOGGER.debug("Getting metods for Model: %s" , model)
    if ( model == "selflearning-switch" ):
        return "TURNON|TURNOFF"
    elif ( model == "codeswitch" ):
        return "TURNON|TURNOFF"
    elif ( model == "selflearning-dimmmer" ):
        return "TURNON|TURNOFF|DIM"

def method(val):
    _LOGGER.debug("Getting metod for val: %s" , val)
    if val == TURNON:
        method = 1
    elif val == TURNOFF:
        method = 0
    else:
        raise RuntimeError("invalid method", val)
    return method


def decode(packet):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """
    data = packet.pop("data")

    house = data & 0xfffc00
    house >>= 10

    unit = data & 0x300
    unit >>= 8
    unit += 1

    method = data & 0xf

    # _LOGGER.debug("Everflourish (data=%x, house=%d, "
    # "unit=%d, method=%d)",
    # data, house, unit, method)

    if house > 16383 or unit < 1 or unit > 4:
        # not everflourish
        _LOGGER.debug("Not Everflourish (data=%x, house=%d, "
                      "unit=%d, method=%d)",
                      data, house, unit, method)
        return

    if method == 0:
        method = "turnoff"
    elif method == 15:
        method = "turnon"
    elif method == 10:
        method = "learn"
    else:
        _LOGGER.debug("Not Everflourish (data=%x, house=%d, "
                      "unit=%d, method=%d)",
                      data, house, unit, method)
        return

    return dict(packet,
                _class="command",
                model="selflearning",
                house=house,
                unit=unit,
                method=method)


def encode(method):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """
    raise NotImplementedError()
