"""Looks of the office floor: the same plan and furniture, re-coloured by what each colour IS (wood, carpet, light stone, walls)
plus a few touches of the look's own (lanterns, desk lamps, neon strips)."""
import colorsys
import re

from simulation.art.floor import DESKS

THEMES = {"majlis": "🕌 مجلس سعودي"}      # the one look of the office


def _hex(r, g, b):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v * 255)))) for v in (r, g, b))


def _hls(h, l, s):
    return _hex(*colorsys.hls_to_rgb(h % 1, max(0, min(1, l)), max(0, min(1, s))))


def _kind(r, g, b):
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    if l > .86:
        return "light", h, l, s
    if s < .22 and l < .33:
        return "wall", h, l, s
    if 0.04 < h < 0.14 and s > .25:
        return "wood", h, l, s
    if s < .25 and b >= r:
        return "carpet", h, l, s
    return "other", h, l, s


def _map(theme):
    def f(m):
        c = m.group(1)
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        r, g, b = (int(c[i:i + 2], 16) / 255 for i in (0, 2, 4))
        k, h, l, s = _kind(r, g, b)
        if theme == "majlis":
            if k == "wood":
                return _hls(.07, l * .62, min(1, s * 1.1))           # dark walnut
            if k == "carpet":
                return _hls(.99, .2 + l * .35, .55)                   # burgundy carpets
            if k == "light":
                return _hls(.11, .9 + (l - .86) * .5, .45)            # cream marble
            if k == "wall":
                return _hls(.08, .22, .45)
            if k == "other" and s < .15:
                return _hls(.1, .55 + l * .3, .28)                    # warehouse concrete -> sand stone
        if theme == "modern":
            if k == "wood":
                return _hls(.095, .78 + (l - .6) * .4, .35)           # pale oak
            if k == "carpet":
                return _hls(.55, .74 + (l - .5) * .3, .08)            # light grey felt
            if k == "wall":
                return _hls(.55, .62, .06)
        if theme == "tech":
            if k == "wood":
                return _hls(.62, .26 + (l - .6) * .25, .14)           # dark polished concrete
            if k == "carpet":
                return _hls(.72, .2 + l * .2, .25)                    # deep violet carpet
            if k == "light":
                return _hls(.62, .34 + (l - .86), .12)
            if k == "wall":
                return "#0b0e14"
            if k == "other" and s < .15:
                return _hls(.62, .22 + l * .15, .1)
        if theme == "night":
            if k == "light":
                return _hls(h, l * .32, s * .6)
            return _hls(h, l * .42, s * .85)
        return "#" + c
    return f


HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
KEEP = ("#0A5654", "#fff", "#ffffff", "#1C2B2A")        # room labels stay readable


# literal colours outside the patterns: walls, the building's ground, filing cabinets (walnut with gold handles)
MAJLIS_SWAP = {"#3d454c": "#4a2f1c", "#2f363c": "#3a2a1e", "#9aa3a8": "#8a5a36", "#7d868b": "#5e3b22", "#5d666b": "#c9a227", "#e0a400": "#b8860b"}


def _recolor(svg, theme):
    """only the floors' patterns and gradients (the <defs>) are re-coloured by what they are; the furniture keeps its own colours"""
    fn = _map(theme)
    a = svg.find("<defs>")
    b = svg.find("</defs>", a)
    if a >= 0 and b > a:
        svg = svg[:a] + HEX.sub(fn, svg[a:b]) + svg[b:]
    for k, v in MAJLIS_SWAP.items():
        svg = svg.replace(k, v)
    return svg


def _recolor_all(svg, theme):
    fn = _map(theme)
    keep = {}
    for i, k in enumerate(KEEP):                          # protect the labels
        svg = svg.replace(f"fill='{k}'", f"fill='@K{i}@'")
        keep[f"@K{i}@"] = k
    svg = HEX.sub(fn, svg)
    for t, k in keep.items():
        svg = svg.replace(t, k)
    return svg


def _lanterns():
    out = ["<defs><radialGradient id='lglow' cx='.5' cy='.5' r='.5'><stop offset='0' stop-color='#ffd27a' stop-opacity='.55'/><stop offset='1' stop-color='#ffd27a' stop-opacity='0'/></radialGradient></defs>"]
    for x in range(120, 1560, 180):
        out.append(f"<circle cx='{x}' cy='365' r='70' fill='url(#lglow)'/><g filter='url(#shs)'><path d='M{x} 352 L{x + 8} 360 L{x + 8} 372 L{x} 380 L{x - 8} 372 L{x - 8} 360 Z' fill='#c9a227' stroke='#7a5a12'/>"
                   f"<circle cx='{x}' cy='366' r='4' fill='#fff3c4'/></g>")
    # eight-point star inlays on the corridor floor
    for x in range(210, 1560, 180):
        out.append(f"<g transform='translate({x},365)' opacity='.35' fill='none' stroke='#c9a227' stroke-width='2'><rect x='-14' y='-14' width='28' height='28'/><rect x='-14' y='-14' width='28' height='28' transform='rotate(45)'/></g>")
    return "".join(out)


def _desk_lamps(color="#ffd88a", op=.5, r=95):
    out = [f"<defs><radialGradient id='dlamp' cx='.5' cy='.5' r='.5'><stop offset='0' stop-color='{color}' stop-opacity='{op}'/><stop offset='1' stop-color='{color}' stop-opacity='0'/></radialGradient></defs>"]
    for kind, x, y in DESKS.values():
        out.append(f"<circle cx='{x}' cy='{y + 18}' r='{r}' fill='url(#dlamp)'/>")
    for x, y in ((1455, 190), (1420, 600), (195, 160), (245, 520), (635, 640)):
        out.append(f"<circle cx='{x}' cy='{y}' r='{r * 1.4}' fill='url(#dlamp)'/>")
    return "".join(out)


def _neon():
    return ("<g opacity='.9'><line x1='30' y1='338' x2='1570' y2='338' stroke='#22d3ee' stroke-width='3'/><line x1='30' y1='392' x2='1570' y2='392' stroke='#a855f7' stroke-width='3'/></g>"
            "<g opacity='.35' filter='url(#blur)'><line x1='30' y1='338' x2='1570' y2='338' stroke='#22d3ee' stroke-width='12'/><line x1='30' y1='392' x2='1570' y2='392' stroke='#a855f7' stroke-width='12'/></g>")


def themed(svg, theme):
    if theme not in THEMES:
        return svg
    out = _recolor(svg, theme)
    # the touches go over the floor and furniture, under the room labels (labels are the last <g filter='url(#shs)'><rect … rx='15'>)
    cut = out.rfind("<g filter='url(#shs)'>", 0, out.find("rx='15' fill='#0A5654'"))
    extra = {"majlis": _lanterns() + _desk_lamps("#ffcf70", .22, 80), "night": _desk_lamps(), "tech": _neon() + _desk_lamps("#8b5cf6", .25, 80)}.get(theme, "")
    if cut > 0:
        out = out[:cut] + extra + out[cut:]
    else:
        out += extra
    if theme == "majlis":
        out = out.replace("fill='#0A5654' opacity='.92'", "fill='#7a5a12' opacity='.95'")
    if theme == "tech":
        out = out.replace("fill='#0A5654' opacity='.92'", "fill='#6d28d9' opacity='.95'")
    return out
