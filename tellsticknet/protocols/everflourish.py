import logging
_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/95f93cd6d316a910c5d4d2d518f772e43b7caa20/telldus-core/tests/service/ProtocolEverflourishTest.cpp
# CPPUNIT_ASSERT_EQUAL_MESSAGE(
#    "Everflourish 4242:3 ON",
#    std::string("class:command;protocol:everflourish;model:selflearning;house:4242;unit:3;method:turnon;"),
#    d->protocol->decodeData(ControllerMessage("protocol:everflourish;data:0x424A6F;"))
# );
# CPPUNIT_ASSERT_EQUAL_MESSAGE(
#    "Everflourish 5353:4 OFF",
#    std::string("class:command;protocol:everflourish;model:selflearning;house:5353;unit:4;method:turnoff;"),
#    d->protocol->decodeData(ControllerMessage("protocol:everflourish;data:0x53A7E0;"))


def decode(data, args):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """

    house = data & 0xFFFC00
    house >>= 10

    unit = data & 0x300
    unit >>= 8
    unit += 1

    method = data & 0xF

    if house > 16383 or unit < 1 or unit > 4:
        # not everflourish
        return None

    if method == 0:
        method = "turnoff"
    elif method == 15:
        method = "turnon"
    elif method == 10:
        method = "learn"
    else:
        raise RuntimeError("invalid method", method)

    return dict(_class="command",
                model="selflearning",
                house=house,
                unit=unit,
                method=method)


def encode(method):
    """
    https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolEverflourish.cpp
    """
    raise NotImplementedError()
