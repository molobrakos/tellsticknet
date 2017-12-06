# pylint: skip-file
from . import nexa, waveman, sartano

import logging
_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/Protocol.cpp


def decode(packet):
    """
    Try each protocol until success
    We must copy packet since "data" key will be popped by
    protocol implementations
    """
    return nexa.decode(packet.copy()) or \
        waveman.decode(packet.copy()) or \
        sartano.decode(packet.copy())


def methods(model):
    return nexa.methods(model) or \
        waveman.methods(model) or \
        sartano.methods(model)

def method(model):
    return nexa.method(model) or \
        waveman.method(model) or \
        sartano.method(model)


def encode(what):
    """
    protocol = 'arctech'
    model = 'selflearning'
    house = 53103098
    unit = 0
    method = 2
    msg = "4:sendh8:protocol%X:%s5:model%X:%s5:housei%Xs4
    ":uniti%Xs6:methodi%Xss" %
    (len(protocol), protocol, len(model), model, house, unit, method)
    """
    pass
