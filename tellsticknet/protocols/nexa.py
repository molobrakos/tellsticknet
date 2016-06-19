import logging
_LOGGER = logging.getLogger(__name__)

# https://github.com/telldus/telldus/blob/master/telldus-core/service/ProtocolNexa.cpp

def decode_selflearning(data, args):
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

lastArctecCodeSwitchWasTurnOff = False


def decode_codeswitch(data, args):

    # print("data %x" % data)
    method = data & 0xF00
    # print("%x" % method)
    method >>= 8
    # print("%x" % method)

    unit = data & 0xF0
    unit >>= 4
    unit += 1

    house = data & 0xF
    # print(house, unit)
    if house > 16 or unit < 1 or unit > 16:
        # not arctech codeswitch
        _LOGGER.debug("Not Arctech")
        return

    house = chr(house + ord('A'))  # house from A to P
    # print(house)
    global lastArctecCodeSwitchWasTurnOff
    # print(method)

    if method != 6 and lastArctecCodeSwitchWasTurnOff:
        lastArctecCodeSwitchWasTurnOff = False
        # probably a stray turnon or bell
        # (perhaps: only certain time interval since last,
        # check that it's the same house/unit
        # Will lose one turnon/bell, but it's better than the alternative...
        return

    if method == 6:
        lastArctecCodeSwitchWasTurnOff = True

    ret = dict(_class="command",
               protocol="arctech",
               model="codeswitch",
               house=house)

    if method == 6:
        ret.update(unit=unit,
                   method="turnoff")
    elif method == 14:
        ret.update(unit=unit,
                   method="turnon")
    elif method == 15:
        ret.update(method="bell")
    else:
        _LOGGER.debug("Not Arctech")
        # not arctech codeswitch
        return

    return ret


def decode(data, args):
    if args["model"] == "selflearning":
        return decode_selflearning(data, args)
    elif args["model"] == "codeswitch":
        return decode_codeswitch(data, args)
    else:
        raise NotImplementedError()


# tests from https://github.com/telldus/telldus/blob/
# 95f93cd6d316a910c5d4d2d518f772e43b7caa20/telldus-core/tests/service/ProtocolNexaTest.cpp
# CPPUNIT_ASSERT_EQUAL_MESSAGE(
# "Arctech Codeswitch A1 ON",
# std::string("class:command;protocol:arctech;model:codeswitch;house:A;unit:1;method:turnon;"),
#  d->protocol->decodeData(ControllerMessage("protocol:arctech;model:codeswitch;data:0xE00;"))
#      );
# 	CPPUNIT_ASSERT_EQUAL_MESSAGE(
# 		"Arctech Codeswitch A1 OFF",
# 		std::string("class:command;protocol:arctech;model:codeswitch;house:A;unit:1;method:turnoff;"),
# 		d->protocol->decodeData(ControllerMessage("protocol:arctech;model:codeswitch;data:0x600;"))
# 	);
# 	CPPUNIT_ASSERT_EQUAL_MESSAGE(
# 		"Arctech Selflearning 1329110 1 ON",
# 		std::string("class:command;protocol:arctech;model:selflearning;house:1329110;unit:1;group:0;method:turnon;"),
# 		d->protocol->decodeData(ControllerMessage("protocol:arctech;model:selflearning;data:0x511F590;")#)
# 	);
# 	CPPUNIT_ASSERT_EQUAL_MESSAGE(
# 		"Arctech Selflearning 1329110 1 OFF",
# 		std::string("class:command;protocol:arctech;model:selflearning;house:1329110;unit:1;group:0;method:turnoff;"),
# 		d->protocol->decodeData(ControllerMessage("protocol:arctech;model:selflearning;data:0x511F580;")#)
# 	);
