def decode(data, args):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolNexa.cpp
    """
    if args["model"] != "selflearning":
        raise NotImplementedError()

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

    return dict(_class="command",
                house=house,
                unit=unit,
                group=group,
                method=method)


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
