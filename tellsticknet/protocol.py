"""
encode/and decode protocol as described in
https://developer.telldus.com/doxygen/html/TellStickNet.html
"""

import logging

_LOGGER = logging.getLogger(__name__)


TAG_INTEGER = ord("i")
TAG_DICT = ord("h")
TAG_LIST = ord("l")
TAG_END = ord("s")
TAG_SEP = ord(":")
CMD_DELAY = "P"
CMD_REP = "R"

CMD_REPEAT_RF_TIMES = 4 #Number of packets the Tellstick Net will send
CMD_REPEAT_RF_DELAY = 10 #Delay between packets in milliseconds


def _expect(condition):
    if not condition:
        raise ValueError()


def _encode_bytes(s):
    """
    encode a string

    >>> _encode_bytes(b'hello')
    b'5:hello'

    >>> _encode_bytes(b'hellothere')
    b'A:hellothere'

    >>> _encode_bytes(b'')
    b'0:'

    >>> _encode_bytes(4711)
    Traceback (most recent call last):
        ...
    TypeError: object of type 'int' has no len()
    """
    return b"%X%c%s" % (len(s), TAG_SEP, s)


def _encode_string(s):
    """
    encode a string

    >>> _encode_string('hello')
    b'5:hello'

    >>> _encode_string('hellothere')
    b'A:hellothere'

    >>> _encode_string('')
    b'0:'

    >>> _encode_string(4711)
    Traceback (most recent call last):
        ...
    AttributeError: 'int' object has no attribute 'encode'
    """
    return _encode_bytes(s.encode())


def _encode_integer(d):
    """
    encode a integer

    >>> _encode_integer(42)
    b'i2as'

    >>> _encode_integer(-42)
    b'i-2as'

    >>> _encode_integer(0)
    b'i0s'

    >>> _encode_integer(3.3)
    b'i3s'
    """
    return b"%c%x%c" % (TAG_INTEGER, int(d), TAG_END)


def _encode_dict(d):
    """
    encode a dict

    >>> from collections import OrderedDict

    >>> _encode_dict(OrderedDict(baz=42, foo='bar'))
    b'h3:bazi2as3:foo3:bars'

    >>> _encode_dict({})
    b'hs'

    >>> _encode_dict([])
    Traceback (most recent call last):
        ...
    ValueError

    >>> _encode_dict(None)
    Traceback (most recent call last):
        ...
    ValueError
    """
    _expect(isinstance(d, dict))

    return b"%c%s%c" % (
        TAG_DICT,
        b"".join(_encode_any(x) for keyval in d.items() for x in keyval),
        TAG_END,
    )


def _encode_list(l):
    """https://developer.telldus.com/doxygen/html/TellStickNet.html"""
    raise NotImplementedError("Encode for List type missing")


def _encode_any(t):
    if isinstance(t, int):
        return _encode_integer(t)
    elif isinstance(t, bytes):
        return _encode_bytes(t)
    elif isinstance(t, str):
        return _encode_string(t)
    elif isinstance(t, dict):
        return _encode_dict(t)
    elif isinstance(t, list):
        return _encode_list(t)
    else:
        raise NotImplementedError("Unknown type")


def encode_packet(command, **args):
    """
    encode a packet

    >>> encode_packet("hello", foo="x")
    b'5:helloh3:foo1:xs'

    >>> encode_packet("hello", data=dict(number=7))
    b'5:helloh4:datah6:numberi7sss'
    """
    res = _encode_string(command)
    if args:
        res += _encode_dict(args)
    if command == "send":
        res += _encode_string(CMD_DELAY) + _encode_integer(CMD_REPEAT_RF_DELAY)
        res += _encode_string(CMD_REP) + _encode_integer(CMD_REPEAT_RF_TIMES)
    return res


def _decode_string(packet):
    """
    decode a string
    returns tuple (decoded string, rest of packet not consumed)

    >>> _decode_string(b'5:hello')
    ('hello', b'')

    >>> _decode_string(b'5:hell')
    Traceback (most recent call last):
        ...
    ValueError

    >>> _decode_string(b'hello')
    Traceback (most recent call last):
        ...
    ValueError
    """
    sep = packet.find(TAG_SEP)
    _expect(sep > 0)
    length = packet[:sep]
    length = int(length, 16)
    start = 1 + sep
    end = start + length
    _expect(end <= len(packet))
    val = packet[start:end]
    return val.decode(), packet[end:]


def _decode_integer(packet):
    """
    decode an integer
    returns tuple (decoded integer, rest of packet not consumed)

    >>> _decode_integer(b'i4711s')
    (18193, b'')

    >>> _decode_integer(b'i0s')
    (0, b'')

    >>> _decode_integer(b'i-3s')
    (-3, b'')

    >>> _decode_integer(b'i03s') # invalid according to specification
    (3, b'')

    >>> _decode_integer(b'i-0s') # invalid according to specification
    (0, b'')

    # this is invalid according to specification but seems to be
    # generated anyway
    >>> _decode_integer(b'i0000000000s')
    (0, b'')
    """
    _expect(packet[0] == TAG_INTEGER)
    packet = packet[1:]
    end = packet.find(TAG_END)
    _expect(end > 0)
    val = packet[:end]
    # disabled check since i0000000000s seems to be present
    # but invalid according to specification
    # _expect(val[0] != "0" or len(val) == 1)
    _expect(val[0] != "-" or val[1] != "0")
    return int(val, 16), packet[(end + 1) :]


