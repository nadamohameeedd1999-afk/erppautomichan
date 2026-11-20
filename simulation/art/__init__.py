"""The drawings of the company: the floor, every employee in every pose (from above), and the camera of every desk."""


def build_art(cfg):
    from simulation.art.camera import camera
    from simulation.art.floor import H, W, assign_desks, build, monitor_pos
    from simulation.art.kit import top_person
    people, cams, mons = {}, {}, {}
    desks, _ = assign_desks(cfg["employees"])
    for e in cfg["employees"]:
        p = e.get("look") or {"kind": "man", "skin": "#E0AC82", "hair": "#2d2018", "shirt": e.get("color", "#2B6CB0")}
        people[e["id"]] = {"sit": top_person(0, 0, 0, p, sit=True, typing=True), "sit_idle": top_person(0, 0, 0, p, sit=True, typing=False),
                           "walk": top_person(0, 0, 0, p, sit=False, typing=False, walk=True), "stand": top_person(0, 0, 0, p, sit=False, typing=False)}
        cams[e["id"]] = camera(p, e["id"])
        if e["id"] in desks:
            mons[e["id"]] = monitor_pos(desks[e["id"]])
    # 🧑‍🍳 the office boy in the pantry and 🆕 the new sales colleague at the third desk (not on the system yet) — they don't work on NQ ERP
    from simulation.art.floor import seat
    boy = {"kind": "man", "skin": "#C68A5E", "hair": "#1b1410", "shirt": "#8B5E3C"}
    extras = {"boy": {"x": 1300, "y": 650, "poses": {"stand": top_person(0, 0, 0, boy, sit=False, typing=False), "walk": top_person(0, 0, 0, boy, sit=False, typing=False, walk=True)}},
              }
    return {"w": W, "h": H, "floor": build(set(desks.values())), "people": people, "cameras": cams, "monitors": mons, "extras": extras}
