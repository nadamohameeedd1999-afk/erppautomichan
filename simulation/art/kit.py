"""Detailed SVG kit: floors, walls, furniture and people seen from above (office floor plan)."""
import math
import random

R = random.Random(7)

DEFS = """
<defs>
 <filter id='sh' x='-30%' y='-30%' width='160%' height='160%'><feDropShadow dx='3' dy='5' stdDeviation='4' flood-color='#000' flood-opacity='.28'/></filter>
 <filter id='shs' x='-30%' y='-30%' width='160%' height='160%'><feDropShadow dx='1.5' dy='2.5' stdDeviation='2' flood-color='#000' flood-opacity='.3'/></filter>
 <filter id='blur'><feGaussianBlur stdDeviation='6'/></filter>
 <pattern id='wood' width='240' height='96' patternUnits='userSpaceOnUse'>
  <rect width='240' height='96' fill='#d9b98f'/>
  <rect y='0' width='130' height='16' fill='#dcbd94'/><rect x='130' y='0' width='110' height='16' fill='#d3b083'/>
  <rect y='16' width='70' height='16' fill='#cfab7d'/><rect x='70' y='16' width='170' height='16' fill='#dec199'/>
  <rect y='32' width='160' height='16' fill='#d6b488'/><rect x='160' y='32' width='80' height='16' fill='#cca779'/>
  <rect y='48' width='40' height='16' fill='#dcbe95'/><rect x='40' y='48' width='150' height='16' fill='#d2ae80'/><rect x='190' y='48' width='50' height='16' fill='#dfc29b'/>
  <rect y='64' width='110' height='16' fill='#d0ac7e'/><rect x='110' y='64' width='130' height='16' fill='#d9ba90'/>
  <rect y='80' width='190' height='16' fill='#dbbc93'/><rect x='190' y='80' width='50' height='16' fill='#cda97b'/>
  <g stroke='#b8925f' stroke-opacity='.45' stroke-width='1'><path d='M0 16H240M0 32H240M0 48H240M0 64H240M0 80H240M0 96H240'/>
  <path d='M130 0V16M70 16V32M160 32V48M40 48V64M190 48V64M110 64V80M190 80V96'/></g>
  <g stroke='#a77f4f' stroke-opacity='.18'><path d='M10 8 C60 6 90 10 125 8M80 24 C130 22 180 27 235 24M20 40 C70 38 120 43 155 40M50 56 C90 54 140 58 185 56M5 72 C40 70 80 74 105 72M120 72 C160 70 200 74 235 72M10 88 C70 86 120 90 185 88'/></g>
 </pattern>
 <pattern id='carpet' width='60' height='60' patternUnits='userSpaceOnUse'>
  <rect width='60' height='60' fill='#8e9aa6'/><rect width='30' height='30' fill='#8a96a2'/><rect x='30' y='30' width='30' height='30' fill='#8a96a2'/>
  <g fill='#7f8b97' opacity='.5'><circle cx='7' cy='9' r='.9'/><circle cx='22' cy='17' r='.9'/><circle cx='41' cy='6' r='.9'/><circle cx='52' cy='44' r='.9'/><circle cx='14' cy='48' r='.9'/><circle cx='36' cy='37' r='.9'/></g>
 </pattern>
 <pattern id='carpet2' width='60' height='60' patternUnits='userSpaceOnUse'><rect width='60' height='60' fill='#6f7f8c'/><rect width='30' height='30' fill='#6b7b88'/><rect x='30' y='30' width='30' height='30' fill='#6b7b88'/></pattern>
 <pattern id='tile' width='80' height='80' patternUnits='userSpaceOnUse'>
  <rect width='80' height='80' fill='#ecebe7'/><rect width='40' height='40' fill='#f1f0ec'/><rect x='40' y='40' width='40' height='40' fill='#f1f0ec'/>
  <path d='M0 40H80M40 0V80' stroke='#d6d4cd' stroke-width='1.2'/><path d='M10 25 C25 20 30 32 38 28' stroke='#d8d6cf' fill='none'/>
 </pattern>
 <pattern id='concrete' width='100' height='100' patternUnits='userSpaceOnUse'>
  <rect width='100' height='100' fill='#c9cbc8'/><g fill='#bfc1be' opacity='.7'><circle cx='12' cy='20' r='2'/><circle cx='70' cy='14' r='1.5'/><circle cx='40' cy='60' r='2.5'/><circle cx='85' cy='80' r='1.6'/><circle cx='20' cy='85' r='1.2'/></g>
  <path d='M0 100H100V0' stroke='#b5b7b4' fill='none'/>
 </pattern>
 <pattern id='rug' width='16' height='16' patternUnits='userSpaceOnUse'><rect width='16' height='16' fill='#8c3b3b'/><path d='M0 8L8 0L16 8L8 16Z' fill='#9c4a45'/><circle cx='8' cy='8' r='2' fill='#c9a86a'/></pattern>
 <linearGradient id='deskW' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#f3efe8'/><stop offset='1' stop-color='#ddd6cb'/></linearGradient>
 <linearGradient id='deskD' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#6d4a2f'/><stop offset='.5' stop-color='#5a3b24'/><stop offset='1' stop-color='#4a2f1c'/></linearGradient>
 <linearGradient id='deskO' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#d6b58a'/><stop offset='1' stop-color='#b99266'/></linearGradient>
 <radialGradient id='chair' cx='.45' cy='.4' r='.7'><stop offset='0' stop-color='#4b525a'/><stop offset='1' stop-color='#23272c'/></radialGradient>
 <radialGradient id='leather' cx='.45' cy='.4' r='.7'><stop offset='0' stop-color='#6b4a33'/><stop offset='1' stop-color='#3b2416'/></radialGradient>
 <linearGradient id='glass' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#cfe7f3' stop-opacity='.9'/><stop offset='1' stop-color='#a9d0e4' stop-opacity='.9'/></linearGradient>
 <radialGradient id='sun' cx='.5' cy='0' r='1'><stop offset='0' stop-color='#fff8d6' stop-opacity='.55'/><stop offset='1' stop-color='#fff8d6' stop-opacity='0'/></radialGradient>
 <radialGradient id='leaf' cx='.4' cy='.35' r='.8'><stop offset='0' stop-color='#8cc48a'/><stop offset='1' stop-color='#3f7a45'/></radialGradient>
 <linearGradient id='sofa' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#7d8f9c'/><stop offset='1' stop-color='#5c6e7b'/></linearGradient>
 <linearGradient id='box' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='#d8b07a'/><stop offset='1' stop-color='#b98d55'/></linearGradient>
 <pattern id='shemagh' width='6' height='6' patternUnits='userSpaceOnUse'><rect width='6' height='6' fill='#fbfbfa'/><path d='M0 0L3 3L0 6M3 0L6 3L3 6' stroke='#c0392b' stroke-width='.9' fill='none'/></pattern>
</defs>"""


