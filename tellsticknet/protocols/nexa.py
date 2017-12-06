# pylint: skip-file
import logging
_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolNexa.cpp
TURNON = 1
TURNOFF = 2


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

def decode_selflearning(packet):

    data = packet.pop("data")

    house = data & 0xFFFFFFC0
    house >>= 6

    group = data & 0x20
    group >>= 5

    method = data & 0x10
    method >>= 4

    unit = data & 0xF
    unit += 1

    if house < 1 or house > 67108863 or unit < 1 or unit > 16:
        return

    if method == 1:
        method = "turnon"
    elif method == 0:
        method = "turnoff"
    else:
        raise RuntimeError("invalid method", method)

    return dict(packet,
                _class="command",
                house=house,
                unit=unit,
                group=group,
                method=method)

lastArctecCodeSwitchWasTurnOff = False


def decode_codeswitch(packet):

    data = packet.pop("data")

    # print("data %x" % data)
    method = data & 0xF00
    # print("%x" % method)
    method >>= 8
    # print("%x" % method)

    unit = data & 0xF0
    unit >>= 4
    unit += 1

    house = data & 0xF
    # print(house, unit)
    if house > 16 or unit < 1 or unit > 16:
        # not arctech codeswitch
        _LOGGER.debug("Not Arctech")
        return

    house = chr(house + ord('A'))  # house from A to P
    # print(house)
    global lastArctecCodeSwitchWasTurnOff
    # print(method)

    if method != 6 and lastArctecCodeSwitchWasTurnOff:
        lastArctecCodeSwitchWasTurnOff = False
        # probably a stray turnon or bell
        # (perhaps: only certain time interval since last,
        # check that it's the same house/unit
        # Will lose one turnon/bell, but it's better than the alternative...
        return

    if method == 6:
        lastArctecCodeSwitchWasTurnOff = True

    ret = dict(packet,
               _class="command",
               protocol="arctech",
               model="codeswitch",
               house=house)

    if method == 6:
        ret.update(unit=unit,
                   method="turnoff")
    elif method == 14:
        ret.update(unit=unit,
                   method="turnon")
    elif method == 15:
        ret.update(method="bell")
    else:
        _LOGGER.debug("Not Arctech")
        # not arctech codeswitch
        return

    return ret


def decode(packet):
    if packet["model"] == "selflearning":
        return decode_selflearning(packet)
    elif packet["model"] == "codeswitch":
        return decode_codeswitch(packet)
    else:
        raise NotImplementedError()
