def decode(data):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolNexa.cpp
    """
    raise NotImplementedError()


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
