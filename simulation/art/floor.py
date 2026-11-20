"""The office floor (everything that does not move): building, floors, walls, furniture, room names. 1600 × 900."""
from simulation.art.kit import (DEFS, bookcase, cabinet, counter, door, exec_desk, floor, fridge, glass_wall, label, meeting_table, pallet, plant, printer,
                        rack, round_table, rug, sofa, sunlight, tv, walls, water_cooler, whiteboard, window, workstation)

W, H = 1600, 900
# where each desk is (the person sits 47 px below its centre, facing it)
DESKS = {"mgr": ("exec", 195, 122), "s1": ("ws", 480, 120), "s2": ("ws", 660, 120), "t1": ("ws", 845, 120), "a1": ("ws", 1040, 120), "a2": ("ws", 1215, 120),
         "w1": ("ws", 380, 455), "p1": ("ws", 635, 520), "c1": ("ws", 915, 520), "h1": ("ws", 1145, 520)}
# which desks each job sits at (in this order)
ROLE_SLOTS = {"manager": ["mgr"], "sales": ["s1", "s2"], "it": ["t1"], "accountant": ["a1", "a2"], "warehouse": ["w1"], "purchasing": ["p1"], "cashier": ["c1"], "hr": ["h1"]}
ROLES_AR = {"manager": "المدير", "sales": "مبيعات", "accountant": "محاسب", "warehouse": "مخازن", "purchasing": "مشتريات", "cashier": "خزنة", "hr": "موارد بشرية", "it": "الدعم الفني (IT)"}


def assign_desks(employees):
    """{employee id: desk} by job; (list of employees with no free desk)"""
    used, out, left = set(), {}, []
    for e in employees:
        free = [d for d in ROLE_SLOTS.get(e.get("role"), []) if d not in used]
        if free:
            out[e["id"]] = free[0]
            used.add(free[0])
        else:
            left.append(e)
    return out, left
SPOTS = {"kitchen": (1410, 482), "cooler": (700, 395), "printer": (905, 250), "meeting": (1455, 260)}


def seat(eid):
    kind, x, y = DESKS[eid]
    return (x - 10, y + 52) if kind == "exec" else (x, y + 47)


def monitor_pos(eid):
    kind, x, y = DESKS[eid]
    return (x - 10, y - 26) if kind == "exec" else (x, y - 19)


def server_rack(x, y):
    """🖥️ the IT room's server cabinet: black, with blinking lights"""
    leds = "".join(f"<rect x='{x + 6}' y='{y + 8 + i * 11}' width='30' height='7' rx='1.5' fill='#1f2937'/><circle cx='{x + 32}' cy='{y + 11.5 + i * 11}' r='1.8' fill='{c}'>"
                   f"<animate attributeName='opacity' values='1;.2;1' dur='{1 + i * .37:.2f}s' repeatCount='indefinite'/></circle>" for i, c in enumerate(["#22c55e", "#22c55e", "#f59e0b", "#22c55e", "#3b82f6"]))
    return f"<g filter='url(#sh)'><rect x='{x}' y='{y}' width='42' height='66' rx='4' fill='#111827' stroke='#374151'/>{leds}</g>"


