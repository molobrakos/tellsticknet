# pylint: skip-file
def decode(packet):
    """
    https://raw.githubusercontent.com/telldus/telldus/master/telldus-core/service/ProtocolOregon.cpp

    >>> decode(dict(data=0x201F242450443BDD, model=6701))["data"]["temp"]
    24.2
    >>> decode(dict(data=0x201F242450443BDD, model=6701))["data"]["humidity"]
    45.0
    """

    if packet["model"] != 6701:
        raise NotImplementedError("The Oregon model %i is not implemented."
                                  % packet["model"])

    data = packet["data"]
    value = int(data)
    value >>= 8
    checksum1 = value & 0xFF
    value >>= 8

    checksum = ((value >> 4) & 0xF) + (value & 0xF)
    hum1 = value & 0xF
    value >>= 8

    checksum += ((value >> 4) & 0xF) + (value & 0xF)
    neg = value & (1 << 3)
    hum2 = (value >> 4) & 0xF
    value >>= 8

    checksum += ((value >> 4) & 0xF) + (value & 0xF)
    temp2 = value & 0xF
    temp1 = (value >> 4) & 0xF
    value >>= 8

    checksum += ((value >> 4) & 0xF) + (value & 0xF)
    temp3 = (value >> 4) & 0xF
    value >>= 8

    checksum += ((value >> 4) & 0xF) + (value & 0xF)
    address = value & 0xFF
    value >>= 8

    checksum += ((value >> 4) & 0xF) + (value & 0xF)
    checksum += 0x1 + 0xA + 0x2 + 0xD - 0xA

    if checksum != checksum1:
        raise ValueError("The checksum in the Oregon packet does not match "
                         "the caluclated one!")

    temperature = ((temp1 * 100) + (temp2 * 10) + temp3)/10.0
    if neg:
        temperature = -temperature

    humidity = (hum1 * 10.0) + hum2

    return dict(packet,
                sensorId=address,
                data=dict(temp=temperature,
                          humidity=humidity))
