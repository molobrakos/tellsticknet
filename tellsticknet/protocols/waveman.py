# pylint: skip-file
import logging
_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolWaveman.cpp

lastArctecCodeSwitchWasTurnOff = False
TURNON = 1
TURNOFF = 2


def method(val):
    _LOGGER.debug("Getting metod for val: %s" , val)
    if val == TURNON:
        method = 14
    elif val == TURNOFF:
        method = 0
    else:
        raise RuntimeError("invalid method", val)
    return method


def methods(model):
    if ( model == "codeswitch"):
        return "TURNON|TURNOFF"

def decode(packet):
    data = packet.pop("data")

    method = data & 0xF00
    method >>= 8

    unit = data & 0xF0
    unit >>= 4
    unit += 1

    house = data & 0xF

    if house > 16 or unit < 1 or unit > 16:
        # not waveman
        _LOGGER.debug("Not Waveman")
        return

    house = chr(house + ord('A'))  # house from A to P

    global lastArctecCodeSwitchWasTurnOff

    if method != 6 and lastArctecCodeSwitchWasTurnOff:
        lastArctecCodeSwitchWasTurnOff = False
        # probably a stray turnon or bell
        # (perhaps: only certain time interval since last,
        # check that it's the same house/unit... Will lose
        # one turnon/bell, but it's better than the alternative...
        return

    if method == 6:
        lastArctecCodeSwitchWasTurnOff = True

    ret = dict(packet,
               _class="command",
               protocol="waveman",
               model="codeswitch",
               house=house)

    if method == 0:
        ret.update(unit=unit,
                   method="turnoff")
    elif method == 14:
        ret.update(unit=unit,
                   method="turnon")
    else:
        _LOGGER.debug("Not Waveman")
        return

    return ret