def build(used=None):
    """used = the desks that have someone (an empty desk isn't drawn)"""
    s = [DEFS, f"<rect width='{W}' height='{H}' fill='#2f363c'/>"]
    s += [floor(20, 20, 350, 310, "url(#carpet2)"), floor(370, 20, 560, 310, "url(#wood)"), floor(930, 20, 400, 310, "url(#wood)"), floor(1330, 20, 250, 310, "url(#carpet)"),
          floor(20, 330, 1560, 70, "url(#tile)"), floor(20, 400, 450, 480, "url(#concrete)"), floor(470, 400, 330, 480, "url(#wood)"),
          floor(800, 400, 230, 480, "url(#carpet)"), floor(1030, 400, 230, 480, "url(#wood)"), floor(1260, 400, 320, 480, "url(#tile)")]
    s += [sunlight(20, 20, 1560, 160), rug(222, 240, 138, 80)]
    s.append(walls([(20, 20, 1580, 20), (20, 20, 20, 880), (1580, 20, 1580, 880), (20, 880, 1580, 880)], 14))
    s += [window(60, 20, 340, 20), window(410, 20, 900, 20), window(960, 20, 1300, 20), window(1360, 20, 1550, 20), window(20, 60, 20, 300), window(20, 450, 20, 840),
          window(520, 880, 760, 880), window(1300, 880, 1540, 880), window(1580, 450, 1580, 840)]
    s += [glass_wall(370, 20, 370, 330), glass_wall(760, 20, 760, 330), glass_wall(930, 20, 930, 330), glass_wall(1330, 20, 1330, 330)]   # 760: 🖥️ IT support
    s.append(walls([(20, 330, 120, 330), (190, 330, 420, 330), (490, 330, 790, 330), (860, 330, 980, 330), (1050, 330, 1380, 330), (1450, 330, 1580, 330),
                    (20, 400, 200, 400), (270, 400, 540, 400), (610, 400, 850, 400), (920, 400, 1080, 400), (1150, 400, 1300, 400), (1380, 400, 1580, 400),
                    (470, 400, 470, 880), (1260, 400, 1260, 880)], 9))
    s += [glass_wall(800, 400, 800, 880), glass_wall(1030, 400, 1030, 880)]
    s += [door(120, 330, 34, -90), door(420, 330, 34, -90), door(790, 330, 34, -90), door(980, 330, 34, -90), door(1380, 330, 34, -90), door(200, 400, 34, 0), door(540, 400, 34, 0),
          door(850, 400, 34, 0), door(1080, 400, 34, 0), door(1300, 400, 34, 0)]
    s += [bookcase(195, 38, 230), sofa(290, 300, 120, 0), "<rect x='262' y='258' width='56' height='28' rx='6' fill='url(#deskD)' filter='url(#sh)'/>", exec_desk(195, 122),
          plant(342, 52, 26), plant(48, 300, 20)]
    for d, (kind, x, y) in DESKS.items():
        if kind == "ws" and (used is None or d in used):
            s.append(workstation(x, y, 0, "#3b4a52", items=d != "w1"))
    s += [printer(905, 290), plant(905, 52, 22), plant(400, 300, 20), whiteboard(565, 318, 160), server_rack(880, 190)]
    s += [cabinet(1135, 300, 3), cabinet(1265, 300, 2), plant(1305, 52, 22)]
    s += [meeting_table(1455, 190, 170, 90, 8), tv(1455, 34, 120), plant(1355, 300, 20), plant(1555, 300, 20)]
    s += [water_cooler(700, 365), plant(1180, 365, 18), plant(300, 365, 18)]
    s += [rack(245, 640, 380), rack(245, 720, 380), rack(245, 800, 380), pallet(75, 470), pallet(75, 550, 6), pallet(150, 550, -4),
          "<g filter='url(#sh)'><rect x='150' y='440' width='40' height='70' rx='6' fill='#e0a400'/><rect x='155' y='450' width='30' height='30' rx='4' fill='#333'/></g>"]
    s += [cabinet(560, 860, 3), plant(775, 860, 22), bookcase(635, 790, 200)]
    s += ["<g filter='url(#sh)'><rect x='940' y='800' width='64' height='64' rx='6' fill='#4b5563'/><circle cx='972' cy='832' r='14' fill='#9ca3af'/><circle cx='972' cy='832' r='5' fill='#374151'/></g>",
          plant(825, 860, 18), cabinet(1145, 860, 3), plant(1240, 640, 18)]
    s += [counter(1388, 412, 185), fridge(1520, 475), round_table(1350, 600, 30, 4), round_table(1490, 600, 30, 4), sofa(1420, 830, 220, 0), plant(1290, 850, 22), plant(1560, 760, 18)]
    s += [label(110, 62, "مكتب المدير"), label(565, 45, "المبيعات"), label(845, 45, "الدعم الفني"), label(1130, 45, "الحسابات"), label(1455, 75, "الاجتماعات"), label(245, 600, "المخازن"),
          label(635, 425, "المشتريات"), label(915, 425, "الخزنة"), label(1145, 425, "الموارد البشرية"), label(1420, 515, "البوفيه")]
    return "".join(s)
