#!/usr/bin/env python3
import paho.mqtt.client as mqtt
import json
import datetime


STATE_ON = "ON"
STATE_OFF = "OFF"
DOUBLE_CLICK_THRESHOLD = 1


def on_connect(client, userdata, flags, rc):
    client.subscribe([(x, 2) for x in topics])


def on_message(client, userdata, message):
    device = message.topic.split("/")[1]
    action = message.payload.decode()
    time_now = message.timestamp

    print(device, time_now, action)

    if not action.startswith("press"):
        return

    if device not in buttons:
        print(f"{device}: unknown??")
        return

    keynum = int(action[-1])

    buttons[device].press(time_now, keynum)


class Button:
    """Represents 4-key button"""

    def __init__(self, bulbs):
        assert len(bulbs) == 2
        self.bulbs = bulbs
        self.last = {}

    def press(self, timestamp, num):
        """Trigger key pressed event"""
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

    def __init__(self, idents, brightness_dimmed, brightness_bright):
        # idents is either string (single ident) or list of strings (several idents)
        assert type(idents) in (list, str)
        if isinstance(idents, str):
            idents = [idents]

        self.idents = idents
        self.brightness_dimmed = brightness_dimmed
        self.brightness_bright = brightness_bright

        if brightness_dimmed is None and brightness_bright is None:
            self.dimmable = False
        else:
            self.dimmable = True

    def set_state(self, state):
        """Set binary state (on/off)"""
        assert state in (STATE_ON, STATE_OFF)
        for ident in self.idents:
            if self.dimmable and state == STATE_ON:
                self.set_bright()  # default to bright
            else:
                client.publish("zigbee2mqtt/"+ident+"/set/state", payload=state)

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


class NordtronicRelay(Bulb):
    """Nordtronic single-channel relay

    https://www.zigbee2mqtt.io/devices/98425031.html"""

    def __init__(self, idents):
        super().__init__(idents, None, None)

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

        super().__init__(idents, None, None)
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
        case "bulb":
            brightness_dimmed = d["brightness_dimmed"] if "brightness_dimmed" in d else 60
            brightness_bright = d["brightness_bright"] if "brightness_bright" in d else 100
            inst = Bulb(idents, brightness_dimmed=brightness_dimmed, brightness_bright=brightness_bright)
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

        if "top" in config['buttons'][btn_id]:
            top = []
            for variant in config['buttons'][btn_id]["top"]:
                top.append(instance_from_yaml(variant))

        if "bottom" in config['buttons'][btn_id]:
            bottom = []
            for variant in config['buttons'][btn_id]["bottom"]:
                bottom.append(instance_from_yaml(variant))

        buttons[btn_id] = Button([top, bottom])

    topics = ["zigbee2mqtt/"+x+"/action" for x in buttons]

    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(config["server"]["hostname"])
    client.loop_forever()
