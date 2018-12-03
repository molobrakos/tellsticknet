import logging

_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolNexa.cpp


def decode_selflearning(packet):

    data = packet["data"]

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

    return dict(
        packet,
        _class="command",
        house=house,
        unit=unit,
        group=group,
        method=method,
    )


lastArctecCodeSwitchWasTurnOff = False


def decode_codeswitch(packet):

    data = packet["data"]

    method = data & 0xF00
    method >>= 8

    unit = data & 0xF0
    unit >>= 4
    unit += 1

    house = data & 0xF
    if house > 16 or unit < 1 or unit > 16:
        # not arctech codeswitch
        _LOGGER.debug("Not Arctech")
        return

    house = chr(house + ord("A"))  # house from A to P

    global lastArctecCodeSwitchWasTurnOff

    if method != 6 and lastArctecCodeSwitchWasTurnOff:
        lastArctecCodeSwitchWasTurnOff = False
        return

    if method == 6:
        lastArctecCodeSwitchWasTurnOff = True

    ret = dict(
        packet,
        _class="command",
        protocol="arctech",
        model="codeswitch",
        house=house,
    )

    if method == 6:
        ret.update(unit=unit, method="turnoff")
    elif method == 14:
        ret.update(unit=unit, method="turnon")
    elif method == 15:
        ret.update(method="bell")
    else:
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