def shade(hexc, f):
    hexc = hexc.lstrip("#")
    r, g, b = (int(hexc[i:i + 2], 16) for i in (0, 2, 4))
    if f < 0:
        r, g, b = (int(c * (1 + f)) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * f) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


_gid = [0]


def grad(c1, c2, kind="lin"):
    _gid[0] += 1
    gid = f"g{_gid[0]}"
    if kind == "rad":
        return gid, f"<radialGradient id='{gid}' cx='.45' cy='.35' r='.75'><stop offset='0' stop-color='{c1}'/><stop offset='1' stop-color='{c2}'/></radialGradient>"
    return gid, f"<linearGradient id='{gid}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{c1}'/><stop offset='1' stop-color='{c2}'/></linearGradient>"


# ------------------------------------------------------------------ building
def floor(x, y, w, h, fill):
    return f"<rect x='{x}' y='{y}' width='{w}' height='{h}' fill='{fill}'/>"


def walls(segs, t=10, color="#3d454c"):
    return "".join(f"<line x1='{a}' y1='{b}' x2='{c}' y2='{d}' stroke='{color}' stroke-width='{t}' stroke-linecap='square'/>" for a, b, c, d in segs)


def glass_wall(x1, y1, x2, y2):
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='#9cc3d6' stroke-width='6' opacity='.85'/>"
            f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='#e9f6fc' stroke-width='1.5' opacity='.9'/>")


