# pylint: skip-file
import logging
_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolSartano.cpp

TURNON = 1
TURNOFF = 2


def method(val):
    _LOGGER.debug("Getting metod for val: %s" , val)
    if val == TURNON:
        method = 1
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

    data2 = 0
    mask = 1 << 11
    for i in range(0, 12):
        data2 >>= 1
        if data & mask == 0:
            data2 |= (1 << 11)
        mask >>= 1

    data = data2

    code = data & 0xFFC
    code >>= 2

    method1 = data & 0x2
    method1 >>= 1

    method2 = data & 0x1

    if method1 == 0 and method2 == 1:
        method = 0  # off
    elif method1 == 1 and method2 == 0:
        method = 1  # on
    else:
        return

    if code > 1023:
        _LOGGER.debug("Not Sartano")
        return

    mask = 1 << 9
    code2 = ""
    for i in range(0, 10):
        if code & mask != 0:
            code2 += "1"
        else:
            code2 += "0"
        mask >>= 1
    code = code2

    ret = dict(packet,
               _class="command",
               protocol="sartano",
               model="codeswitch",
               code=code)

    if method == 0:
        ret.update(method="turnoff")
    else:
        ret.update(method="turnon")

    return ret
