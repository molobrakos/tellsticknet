def decode(data, args=None):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolFineoffset.cpp

    >>> decode(0x48801aff05)["data"]["temp"]
    2.6
    """

    data = "%x" % int(data)
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
        return dict(model="temperaturehumidity",
                    sensorId=id,
                    data=dict(humidity=humidity,
                              temp=temp))
    else:
        return dict(model="temperature",
                    sensorId=id,
                    data=dict(temp=temp))