def window(x1, y1, x2, y2):
    out = f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' stroke='#bfe0ef' stroke-width='9'/>"
    n = max(1, int(math.hypot(x2 - x1, y2 - y1) // 60))
    for i in range(1, n):
        px, py = x1 + (x2 - x1) * i / n, y1 + (y2 - y1) * i / n
        out += f"<circle cx='{px}' cy='{py}' r='3.5' fill='#3d454c'/>"
    return out


def door(x, y, r=34, rot=0):
    return (f"<g transform='translate({x},{y}) rotate({rot})'><path d='M0 0 L{r} 0 A{r} {r} 0 0 0 0 {r} Z' fill='#f6f2ea' opacity='.35'/>"
            f"<path d='M{r} 0 A{r} {r} 0 0 0 0 {r}' fill='none' stroke='#8d8d8d' stroke-width='1' stroke-dasharray='3 3'/>"
            f"<line x1='0' y1='0' x2='0' y2='{r}' stroke='#7a5c3e' stroke-width='4'/></g>")


def sunlight(x, y, w, h):
    return f"<rect x='{x}' y='{y}' width='{w}' height='{h}' fill='url(#sun)'/>"


def label(x, y, text):
    w = len(text) * 9 + 30
    return (f"<g filter='url(#shs)'><rect x='{x - w / 2}' y='{y - 15}' width='{w}' height='30' rx='15' fill='#0A5654' opacity='.92'/></g>"
            f"<text x='{x}' y='{y + 5}' text-anchor='middle' font-size='14' font-weight='800' fill='#fff'>{text}</text>")


# ------------------------------------------------------------------ furniture
def plant(x, y, r=22, pot="#e8e4dc"):
    leaves = ""
    for i in range(9):
        a = i * 40 + R.uniform(-12, 12)
        L = r * R.uniform(.75, 1.05)
        leaves += (f"<ellipse cx='{L * .5 * math.cos(math.radians(a)):.1f}' cy='{L * .5 * math.sin(math.radians(a)):.1f}' rx='{L * .55:.1f}' ry='{L * .22:.1f}' "
                   f"transform='rotate({a:.0f} {L * .5 * math.cos(math.radians(a)):.1f} {L * .5 * math.sin(math.radians(a)):.1f})' fill='url(#leaf)' stroke='#2f5e35' stroke-width='.6'/>")
    return (f"<g transform='translate({x},{y})' filter='url(#sh)'><circle r='{r * .55}' fill='{pot}' stroke='#c9c3b8'/><circle r='{r * .45}' fill='#5b4636'/>"
            f"{leaves}<circle r='{r * .18}' fill='#5f9c5e'/></g>")


def office_chair(x, y, rot=0, color="url(#chair)"):
    arms = "<rect x='-19' y='-8' width='5' height='18' rx='2.5' fill='#1d2125'/><rect x='14' y='-8' width='5' height='18' rx='2.5' fill='#1d2125'/>"
    return (f"<g transform='translate({x},{y}) rotate({rot})' filter='url(#shs)'>"
            + "".join(f"<line x1='0' y1='0' x2='{20 * math.cos(math.radians(a)):.1f}' y2='{20 * math.sin(math.radians(a)):.1f}' stroke='#2a2e33' stroke-width='3'/>" for a in range(18, 378, 72))
            + f"<rect x='-15' y='-14' width='30' height='28' rx='9' fill='{color}'/>{arms}<path d='M-17 13 Q0 24 17 13 L15 19 Q0 28 -15 19 Z' fill='#1b1f23'/></g>")


def monitor(x, y, rot=0, scr="#0F7C7A", w=46):
    return (f"<g transform='translate({x},{y}) rotate({rot})'><rect x='{-w / 2}' y='-4' width='{w}' height='7' rx='2' fill='#16191c'/>"
            f"<rect x='{-w / 2 + 2}' y='-3' width='{w - 4}' height='3' rx='1' fill='{scr}' opacity='.9'/><rect x='-5' y='3' width='10' height='6' fill='#2a2e33'/>"
            f"<ellipse cy='10' rx='9' ry='4' fill='#2a2e33'/></g>")


def keyboard(x, y, rot=0):
    keys = "".join(f"<rect x='{-16 + i * 3.3:.1f}' y='{-3 + j * 2.6:.1f}' width='2.6' height='1.9' rx='.4' fill='#d9d9d6'/>" for i in range(10) for j in range(3))
    return f"<g transform='translate({x},{y}) rotate({rot})'><rect x='-18' y='-5' width='36' height='10' rx='2' fill='#f4f4f1' stroke='#cfcfca'/>{keys}</g>"


def workstation(x, y, rot=0, scr="#0F7C7A", top="url(#deskW)", w=120, d=62, items=True, chair=True):
    """a desk seen from above; the person sits at +y side (bottom) facing up"""
    inner = (f"<rect x='{-w / 2}' y='{-d / 2}' width='{w}' height='{d}' rx='4' fill='{top}' stroke='#bdb4a6' filter='url(#sh)'/>"
             f"<rect x='{-w / 2}' y='{-d / 2}' width='{w}' height='4' fill='#b9b0a2' opacity='.6'/>")
    inner += monitor(0, -d / 2 + 12, 0, scr) + keyboard(0, 6)
    if items:
        inner += (f"<ellipse cx='26' cy='9' rx='4' ry='5.5' fill='#f2f2ef' stroke='#ccc'/>"
                  f"<g transform='translate({-w / 2 + 16},{-6}) rotate(-8)'><rect x='-11' y='-14' width='22' height='29' fill='#fff' stroke='#d6d6d0'/><path d='M-7 -8H7M-7 -3H7M-7 2H4' stroke='#c9c9c3'/></g>"
                  f"<g transform='translate({w / 2 - 16},{-d / 2 + 14})'><circle r='6.5' fill='#fff' stroke='#bbb'/><circle r='4.5' fill='#6b3e22'/></g>"
                  f"<g transform='translate({w / 2 - 22},10)'><rect x='-7' y='-10' width='14' height='20' rx='2' fill='#2d3236'/><rect x='-5' y='-8' width='10' height='9' fill='#4a8fb0' opacity='.7'/></g>")
    out = f"<g transform='translate({x},{y}) rotate({rot})'>{inner}"
    if chair:
        out += office_chair(0, d / 2 + 18, 180)
    return out + "</g>"


def exec_desk(x, y):
    return (f"<g transform='translate({x},{y})'><path d='M-90 -38 H90 V38 H40 V18 H-90 Z' fill='url(#deskD)' stroke='#3a2414' filter='url(#sh)'/>"
            + monitor(-10, -26, 0, "#0F7C7A", 54) + keyboard(-10, -4) +
            "<rect x='40' y='-30' width='34' height='24' rx='2' fill='#2b2f33'/><rect x='42' y='-28' width='30' height='18' fill='#3f6f86' opacity='.8'/>"
            "<g transform='translate(-70,-20)'><circle r='8' fill='#c9a86a'/><circle r='5' fill='#f7e7b4'/></g><rect x='-75' y='0' width='26' height='14' rx='2' fill='#f5f1e8' stroke='#ccc'/>"
            "</g>" + office_chair(x - 10, y + 52, 180, "url(#leather)"))


def sofa(x, y, w=150, rot=0, color="url(#sofa)"):
    cush = "".join(f"<rect x='{-w / 2 + 12 + i * (w - 24) / 3:.1f}' y='-8' width='{(w - 24) / 3 - 4:.1f}' height='26' rx='6' fill='#8fa1ad' stroke='#6c7e8a'/>" for i in range(3))
    return (f"<g transform='translate({x},{y}) rotate({rot})' filter='url(#sh)'><rect x='{-w / 2}' y='-24' width='{w}' height='50' rx='12' fill='{color}' stroke='#4e5f6b'/>"
            f"<rect x='{-w / 2 + 4}' y='-22' width='{w - 8}' height='14' rx='7' fill='#6e808c'/>{cush}"
            f"<rect x='{-w / 2}' y='-24' width='12' height='50' rx='6' fill='#64767f'/><rect x='{w / 2 - 12}' y='-24' width='12' height='50' rx='6' fill='#64767f'/></g>")


def bookcase(x, y, w=150, rot=0):
    books = ""
    cx = -w / 2 + 4
    cols = ["#8c3b3b", "#2b5d7d", "#c9a227", "#3f6b4f", "#6b4a8a", "#b56b2c", "#2d3e50", "#a33c5c"]
    while cx < w / 2 - 6:
        bw = R.uniform(4, 8)
        books += f"<rect x='{cx:.1f}' y='-9' width='{bw:.1f}' height='{R.uniform(12, 17):.1f}' fill='{R.choice(cols)}'/>"
        cx += bw + .8
    return f"<g transform='translate({x},{y}) rotate({rot})' filter='url(#shs)'><rect x='{-w / 2}' y='-12' width='{w}' height='24' fill='#5a3b24'/>{books}</g>"


def cabinet(x, y, n=3, rot=0):
    return (f"<g transform='translate({x},{y}) rotate({rot})' filter='url(#shs)'>" + "".join(
        f"<rect x='{-n * 15 + i * 30}' y='-16' width='28' height='32' rx='2' fill='#9aa3a8' stroke='#7d868b'/><rect x='{-n * 15 + i * 30 + 9}' y='-2' width='10' height='3' rx='1.5' fill='#5d666b'/>"
        for i in range(n)) + "</g>")


def printer(x, y):
    return (f"<g transform='translate({x},{y})' filter='url(#sh)'><rect x='-24' y='-20' width='48' height='40' rx='4' fill='#e9eaec' stroke='#bfc2c6'/>"
            "<rect x='-16' y='-14' width='32' height='10' rx='2' fill='#c7cacd'/><rect x='-12' y='4' width='24' height='12' fill='#fff' stroke='#ddd'/><circle cx='16' cy='-12' r='2' fill='#2ecc71'/></g>")


def water_cooler(x, y):
    return (f"<g transform='translate({x},{y})' filter='url(#sh)'><rect x='-15' y='-15' width='30' height='30' rx='4' fill='#e8ecef' stroke='#c2c9ce'/>"
            "<circle r='11' fill='#9fd3ea' stroke='#6fb3d2'/><circle r='5' fill='#c9e9f6'/></g>")


def meeting_table(x, y, w=380, h=110, chairs=12):
    out = ""
    per = chairs // 2
    for i in range(per):
        cx = x - w / 2 + 40 + i * (w - 80) / max(1, per - 1)
        out += office_chair(cx, y - h / 2 - 16, 0) + office_chair(cx, y + h / 2 + 16, 180)
    out += (f"<g filter='url(#sh)'><rect x='{x - w / 2}' y='{y - h / 2}' width='{w}' height='{h}' rx='{h / 2}' fill='url(#deskD)' stroke='#3a2414'/></g>"
            f"<rect x='{x - w / 2 + 30}' y='{y - h / 2 + 10}' width='{w - 60}' height='8' rx='4' fill='#fff' opacity='.12'/>"
            f"<g transform='translate({x},{y})'><circle r='12' fill='#2d3236'/><circle r='5' fill='#5a6066'/></g>"
            + "".join(f"<rect x='{x - w / 2 + 60 + i * 90}' y='{y - 10 + (i % 2) * 6}' width='22' height='16' fill='#fff' stroke='#ddd' transform='rotate({R.uniform(-15, 15):.0f} {x - w / 2 + 70 + i * 90} {y})'/>" for i in range(4)))
    return out


def round_table(x, y, r=30, n=4):
    out = "".join(office_chair(x + (r + 16) * math.cos(math.radians(a)), y + (r + 16) * math.sin(math.radians(a)), a + 90) for a in range(45, 405, 360 // n))
    return out + f"<circle cx='{x}' cy='{y}' r='{r}' fill='url(#deskW)' stroke='#bdb4a6' filter='url(#sh)'/><circle cx='{x + 6}' cy='{y - 5}' r='5' fill='#fff' stroke='#bbb'/>"


def counter(x, y, w=300, sink=True):
    out = f"<g filter='url(#sh)'><rect x='{x}' y='{y}' width='{w}' height='46' rx='3' fill='#e3e0d8' stroke='#bab5aa'/></g>"
    if sink:
        out += f"<rect x='{x + 14}' y='{y + 8}' width='46' height='30' rx='6' fill='#c9d3d8' stroke='#9aa6ac'/><circle cx='{x + 37}' cy='{y + 12}' r='3' fill='#7c878d'/>"
    out += (f"<rect x='{x + w / 2 - 17}' y='{y + 6}' width='34' height='34' rx='4' fill='#2b2f33'/><circle cx='{x + w / 2}' cy='{y + 23}' r='7' fill='#6b3e22'/>"
            f"<rect x='{x + w - 50}' y='{y + 10}' width='40' height='26' rx='4' fill='#d0d0cc' stroke='#aaa'/>")
    return out


def fridge(x, y):
    return f"<g filter='url(#sh)'><rect x='{x}' y='{y}' width='54' height='54' rx='4' fill='#e9ecee' stroke='#b9c0c4'/><line x1='{x + 4}' y1='{y + 22}' x2='{x + 50}' y2='{y + 22}' stroke='#b9c0c4'/></g>"


def rack(x, y, w=200, rot=0):
    boxes = ""
    cx = -w / 2 + 6
    while cx < w / 2 - 30:
        bw = R.choice([26, 30, 36])
        boxes += (f"<rect x='{cx}' y='-17' width='{bw}' height='34' fill='url(#box)' stroke='#9b7444'/>"
                  f"<line x1='{cx + bw / 2}' y1='-17' x2='{cx + bw / 2}' y2='17' stroke='#c9a46a' stroke-width='3'/>")
        cx += bw + 4
    return (f"<g transform='translate({x},{y}) rotate({rot})' filter='url(#sh)'><rect x='{-w / 2}' y='-22' width='{w}' height='44' fill='#3d6a8f' opacity='.25'/>"
            f"{boxes}<rect x='{-w / 2}' y='-22' width='4' height='44' fill='#e67e22'/><rect x='{w / 2 - 4}' y='-22' width='4' height='44' fill='#e67e22'/></g>")


def pallet(x, y, rot=0):
    return (f"<g transform='translate({x},{y}) rotate({rot})' filter='url(#sh)'><rect x='-30' y='-24' width='60' height='48' fill='#b8935e'/>"
            + "".join(f"<rect x='-30' y='{-22 + i * 10}' width='60' height='7' fill='#c9a46d'/>" for i in range(5))
            + "<rect x='-22' y='-18' width='26' height='22' fill='url(#box)' stroke='#9b7444'/><rect x='6' y='-14' width='20' height='20' fill='url(#box)' stroke='#9b7444'/></g>")


def whiteboard(x, y, w=140, rot=0):
    return f"<g transform='translate({x},{y}) rotate({rot})' filter='url(#shs)'><rect x='{-w / 2}' y='-5' width='{w}' height='10' rx='2' fill='#fafafa' stroke='#b9bec2'/><rect x='{-w / 2 + 10}' y='-2' width='30' height='3' fill='#2b6cb0'/></g>"


def tv(x, y, w=110, rot=0):
    return f"<g transform='translate({x},{y}) rotate({rot})'><rect x='{-w / 2}' y='-4' width='{w}' height='8' rx='2' fill='#111'/><rect x='{-w / 2 + 3}' y='-2' width='{w - 6}' height='3' fill='#0F7C7A' opacity='.7'/></g>"


def rug(x, y, w, h):
    return f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='6' fill='url(#rug)' stroke='#c9a86a' stroke-width='4' opacity='.92'/>"


# ------------------------------------------------------------------ people from above
def top_person(x, y, rot, p, sit=True, typing=True, walk=False):
    """p = dict(shirt, skin, hair, kind)"""
    sh, sk, hr, kind = p["shirt"], p["skin"], p["hair"], p["kind"]
    g1, d1 = grad(shade(sh, .18), shade(sh, -.25), "rad")
    g2, d2 = grad(shade(sk, .15), shade(sk, -.18), "rad")
    g3, d3 = grad(shade(hr, .15), shade(hr, -.3), "rad")
    defs = f"<defs>{d1}{d2}{d3}</defs>"
    shirt = "#f7f7f5" if kind == "saudi" else sh
    gS = f"url(#{g1})" if kind != "saudi" else "#f4f4f1"
    # arms: forward to the keyboard (typing) or along the body (walking)
    if typing and sit:
        arms = (f"<path d='M-20 -2 C-24 -14 -16 -26 -9 -30' stroke='{shirt}' stroke-width='9' fill='none' stroke-linecap='round'/>"
                f"<path d='M20 -2 C24 -14 16 -26 9 -30' stroke='{shirt}' stroke-width='9' fill='none' stroke-linecap='round'/>"
                f"<circle cx='-8' cy='-32' r='4.5' fill='url(#{g2})'/><circle cx='8' cy='-32' r='4.5' fill='url(#{g2})'/>")
    elif walk:
        arms = (f"<path d='M-21 0 C-24 8 -22 16 -18 22' stroke='{shirt}' stroke-width='8.5' fill='none' stroke-linecap='round'/>"
                f"<path d='M21 0 C24 -8 22 -16 18 -22' stroke='{shirt}' stroke-width='8.5' fill='none' stroke-linecap='round'/>"
                f"<circle cx='-18' cy='25' r='4.3' fill='url(#{g2})'/><circle cx='18' cy='-25' r='4.3' fill='url(#{g2})'/>")
    else:
        arms = (f"<path d='M-21 -1 C-24 6 -22 12 -19 16' stroke='{shirt}' stroke-width='8.5' fill='none' stroke-linecap='round'/>"
                f"<path d='M21 -1 C24 6 22 12 19 16' stroke='{shirt}' stroke-width='8.5' fill='none' stroke-linecap='round'/>")
    feet = ("<ellipse cx='-8' cy='-26' rx='4.5' ry='8' fill='#2a2a2a'/><ellipse cx='8' cy='20' rx='4.5' ry='8' fill='#2a2a2a'/>" if walk else "")
    body = f"<path d='M-24 2 C-24 -12 -14 -15 0 -15 C14 -15 24 -12 24 2 C24 13 14 16 0 16 C-14 16 -24 13 -24 2 Z' fill='{gS}' stroke='rgba(0,0,0,.18)'/>"
    if kind == "saudi":
        body += "<path d='M-6 -14 L0 -2 L6 -14' fill='none' stroke='#ddd'/>"
        head = ("<ellipse cx='0' cy='0' rx='15' ry='14' fill='url(#shemagh)' stroke='#d8d8d4'/><path d='M-15 2 C-18 14 -12 22 -6 24 L6 24 C12 22 18 14 15 2' fill='url(#shemagh)' stroke='#d8d8d4'/>"
                "<ellipse cx='0' cy='-1' rx='10' ry='9.5' fill='none' stroke='#111' stroke-width='3'/><ellipse cx='0' cy='-1' rx='10' ry='9.5' fill='none' stroke='#444' stroke-width='1' transform='scale(.82)'/>"
                f"<ellipse cx='0' cy='-14' rx='5' ry='2.6' fill='url(#{g2})'/><ellipse cx='0' cy='-15.6' rx='2.2' ry='1.7' fill='{shade(sk, -.05)}'/>")
    elif kind == "hijab":
        head = (f"<ellipse cx='0' cy='0' rx='14' ry='13.5' fill='url(#{g3})'/><path d='M-14 3 C-16 14 -9 20 0 21 C9 20 16 14 14 3' fill='url(#{g3})'/>"
                f"<path d='M-8 -8 C-2 -11 4 -11 9 -7' stroke='{shade(hr, .3)}' stroke-width='1.2' fill='none'/><path d='M-10 2 C-4 6 4 6 10 2' stroke='{shade(hr, -.35)}' stroke-width='1' fill='none'/>"
                f"<ellipse cx='0' cy='-12.5' rx='6.5' ry='3.2' fill='url(#{g2})'/><ellipse cx='0' cy='-14.6' rx='2.4' ry='1.8' fill='{shade(sk, -.05)}'/>")
    else:
        strands = "".join(f"<path d='M{-8 + i * 3} -4 C{-6 + i * 3} 1 {-7 + i * 3} 7 {-9 + i * 3} 12' stroke='{shade(hr, .25)}' stroke-width='.8' fill='none'/>" for i in range(6))
        # facing -y (the desk): the face / forehead and the nose show at the front, the hair covers the back
        head = (f"<ellipse cx='0' cy='0' rx='12.5' ry='12.5' fill='url(#{g2})'/><ellipse cx='-12.3' cy='-1' rx='2.4' ry='4' fill='{shade(sk, -.12)}'/><ellipse cx='12.3' cy='-1' rx='2.4' ry='4' fill='{shade(sk, -.12)}'/>"
                f"<path d='M-12.5 -2 C-12 -9 -6 -10 0 -10 C6 -10 12 -9 12.5 -2 C13 8 7 13 0 13 C-7 13 -13 8 -12.5 -2 Z' fill='url(#{g3})'/>{strands}"
                f"<ellipse cx='0' cy='-13' rx='3' ry='2.4' fill='{shade(sk, -.05)}'/>")
    hy = 2 if sit else 0
    return (f"<g transform='translate({x},{y}) rotate({rot})'>{defs}<ellipse cx='3' cy='6' rx='28' ry='22' fill='#000' opacity='.18' filter='url(#blur)'/>"
            f"{feet}{arms}{body}<g transform='translate(0,{hy})'>{head}</g></g>")


def name_tag(x, y, name, color="#0F7C7A"):
    w = len(name) * 8 + 20
    return (f"<g filter='url(#shs)'><rect x='{x - w / 2}' y='{y - 10}' width='{w}' height='20' rx='10' fill='#fff'/></g>"
            f"<circle cx='{x + w / 2 - 9}' cy='{y}' r='4' fill='{color}'/><text x='{x - 3}' y='{y + 4.5}' text-anchor='middle' font-size='12' font-weight='800' fill='#1C2B2A'>{name}</text>")


def bubble(x, y, text, red=False):
    w = len(text) * 7.4 + 28
    st = "#C62828" if red else "#d6dedd"
    return (f"<g filter='url(#sh)'><rect x='{x - w / 2}' y='{y - 50}' width='{w}' height='32' rx='16' fill='#fff' stroke='{st}' stroke-width='{2.2 if red else 1}'/>"
            f"<path d='M{x - 7} {y - 19} L{x} {y - 8} L{x + 7} {y - 19} Z' fill='#fff'/></g>"
            f"<text x='{x}' y='{y - 29}' text-anchor='middle' font-size='13.5' fill='#1C2B2A'>{text}</text>")


def status_glow(x, y, color):
    return f"<circle cx='{x}' cy='{y}' r='38' fill='{color}' opacity='.18' filter='url(#blur)'/>"