def _decode_dict(packet):
    """
    decode a dict
    returns tuple (decoded string, rest of packet not consumed)

    >>> _decode_dict(b'h3:foo3:bars')
    ({'foo': 'bar'}, b'')
    """
    rest = packet[1:]
    d = {}

    while rest[0] != TAG_END:
        k, rest = _decode_string(rest)
        v, rest = _decode_any(rest)
        d[k] = v
    return d, rest[1:]


def _decode_list(packet):
    """
    decode a list
    returns tuple (decoded list, rest of packet not consumed)

    >>> _decode_list(b'l3:foo3:bars')
    (['foo', 'bar'], b'')
    """
    rest = packet[1:]
    result = []

    while rest[0] != TAG_END:
        item, rest = _decode_any(rest)
        result.append(item)
    return result, rest[1:]


def _decode_any(packet):
    """
    decode a token
    """
    tag = packet[0]
    if tag == TAG_INTEGER:
        return _decode_integer(packet)
    elif tag == TAG_DICT:
        return _decode_dict(packet)
    elif tag == TAG_LIST:
        return _decode_list(packet)
    else:
        return _decode_string(packet)


def _fixup(d):
    """
    Convenience method to let the protocol implementation use the key '_class'
    instead of 'class', which is a reserved word, as an argument to the dict
    constructor

    >>> _fixup(dict(a=1, _b=2)) == {'a': 1, 'b': 2}
    True
    """
    return (
        {(k[1:] if k.startswith("_") else k): v for k, v in d.items()}
        if d
        else None
    )


def _decode(**packet):
    """
    dynamic lookup of the protocol implementation
    """

    protocol = packet["protocol"]
    try:
        modname = "tellsticknet.protocols.%s" % protocol
        import importlib

        module = importlib.import_module(modname)
        func = module.decode

        # convert any _class=foo to class=foo
        packet = _fixup(func(packet.copy()))

        if packet:
            data = packet.pop("data")
            if isinstance(data, dict):
                # convert data={temp=42, humidity=38} to
                # data=[{name=temp, value=42},{name=humidity, valye=38}]
                packet["data"] = [
                    dict(name=name, value=value)
                    for name, value in data.items()
                ]
            return packet
        raise NotImplementedError
    except ImportError:
        SRC_URL = (
            "https://github.com/telldus/telldus/"
            "tree/master/telldus-core/service"
        )
        _LOGGER.exception(
            "Can not decode protocol %s, packet <%s> "
            "Missing or broken _decode in %s "
            "Check %s for protocol implementation",
            protocol,
            packet["data"],
            modname,
            SRC_URL,
        )
        raise


def encode(**device):
    protocol = device.pop("protocol")
    _LOGGER.debug("Encoding for protocol %s", protocol)
    protocol = get_protocol(protocol)
    return protocol.encode(**device)


def _decode_command(packet):
    command, rest = _decode_any(packet)
    _expect(len(rest))
    args, rest = _decode_any(rest)
    _expect(len(rest) == 0)
    _expect(isinstance(command, str))
    _expect(isinstance(args, dict))
    return command, args


def decode_packet(packet):
    """
    decode a packet

    >>> packet = "7:RawDatah5:class6:sensor8:protocol\
8:mandolyn5:model13:temperaturehumidity4:dataiAF1D466Bss"
    >>> decode_packet(packet)["data"][0]["value"]
    20.4

    >>> packet = "7:RawDatah5:class6:sensor8:protocol\
A:fineoffset4:datai488029FF9Ass"
    >>> decode_packet(packet)["data"][0]["value"]
    4.1

    packet = "7:RawDatah8:protocolC:everflourish4:dataiA1CC92ss"
    >>> decode_packet(packet)["data"][0]["value"]
    4.1

    >>> packet = "7:RawDatah8:protocolA:fineoffset2:idi98s6:valueslh\
5:scalei0s4:typei1s5:value4:16.6ss5:modelB:temperature\
4:datai4980A6FFBBs5:class6:sensors"
    >>> decode_packet(packet)["values"][0]["value"]
    '16.6'

    """

    if isinstance(packet, str):
        packet = packet.encode()

    try:
        command, args = _decode_command(packet)
    except ValueError:
        _LOGGER.error("Skipping malformed packet <%s>", packet)
        return None

    if command == "zwaveinfo":
        _LOGGER.info("Got Z-Wave info packet")
        _LOGGER.debug("%s %s", command, args)
    elif command == "RawData":
        return _decode(**args)
    else:
        raise NotImplementedError("Unknown command type")


def get_protocol(protocol):
    try:
        modname = "tellsticknet.protocols.%s" % protocol
        import importlib

        module = importlib.import_module(modname)
        return module
    except ImportError:
        SRC_URL = (
            "https://github.com/telldus/telldus/"
            "tree/master/telldus-core/service"
        )
        _LOGGER.exception(
            f"Can not decode protocol {protocol}"
            f"Check {SRC_URL} for protocol implementation"
        )
        raise
