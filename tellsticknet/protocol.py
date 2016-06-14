"""
encode/and decode protocol as described in
https://developer.telldus.com/doxygen/html/TellStickNet.html
"""

import logging
from collections import OrderedDict
_LOGGER = logging.getLogger(__name__)


TAG_INTEGER = "i"
TAG_DICT = "h"
TAG_LIST = "l"
TAG_END = "s"
TAG_SEP = ":"


def _expect(condition):
    if not condition:
        raise RuntimeError()


def _encode_string(s):
    """
    encode a string

    >>> _encode_string("hello")
    '5:hello'

    >>> _encode_string("hellothere")
    'a:hellothere'

    >>> _encode_string("")
    '0:'

    >>> _encode_string(4711)
    Traceback (most recent call last):
        ...
    TypeError: object of type 'int' has no len()
    """
    return "%x%s%s" % (len(s), TAG_SEP, s)


def _encode_integer(d):
    """
    encode a integer

    >>> _encode_integer(42)
    'i2as'

    >>> _encode_integer(-42)
    'i-2as'

    >>> _encode_integer(0)
    'i0s'

    >>> _encode_integer(3.3)
    'i3s'
    """
    return "%s%x%s" % (TAG_INTEGER, d, TAG_END)


def _encode_dict(d):
    """
    encode a dict

    >>> _encode_dict({"foo": "bar", "baz": 42})
    'h3:bazi2as3:foo3:bars'

    >>> _encode_dict({})
    'hs'

    >>> _encode_dict([])
    Traceback (most recent call last):
        ...
    RuntimeError

    >>> _encode_dict(None)
    Traceback (most recent call last):
        ...
    RuntimeError
    """
    _expect(isinstance(d, dict))
    d = OrderedDict(sorted(d.items()))  # deterministic (for testing)
    return "%s%s%s" % (
        TAG_DICT,
        "".join(_encode_any(x)
                for keyval in d.items()
                for x in keyval),
        TAG_END)


def _encode_list(l):
    raise NotImplementedError()


def _encode_any(t):
    if isinstance(t, int):
        return _encode_integer(t)
    elif isinstance(t, str):
        return _encode_string(t)
    elif isinstance(t, dict):
        return _encode_dict(t)
    elif isinstance(t, list):
        return _encode_list(t)
    else:
        raise NotImplementedError()


def encode_packet(command, **args):
    """
    encode a packet

    >>> encode_packet("hello", foo="x")
    b'5:helloh3:foo1:xs'
    """
    res = _encode_string(command)
    if args:
        res += _encode_dict(args)
    return res.encode("ascii")


def _decode_string(packet):
    """
    decode a string
    returns tuple (decoded string, rest of packet not consumed)

    >>> _decode_string("5:hello")
    ('hello', '')

    >>> _decode_string("5:hell")
    Traceback (most recent call last):
        ...
    RuntimeError

    >>> _decode_string("hello")
    Traceback (most recent call last):
        ...
    RuntimeError
    """
    sep = packet.find(TAG_SEP)
    _expect(sep > 0)
    length = packet[:sep]
    length = int(length, 16)
    start = len(TAG_SEP) + sep
    end = start + length
    _expect(end <= len(packet))
    val = packet[start:end]
    return val, packet[end:]


def _decode_integer(packet):
    """
    decode an integer
    returns tuple (decoded integer, rest of packet not consumed)

    >>> _decode_integer("i4711s")
    (18193, '')
    """
    _expect(packet[0] == TAG_INTEGER)
    packet = packet[len(TAG_INTEGER):]
    end = packet.find(TAG_END)
    _expect(end > 1)
    val = packet[:end]
    return int(val, 16), packet[end + len(TAG_END):]


def _decode_dict(packet):
    """
    decode a dict
    returns tuple (decoded string, rest of packet not consumed)

    >>> _decode_dict("h3:foo3:bars")
    ({'foo': 'bar'}, '')
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

    """
    raise NotImplementedError()


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


def _decode_protocoldata(protocol, data):
    """
    dynamic lookup of the protocol implementation
    """
    import importlib
    try:
        modname = "tellsticknet.protocols.%s" % protocol
        module = importlib.import_module(modname)
        func = getattr(module, "decode")
        return func(data)
    except:
        SRC_URL = ("https://github.com/telldus/telldus/"
                   "tree/master/telldus-core/service")
        _LOGGER.error("Can not decode protocol %s, packet <%s> "
                      "Missing or broken _decode in %s "
                      "Check %s for protocol implementation",
                      protocol, data,
                      modname, SRC_URL)
        return dict()


def _decode_command(packet):
    command, rest = _decode_any(packet)
    args, rest = _decode_any(rest)
    _expect(len(rest) == 0)
    _expect(isinstance(command, str))
    _expect(isinstance(args, dict))
    return command, args


def decode_packet(packet, **add_attrs):
    """
    decode a packet

    >>> packet = b"7:RawDatah5:class6:sensor8:protocol\
    8:mandolyn5:model13:temperaturehumidity4:dataiAF1D466Bss"
    >>> decode_packet(packet)["data"]["temp"]
    20.4

    >>> packet = b"7:RawDatah5:class6:sensor8:protocol\
    A:fineoffset4:datai488029FF9Ass"
    >>> decode_packet(packet)["data"]["temp"]
    4.1
    """

    if isinstance(packet, bytes):
        packet = packet.decode("ascii")

    try:
        command, args = _decode_command(packet)
        if command != "RawData":
            raise NotImplementedError()
        protocol = args["protocol"]
        data = args["data"]
        data = _decode_protocoldata(protocol, data)
    except:
        return None

    args.update(data)
    args.update(add_attrs)

    return args
