[![Build Status](https://travis-ci.org/molobrakos/tellsticknet.svg?branch=master)](https://travis-ci.org/molobrakos/tellsticknet)

Interface with a Tellstick Net device on the local network bypassing the Telldus Live cloud service (events are still passed through the Telldus Live cloud service).

Use cases
- The Tellstick Net device is on a poor connection, such as a mobile broadband subscription in the summer house
- Archival of sensor readings
- Faster sensor updates than from the Telldus live service
- Instant updates for sensors such as door sensors.

There is no support for local access to Tellstick Net in the [telldus-core][1] or [tellcore][2] libraries. This Python implementation tries to fill the gap. Unfortunately, the [Protocol::decodeData method][3] is not exposed in the telldus-core library, so the protocol parsing is reimplemented in Python.
    
[1]: https://github.com/telldus/telldus/search?utf8=%E2%9C%93&q=TELLSTICK_CONTROLLER_TELLSTICK_NET
[2]: https://github.com/erijo/tellcore-py
[3]: https://github.com/telldus/telldus/blob/master/telldus-core/service/Protocol.cpp#L216

Examples:

Discovery
```bash
> ./script/discover # (or python3 -m tellsticknet.discover)
[('192.168.1.106', ['TellStickNet', '<MAC>', '<CODE>', '17'])]
```

Listen for received packets and print parsed values
```bash
> ./script/listen 2>/dev/null # or python3 -m tellsticknet
{'model': 'temperaturehumidity', 'data': {'humidity': 31, 'temp': 18.1}, 'lastUpdated': 1459502928, 'sensorId': 104, 'protocol': 'mandolyn', 'class': 'sensor'}
{'model': 'temperaturehumidity', 'data': {'humidity': 34, 'temp': 16.7}, 'lastUpdated': 1459503006, 'sensorId': 135, 'protocol': 'fineoffset', 'class': 'sensor'}
(...)
```

Listen for raw packets and dump to file
```bash
> ./script/listen raw 2>/dev/null | tee packets.log
2016-04-01T11:39:15 7:RawDatah5:class6:sensor8:protocolA:fineoffset4:datai41B03B4DAAss
2016-04-01T11:39:17 7:RawDatah5:class6:sensor8:protocol8:mandolyn5:model13:temperaturehumidity4:datai13413986ss
(...)
```

Parse previously dumped packets
```bash
> cat packets.log | ./script/parse
{"class": "sensor", "data": {"temp": 5.9, "humidity": 77}, "model": "temperaturehumidity", "sensorId": 27, "lastUpdated": 1459503555, "protocol": "fineoffset"}
{"class": "sensor", "data": {"temp": 7.5, "humidity": 65}, "model": "temperaturehumidity", "sensorId": 11, "lastUpdated": 1459503557, "protocol": "mandolyn"}
(...)

```
Display all sensors
```bash
> cat packets.log | ./script/parse | jq ".sensorId" | sort -n | uniq
11
27
135
(...)
```

Export temperature readings as csv
```bash
> cat packets.log | ./script/parse | jq '[.sensorId, .lastUpdated, .data["temp"]] | @csv'
"136,1459504835,3.6"
"104,1459504848,18.6"
(...)
```

Archive all packets, one file per day
```bash
> ./script/dump | tee >(cronolog packets.%Y-%m-%d.log)
```

Start MQTT gateway, forwarding all sensor readings to a MQTT server (where Home Assistant can be a subscriber), also receive any commands from the server (e.g. from Home Assistant)
```bash
> ./script/tellsticknet mqtt -vv
```
