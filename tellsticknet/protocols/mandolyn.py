def decode(data):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolMandolyn.cpp

    >>> decode(0x134039c3)["data"]["temp"]
    7.8
    """

    value = int(data)
    value >>= 1
    temp = ((value & 0x7fff) - 6400) / 128
    temp = round(temp, 1)

    value >>= 15
    humidity = value & 0x7f

    value >>= 7
    value >>= 3
    channel = (value & 0x3) + 1

    value >>= 2
    house = value & 0xf

    return dict(sensorId=house*10+channel,
                data=dict(temp=temp,
                          humidity=humidity))
