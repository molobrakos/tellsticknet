# pylint: skip-file
def decode(packet):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolMandolyn.cpp

    >>> decode(dict(data=0x134039c3))["data"]["temp"]
    7.8
    """
    data = packet["data"]
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

    return dict(packet,
                sensorId=house*10+channel,
                data=dict(temp=temp,
                          humidity=humidity))
