#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import datetime


STATE_ON = "ON"
STATE_OFF = "OFF"
DOUBLE_CLICK_THRESHOLD = 1
TOPIC_LIGHTMODE = "homeassistant/select/lightmode/value"
LIGHTMODE = "bright"


def on_connect(client, userdata, flags, rc):
    client.subscribe([(x, 2) for x in topics])


def on_message(client, userdata, message):
    global LIGHTMODE

    if message.topic == TOPIC_LIGHTMODE:
        LIGHTMODE = message.payload.decode()
    else:
        device = message.topic.split("/")[1]
        action = message.payload.decode()
        time_now = message.timestamp

        print(device, time_now, action)

        if device not in buttons:
            print(f"{device}: unknown??")
            return

        buttons[device].press(time_now, action)


class ZgpButton:
    """Represents 4-key Zigbee GreenPower button"""

    def __init__(self, bulbs):
        assert len(bulbs) == 2
        self.bulbs = bulbs
        self.last = {}

    def press(self, timestamp, action):
        """Trigger key pressed event"""

        if not action.startswith("press"):
            return
        num = int(action[-1])

        bulbno = 0 if num in (1, 3) else 1
        bulb = self.bulbs[bulbno]

        if bulb is None:
            return

        delta = None
        if num in self.last:
            delta = timestamp - self.last[num]

        self.last[num] = timestamp

        double_click = False

        if num in (1, 2):
            state = STATE_ON
            if delta is not None and delta < DOUBLE_CLICK_THRESHOLD:
                double_click = True

        elif num in (3, 4):
            state = STATE_OFF
            if delta is not None and delta < DOUBLE_CLICK_THRESHOLD:
                double_click = True

        else:
            print(f"press num='{num}' invalid")
            return

        if double_click:
            if state == STATE_OFF:
                for b in bulb:
                    b.set_dimmed()
            else:
                for b in bulb:
                    b.set_bright()
        else:
            for b in bulb:
                b.set_state(state)


class Bulb:
    """Represents dimmable bulb"""

    def __init__(self, idents, brightness_default, brightness_dimmed, brightness_bright):
        # idents is either string (single ident) or list of strings (several idents)
        assert type(idents) in (list, str)
        if isinstance(idents, str):
            idents = [idents]

        self._idents = idents
        self._brightness_default = brightness_default
        self._brightness_dimmed = brightness_dimmed
        self._brightness_bright = brightness_bright

        if brightness_default is None or \
           brightness_dimmed is None or \
           brightness_bright is None:
            self._dimmable = False
        else:
            self._dimmable = True

    @property
    def brightness_default(self):
        return self._brightness_default

    @property
    def brightness_dimmed(self):
        return self._brightness_dimmed

    @property
    def brightness_bright(self):
        return self._brightness_bright

    @property
    def idents(self):
        return self._idents

    @property
    def dimmable(self):
        return self._dimmable

    def set_state(self, state):
        """Set binary state (on/off)"""
        assert state in (STATE_ON, STATE_OFF)
        for ident in self.idents:
            if self.dimmable and state == STATE_ON:
                self.set_default()
            else:
                client.publish("zigbee2mqtt/"+ident+"/set/state", payload=state)

    def set_default(self):
        """Set default brightness"""
        self.set_brightness(self.brightness_default)

    def set_bright(self):
        """Set bright mode"""
        self.set_brightness(self.brightness_bright)

    def set_dimmed(self):
        """Set dimmed mode"""
        self.set_brightness(self.brightness_dimmed)

    def set_brightness(self, brightness):
        """Set brightness of bulb on scale from 0 to 100"""
        if not self.dimmable:
            return

        brightness = int(brightness * 255/100)
        print(f"set brightness {brightness}")
        for ident in self.idents:
            client.publish("zigbee2mqtt/"+ident+"/set/brightness", payload=brightness)


