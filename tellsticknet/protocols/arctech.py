from . import nexa, waveman, sartano

import logging
_LOGGER = logging.getLogger(__name__)


def decode(data, args):
    print("ok")
    return nexa.decode(data, args) or \
        waveman.decode(data, args) or \
        sartano.decode(data, args)


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
