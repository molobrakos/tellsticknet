from . import nexa, waveman, sartano
from .. import const
from collections import OrderedDict
import logging

_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/Protocol.cpp


def decode(packet):
    """
    Try each protocol until success
    We must copy packet since "data" key will be popped by
    protocol implementations
    """
    return (
        nexa.decode(packet) or waveman.decode(packet) or sartano.decode(packet)
    )


def encode(model, house, unit, method, param, **kwargs):
    """
    https://github.com/telldus/tellstick-server/blob/master/rf433/src/rf433/ProtocolArctech.py
    """

    if method == const.TURNON and model == "selflearning-dimmer":
        method, param = const.DIM, 255
    elif method == const.DIM and int(param) == 0:
        method = const.TURNOFF

    unit = unit - 1

    if method in (const.TURNON, const.TURNOFF):
        # Native support in Tellstick Net firmware for arctech on/off
        # https://github.com/telldus/tellstick-net/blob/master/firmware/tellsticknet.c#L85
        # https://github.com/telldus/tellstick-net/blob/master/firmware/transmit_arctech.c
        return OrderedDict(
            protocol="arctech",
            model="selflearning",
            house=house,
            unit=unit,
            method=method,
        )

    SHORT = bytes([24])
    LONG = bytes([127])

    ONE = SHORT + LONG + SHORT + SHORT
    ZERO = SHORT + SHORT + SHORT + LONG

    code = SHORT + bytes([255])

    for i in range(25, -1, -1):
        if house & (1 << i):
            code = code + ONE
        else:
            code = code + ZERO

    code = code + ZERO

    if method == const.DIM:
        code = code + SHORT + SHORT + SHORT + SHORT
    elif method == const.TURNOFF:
        code = code + ZERO
    elif method == const.TURNON or method == const.BELL:
        code = code + ONE
    elif method == const.LEARN:
        code = code + ONE
    else:
        _LOGGER.warning("Unknown method")

    for i in range(3, -1, -1):
        if unit & (1 << i):
            code = code + ONE
        else:
            code = code + ZERO

    if method == const.DIM:
        level = int(param) // 16
        for i in range(3, -1, -1):
            if level & (1 << i):
                code = code + ONE
            else:
                code = code + ZERO

    return code + SHORT