class NightBulb(Bulb):
    """Bulb with different brightness at night

    Same as Bulb, but changes default brightness depending on the value of
    TOPIC_LIGHTMODE. Some other entity must publish "bright", "dimmed" or
    "night" to this topic to control the behavior of a NightBulb. Use retain on
    this topic.

    """
    def __init__(self, brightness_night, **kwargs):
        super().__init__(**kwargs)
        self._brightness_night = brightness_night

    @property
    def brightness_night(self):
        return self._brightness_night

    @property
    def brightness_default(self):
        if LIGHTMODE == "bright":
            return self._brightness_default
        elif LIGHTMODE == "dimmed":
            return self.brightness_dimmed
        else:  # night
            return self.brightness_night


class NordtronicRelay(Bulb):
    """Nordtronic single-channel relay

    https://www.zigbee2mqtt.io/devices/98425031.html"""

    def __init__(self, idents):
        super().__init__(idents, None, None, None)

    def set_state(self, state):
        """Set binary state (on/off)"""
        assert state in (STATE_ON, STATE_OFF)

        for i in range(len(self.idents)):
            payload = {f"state": state}

            client.publish("zigbee2mqtt/"+self.idents[i]+"/set", payload=json.dumps(payload))


class WiserRelay(Bulb):
    """Multi-channel relay

    https://www.zigbee2mqtt.io/devices/545D6514.html"""

    def __init__(self, idents, channels, ontime=None):
        assert type(channels) in (list, int)
        if isinstance(channels, int):
            channels = [channels]

        super().__init__(idents, None, None, None)
        assert len(self.idents) == len(channels)
        self.channels = channels
        self.ontime = ontime

    def set_state(self, state):
        """Set binary state (on/off), optionally with delayed off"""
        assert state in (STATE_ON, STATE_OFF)

        for i in range(len(self.idents)):
            payload = {f"state_l{self.channels[i]}": state}
            if self.ontime is not None:
                payload["on_time"] = self.ontime

            client.publish("zigbee2mqtt/"+self.idents[i]+"/set", payload=json.dumps(payload))


def instance_from_yaml(d):
    idents = d["idents"]

    match d["type"]:
        case "bulb" | "nightbulb":
            brightness_dimmed = d["brightness_dimmed"] if "brightness_dimmed" in d else 60
            brightness_bright = d["brightness_bright"] if "brightness_bright" in d else 100
            brightness_default = d["brightness_default"] if "brightness_default" in d else brightness_bright
            kwargs = {"idents": idents,
                      "brightness_default": brightness_default,
                      "brightness_dimmed": brightness_dimmed,
                      "brightness_bright": brightness_bright}
            if d["type"] == "bulb":
                inst = Bulb(**kwargs)
            else:
                brightness_night = d["brightness_night"] if "brightness_night" in d else 1
                inst = NightBulb(brightness_night, **kwargs)
        case "wiserrelay":
            ontime = d["ontime"] if "ontime" in d else None
            inst = WiserRelay(idents=[x["name"] for x in idents],
                              channels=[x["channel"] for x in idents],
                              ontime=ontime)
        case "nordtronicrelay":
            inst = NordtronicRelay(idents)
        case _:
            inst = None

    return inst


if __name__ == "__main__":
    import yaml
    config = yaml.safe_load(open("cfg/config.yaml"))

    buttons = {}
    for btn_id in config['buttons']:
        top = None
        bottom = None
        btnclass = ZgpButton

        if "type" in config["buttons"][btn_id]:
            match config["buttons"][btn_id]["type"]:
                case "ZGP":
                    btnclass = ZgpButton
                case _:
                    print(f"Skipped unknown button type {config['buttons'][btn_id]['type']}")

        if "top" in config['buttons'][btn_id]:
            top = []
            for variant in config['buttons'][btn_id]["top"]:
                top.append(instance_from_yaml(variant))

        if "bottom" in config['buttons'][btn_id]:
            bottom = []
            for variant in config['buttons'][btn_id]["bottom"]:
                bottom.append(instance_from_yaml(variant))

        buttons[btn_id] = btnclass([top, bottom])

    topics = ["zigbee2mqtt/"+x+"/action" for x in buttons]
    topics.append(TOPIC_LIGHTMODE)

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(config["server"]["hostname"])
    client.loop_forever()
