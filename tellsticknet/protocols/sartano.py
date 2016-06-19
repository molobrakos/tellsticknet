import logging
_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolSartano.cpp

def decode(data_in, args):
    data = 0
    mask = 1 << 11
    for i in range(0, 12):
        data >>= 1
        if data_in & mask == 0:
            data |= (1 << 11)
        mask >>= 1

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

    ret = dict(_class="command",
               protocol="sartano",
               model="codeswitch",
               code=code)

    if method == 0:
        ret.update(method="turnoff")
    else:
        ret.update(method="turnon")

    return ret
