#!/usr/bin/env python3
"""Build the Stream Deck MK.2 "Home" page for peecee.

Writes ./sdpage/manifest.json, ./sdpage/Images/*.png, ./sdpage/back-action.json
and ./sd-preview.png. Webhook IDs are <prefix>-<key>; the private prefix is read
from ~/.config/streamdeck-peecee/webhook-prefix on proximal and never committed.
Needs Pillow and the FontAwesome 4 webfont (fonts-font-awesome).
"""
import json, os, random, string, uuid
from PIL import Image, ImageDraw, ImageFont

FONT = '/usr/share/fonts/truetype/font-awesome/fontawesome-webfont.ttf'
FA, FA2 = ImageFont.truetype(FONT, 62), ImageFont.truetype(FONT, 46)
PREFIX = open(os.path.expanduser('~/.config/streamdeck-peecee/webhook-prefix')).read().strip()
HA = 'http://192.168.1.64:8123/api/webhook/'
PAGES = {"Plugin": {"Name": "Pages", "UUID": "com.elgato.streamdeck.page", "Version": "1.0"}}
os.makedirs('sdpage/Images', exist_ok=True)


def grad(c1, c2):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    im = Image.new('RGB', (144, 144))
    px = im.load()
    for y in range(144):
        for x in range(144):
            t = (x + y) / 286
            px[x, y] = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
    return im


def icon(glyph, c1, c2, font=FA):
    im = grad(c1, c2)
    ImageDraw.Draw(im).text((72, 58), glyph, font=font, fill='white', anchor='mm')
    name = 'Images/' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=26)) + 'Z.png'
    im.save('sdpage/' + name)
    return name


def act(name, uuid_, settings, img, title, extra=None):
    state = {"FontFamily": "", "FontSize": 11, "FontStyle": "", "FontUnderline": False, "Image": img,
             "OutlineThickness": 2, "ShowTitle": True, "Title": title, "TitleAlignment": "bottom",
             "TitleColor": "#ffffff"}
    a = {"ActionID": str(uuid.uuid4()), "LinkedTitle": False, "Name": name, "Resources": None,
         "Settings": settings, "State": 0, "States": [state], "UUID": uuid_}
    a.update(extra or {})
    return a


def hook(key, glyph, c1, c2, title, font=FA):
    # openInBrowser false = the Website action's "GET request in background"
    return act("Website", "com.elgato.streamdeck.system.website",
               {"openInBrowser": False, "path": HA + PREFIX + "-" + key}, icon(glyph, c1, c2, font), title)


MEDIA = "com.elgato.streamdeck.system.multimedia"  # actionIdx: 0 play/pause, 4 mute, 5 vol+, 6 vol-
A = {
    "0,0": hook("desk-lamp", "\uf0eb", "#f7b733", "#fc4a1a", "Desk Lamp"),
    "1,0": hook("bedroom-lamp", "\uf236", "#f6d365", "#fda085", "Bed Lamp"),
    "2,0": hook("red-light", "\uf0eb", "#ff416c", "#b31217", "Red Light"),
    "3,0": hook("hall-light", "\uf0eb", "#36d1dc", "#5b86e5", "Hall Light"),
    "4,0": hook("living-room-off", "\uf011", "#606c88", "#1f1f1f", "Living Off"),
    "0,1": hook("dinner", "\uf0f5", "#56ab2f", "#a8e063", "Dinner"),
    "1,1": hook("bedtime", "\uf252", "#654ea3", "#da98b4", "Bedtime"),
    "2,1": hook("come-here", "\uf0a1", "#ee0979", "#ff6a00", "Come Here"),
    "3,1": hook("movie-mode", "\uf008", "#8e2de2", "#4a00e0", "Movie"),
    "4,1": hook("goodnight", "\uf186", "#141e30", "#3a5a8c", "Goodnight"),
    "0,2": act("Multimedia", MEDIA, {"actionIdx": 0}, icon("\uf04b\uf04c", "#11998e", "#38ef7d", FA2), "Play/Pause"),
    "1,2": act("Multimedia", MEDIA, {"actionIdx": 4}, icon("\uf026", "#b24592", "#f15f79"), "Mute"),
    "2,2": act("Website", "com.elgato.streamdeck.system.website",
               {"openInBrowser": True, "path": "http://100.85.100.81:3003/"},
               icon("\uf201", "#f12711", "#f5af19"), "Grafana"),
    "3,2": act("Open", "com.elgato.streamdeck.system.open",
               {"path": "\"C:\\ProgramData\\Infra\\streamdeck\\Lock peecee.lnk\""},
               icon("\uf023", "#232526", "#5a5f63"), "Lock PC"),
    "4,2": act("Next Page", "com.elgato.streamdeck.page.next", {},
               icon("\uf141", "#434343", "#7a7a7a"), "More ›", PAGES),
}
json.dump({"Controllers": [{"Actions": A, "Type": "Keypad"}], "Icon": "", "Name": "Home"},
          open('sdpage/manifest.json', 'w'), ensure_ascii=False)
json.dump(act("Previous Page", "com.elgato.streamdeck.page.previous", {},
              icon("\uf053", "#434343", "#7a7a7a"), "‹ Home", PAGES),
          open('sdpage/back-action.json', 'w'), ensure_ascii=False)
sheet = Image.new('RGB', (750, 450), 'black')
for k, a in A.items():
    c, r = map(int, k.split(','))
    sheet.paste(Image.open('sdpage/' + a["States"][0]["Image"]), (c * 150, r * 150))
sheet.save('sd-preview.png')
