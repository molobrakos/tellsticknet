# pylint: skip-file
def decode(packet):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolFineoffset.cpp

    >>> decode(dict(data=0x48801aff05))["data"]["temp"]
    2.6
    """
    data = packet.pop("data")
    data = "%010x" % int(data)
    data = data[:-2]
    humidity = int(data[-2:], 16)

    data = data[:-2]
    value = int(data[-3:], 16)
    temp = (value & 0x7ff) / 10

    value >>= 11
    if (value & 1):
        temp = -temp

    data = data[:-3]
    id = int(data, 16) & 0xff

    if humidity <= 100:
        return dict(packet,
                    model="temperaturehumidity",
                    sensorId=id,
                    data=dict(humidity=humidity,
                              temp=temp))
    else:
        return dict(packet,
                    model="temperature",
                    sensorId=id,
                    data=dict(temp=temp))
