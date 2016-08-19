def decode(packet):
    """
    https://raw.githubusercontent.com/telldus/telldus/master/telldus-core/service/ProtocolOregon.cpp

    >>> decode(dict(data=0x201F242450443BDD))["data"]["temp"]
    24.2
    >>> decode(dict(data=0x201F242450443BDD))["data"]["humidity"]
    45.0
    """
    

    data = packet["data"]
    value = int(data)
    value >>= 8
    value >>= 8

    hum1 = value & 0xF
    value >>= 8

    neg = value & (1 << 3)
    hum2 = (value >> 4) & 0xF
    value >>= 8

    temp2 = value & 0xF
    temp1 = (value >> 4) & 0xF
    value >>= 8

    temp3 = (value >> 4) & 0xF
    value >>= 8;

    address = value & 0xFF
    value >>= 8

    temperature = ((temp1 * 100) + (temp2 * 10) + temp3)/10.0
    if neg:
        temperature = -temperature

    humidity = (hum1 * 10.0) + hum2

    return dict(packet,
                sensorId=address,
                data=dict(temp=temperature,
                          humidity=humidity))
