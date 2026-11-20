"""The «camera» of one desk: the employee at their desk, facing us, their screen beside them (filled live by the page)."""
import math
from simulation.art.kit import shade


def camera(p, eid):
    sk, hr, sh, kind = p["skin"], p["hair"], p["shirt"], p["kind"]
    u = eid
    top = shade(sh, .15) if kind != "saudi" else "#ffffff"
    bot = shade(sh, -.35) if kind != "saudi" else "#dcdcd6"
    if kind == "hijab":
        head = (f"<path d='M190 120 C186 60 314 60 310 120 C312 176 292 222 250 236 C208 222 188 176 190 120 Z' fill='url(#hj{u})'/>"
                f"<ellipse cx='250' cy='140' rx='44' ry='54' fill='url(#fc{u})'/>"
                f"<path d='M206 118 C214 82 286 82 294 118 C282 98 218 98 206 118 Z' fill='url(#hj{u})'/>"
                f"<path d='M196 234 C220 250 280 250 304 234 L296 300 C270 312 230 312 204 300 Z' fill='url(#hj{u})' opacity='.95'/>")
    elif kind == "saudi":
        head = (f"<ellipse cx='250' cy='142' rx='42' ry='52' fill='url(#fc{u})'/>"
                f"<path d='M196 128 C190 70 310 70 304 128 L318 250 C292 226 292 190 290 140 L210 140 C208 190 208 226 182 250 Z' fill='url(#sm{u})' stroke='#d9d9d4'/>"
                f"<rect x='204' y='92' width='92' height='12' rx='6' fill='#111'/><rect x='206' y='104' width='88' height='6' rx='3' fill='#222'/>"
                f"<path d='M222 176 C230 196 270 196 278 176 C276 200 266 212 250 214 C234 212 224 200 222 176 Z' fill='#2d2018'/>")
    else:
        beard = (f"<path d='M210 160 C214 196 286 196 290 160 C288 204 270 214 250 216 C230 214 212 204 210 160 Z' fill='{hr}' opacity='.9'/>" if p.get("beard") else "")
        head = (f"<rect x='232' y='186' width='36' height='44' rx='12' fill='{shade(sk, -.08)}'/>"
                f"<ellipse cx='204' cy='146' rx='8' ry='13' fill='{shade(sk, -.1)}'/><ellipse cx='296' cy='146' rx='8' ry='13' fill='{shade(sk, -.1)}'/>"
                f"<ellipse cx='250' cy='140' rx='46' ry='56' fill='url(#fc{u})'/>{beard}"
                f"<path d='M204 132 C198 76 302 76 296 132 C290 106 270 96 250 98 C230 96 210 106 204 132 Z' fill='url(#hr{u})'/>")
    collar = (f"<path d='M226 232 L250 262 L274 232' fill='none' stroke='#f5f5f2' stroke-width='10'/>" if kind == "man" else "")
    return f"""<svg viewBox='0 0 560 340' style='display:block;width:100%'>
 <defs>
  <linearGradient id='wl{u}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#eef0ec'/><stop offset='1' stop-color='#d9ddd6'/></linearGradient>
  <radialGradient id='fc{u}' cx='.45' cy='.4' r='.65'><stop offset='0' stop-color='{shade(sk, .18)}'/><stop offset='.75' stop-color='{sk}'/><stop offset='1' stop-color='{shade(sk, -.2)}'/></radialGradient>
  <linearGradient id='hj{u}' x1='0' y1='0' x2='1' y2='1'><stop offset='0' stop-color='{shade(hr, .25)}'/><stop offset='1' stop-color='{shade(hr, -.35)}'/></linearGradient>
  <linearGradient id='hr{u}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{shade(hr, .2)}'/><stop offset='1' stop-color='{shade(hr, -.3)}'/></linearGradient>
  <linearGradient id='bl{u}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='{top}'/><stop offset='1' stop-color='{bot}'/></linearGradient>
  <pattern id='sm{u}' width='8' height='8' patternUnits='userSpaceOnUse'><rect width='8' height='8' fill='#fbfbfa'/><path d='M0 0L4 4L0 8M4 0L8 4L4 8' stroke='#c0392b' stroke-width='1' fill='none'/></pattern>
  <linearGradient id='dk{u}' x1='0' y1='0' x2='0' y2='1'><stop offset='0' stop-color='#efe9df'/><stop offset='1' stop-color='#d4cbbd'/></linearGradient>
  <linearGradient id='ch{u}' x1='0' y1='0' x2='1' y2='0'><stop offset='0' stop-color='#1c1f23'/><stop offset='.5' stop-color='#3a3f45'/><stop offset='1' stop-color='#1c1f23'/></linearGradient>
  <radialGradient id='lf{u}' cx='.4' cy='.35' r='.8'><stop offset='0' stop-color='#8cc48a'/><stop offset='1' stop-color='#3f7a45'/></radialGradient>
  <filter id='cs{u}'><feDropShadow dx='0' dy='6' stdDeviation='6' flood-opacity='.3'/></filter>
 </defs>
 <rect width='560' height='340' fill='url(#wl{u})'/>
 <g transform='translate(38,28)'><rect width='130' height='110' fill='#bfe0ef'/>{''.join(f"<rect y='{i * 9}' width='130' height='6' fill='#f3f0e6'/>" for i in range(12))}<rect width='130' height='110' fill='none' stroke='#9aa5a8' stroke-width='5'/></g>
 <g transform='translate(400,36)' filter='url(#cs{u})'><rect width='74' height='54' fill='#fff' stroke='#8d6e4f' stroke-width='5'/><rect x='12' y='12' width='50' height='4' fill='#c9a86a'/><rect x='12' y='22' width='40' height='3' fill='#bbb'/><rect x='12' y='30' width='44' height='3' fill='#bbb'/><circle cx='54' cy='42' r='6' fill='#c0392b' opacity='.7'/></g>
 <g transform='translate(470,110)'><rect x='-6' y='0' width='70' height='8' fill='#8d6e4f'/>{''.join(f"<rect x='{i * 13}' y='-34' width='11' height='34' fill='{c}'/>" for i, c in enumerate(['#2b5d7d', '#8c3b3b', '#3f6b4f', '#c9a227', '#2d3e50']))}</g>
 <g transform='translate(505,190)'><rect x='-16' y='10' width='32' height='34' rx='4' fill='#e8e4dc'/>{''.join(f"<ellipse cx='{12 * math.cos(math.radians(a)):.0f}' cy='{-6 + 10 * math.sin(math.radians(a)):.0f}' rx='16' ry='6' transform='rotate({a} {12 * math.cos(math.radians(a)):.0f} {-6 + 10 * math.sin(math.radians(a)):.0f})' fill='url(#lf{u})'/>" for a in range(0, 360, 40))}</g>
 <path d='M150 330 L150 120 C150 92 170 78 200 78 L300 78 C330 78 350 92 350 120 L350 330 Z' fill='url(#ch{u})'/>
 <path d='M130 340 C130 262 170 232 250 226 C330 232 370 262 370 340 Z' fill='url(#bl{u})'/>{collar}
 <path d='M150 290 C140 300 170 318 210 318' stroke='url(#bl{u})' stroke-width='30' fill='none' stroke-linecap='round'/>
 <path d='M350 290 C360 300 330 318 290 318' stroke='url(#bl{u})' stroke-width='30' fill='none' stroke-linecap='round'/>
 {head}
 <path d='M226 125 Q236 119 245 124' stroke='#3b2a20' stroke-width='3' fill='none' stroke-linecap='round'/><path d='M255 124 Q264 119 274 125' stroke='#3b2a20' stroke-width='3' fill='none' stroke-linecap='round'/>
 <ellipse cx='236' cy='138' rx='7' ry='5' fill='#fff'/><ellipse cx='264' cy='138' rx='7' ry='5' fill='#fff'/>
 <circle cx='237' cy='138' r='3.6' fill='#3b2614'/><circle cx='265' cy='138' r='3.6' fill='#3b2614'/><circle cx='238' cy='137' r='1.1' fill='#fff'/><circle cx='266' cy='137' r='1.1' fill='#fff'/>
 <path d='M251 146 C249 152 248 157 246 160' stroke='{shade(sk, -.25)}' stroke-width='1.6' fill='none' stroke-linecap='round'/><path d='M244 161 Q250 165 256 161' stroke='{shade(sk, -.3)}' stroke-width='1.8' fill='none' stroke-linecap='round'/>
 <path d='M237 175 Q250 170 263 175 Q250 184 237 175 Z' fill='#b0565a'/>
 <rect x='0' y='300' width='560' height='40' fill='url(#dk{u})'/><rect x='0' y='300' width='560' height='4' fill='#c4baa9'/>
 <g transform='translate(250,318)'><rect x='-60' y='-8' width='120' height='16' rx='3' fill='#f4f4f1' stroke='#cfcfca'/>{''.join(f"<rect x='{-56 + i * 7.4:.1f}' y='-5' width='6' height='4' rx='1' fill='#d9d9d6'/>" for i in range(15))}</g>
 <ellipse cx='196' cy='316' rx='16' ry='9' fill='{sk}'/><ellipse cx='304' cy='316' rx='16' ry='9' fill='{sk}'/>
 <g transform='translate(470,300)'><path d='M-14 -26 h28 v26 a4 4 0 0 1 -4 4 h-20 a4 4 0 0 1 -4 -4 z' fill='#fff' stroke='#ccc'/><path d='M14 -20 c10 0 10 14 0 14' stroke='#ccc' stroke-width='3' fill='none'/></g>
 <g transform='translate(60,170)' filter='url(#cs{u})'><rect x='-6' y='0' width='150' height='100' rx='6' fill='#16191c'/><rect x='0' y='6' width='138' height='86' fill='#fff' class='cam-bg'/>
  <rect x='0' y='6' width='138' height='14' fill='#0F7C7A' class='cam-bar'/><text x='69' y='16.5' font-size='8' fill='#fff' text-anchor='middle' class='cam-title'>NQ ERP</text>
  <rect x='8' y='26' width='122' height='6' rx='2' fill='#e2e8e8'/><rect x='8' y='36' width='90' height='6' rx='2' fill='#e2e8e8'/><rect x='8' y='46' width='108' height='6' rx='2' fill='#e2e8e8'/>
  <g class='cam-err' style='display:none'><rect x='10' y='50' width='118' height='36' rx='5' fill='#fdecea' stroke='#C62828'/><text x='69' y='64' font-size='7.5' fill='#C62828' text-anchor='middle' font-weight='700' class='cam-msg'></text>
   <text x='69' y='77' font-size='6.5' fill='#7f1d1d' text-anchor='middle'>رسالة النظام</text></g>
  <rect x='60' y='100' width='18' height='18' fill='#2a2e33'/><rect x='40' y='116' width='58' height='6' rx='3' fill='#2a2e33'/></g>
</svg>"""
