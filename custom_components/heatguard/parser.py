"""Parse the observed RemoteGuard HTML without executing JavaScript."""
from html.parser import HTMLParser
import math
import re

FIELDS = {"id_59", "id_60", "id_61", "id_62", "id_64", "id_65", "id_66", "id_67", "id_83"}
LIMITS = {"id_61": (6, 20), "id_62": (25, 55), "id_66": (30, 60), "id_67": (30, 60)}
VOID = {"input", "br", "hr", "img", "meta", "link", "source", "wbr", "area", "base", "embed", "param", "col"}

class Node:
    def __init__(self, tag="root", attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []
    @property
    def text(self):
        return "".join(c if isinstance(c, str) else c.text for c in self.children)
    def find(self, tag=None):
        for c in self.children:
            if isinstance(c, Node):
                if tag is None or c.tag == tag:
                    yield c
                yield from c.find(tag)

class Tree(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)
    def handle_starttag(self, tag, attrs):
        n = Node(tag, attrs)
        self.stack[-1].children.append(n)
        if tag not in VOID:
            self.stack.append(n)
    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        self.stack[-1].children.append(data)

class ParseError(ValueError):
    pass

def parse_account(html, uid):
    root = Tree(html).root
    for form in root.find("form"):
        if "device_settings" not in (form.attrs.get("class") or "").split():
            continue
        inputs = list(form.find("input"))
        if not any(i.attrs.get("name") == "uid" and i.attrs.get("value") == uid for i in inputs):
            continue
        settings = {}
        for i in inputs:
            name = i.attrs.get("name")
            if name not in FIELDS:
                continue
            if i.attrs.get("type") == "radio" and "checked" not in i.attrs:
                continue
            settings[name] = i.attrs.get("value", "")
        if set(settings) != FIELDS:
            raise ParseError("RemoteGuard settings schema changed")
        validate(settings)
        telemetry = next((n for n in root.find() if n.attrs.get("id") == "vals" + uid), None)
        if telemetry is None:
            raise ParseError("Device telemetry not found")
        return {"settings": settings, **parse_telemetry(telemetry)}
    raise ParseError("Device UID not found in account")

def parse_telemetry(root):
    values = {}
    for h in root.find("h5"):
        span = next(h.find("span"), None)
        if span is not None:
            raw = span.text.strip()
            label = " ".join(h.text.removesuffix(span.text).split()).casefold()
            match = re.match(r"^\s*(-?\d+(?:[.,]\d+)?)", raw)
            values[label] = {"raw": raw, "value": float(match[1].replace(",", ".")) if match else None}
    if not values:
        raise ParseError("No telemetry values")
    times = [n.text.strip().strip("()") for n in root.find() if "device-time" in (n.attrs.get("class") or "").split()]
    return {"values": values, "device_time": times[0] if times else None}

def validate(settings):
    for name, bounds in LIMITS.items():
        v = float(settings[name])
        if not math.isfinite(v) or not bounds[0] <= v <= bounds[1] or not v.is_integer():
            raise ValueError(f"Invalid {name}: expected integer {bounds[0]}..{bounds[1]}")
    for name in ("id_59", "id_60", "id_83"):
        if settings[name] not in ("0", "1"):
            raise ValueError(f"Invalid {name}")
    for name in ("id_64", "id_65"):
        if settings[name] not in ("0", "1", "2"):
            raise ValueError(f"Invalid {name}")
