"""
🧮 Combinations table (idea: Tricentis Tosca TestCase-Design / «linear expansion»)

You write the possible values of each field — customer type, payment way, discount… — and get the fewest rows that
still test what matters, saved as a data file (data/datasets) that the Test Builder runs row by row.

  linear   (توسع خطي)   one base row (the first value of every field), then for each field each other value once
                        with the rest at their base → 1 + Σ(values − 1) rows. Every value is tried at least once.
  pairwise (كل زوجين)   every pair of values of any two fields shows up together at least once — catches the bugs
                        that only happen with one particular combination (credit customer + discount + foreign currency)
  all      (كل التوافيق) every combination (only for small tables: capped at 500 rows)
"""
import itertools


def linear(table):
    cols = [c for c, vs in table.items() if vs]
    base = {c: table[c][0] for c in cols}
    rows = [dict(base)]
    for c in cols:
        for v in table[c][1:]:
            rows.append({**base, c: v})
    return rows


def pairwise(table):
    cols = [c for c, vs in table.items() if vs]
    if len(cols) < 2:
        return linear(table)
    left = {(a, va, b, vb) for a, b in itertools.combinations(cols, 2) for va in table[a] for vb in table[b]}
    rows = []
    while left:
        best, best_n = None, -1
        # greedy: start from the pair still uncovered, fill the other fields with the value covering most pairs
        a, va, b, vb = next(iter(sorted(left)))
        row = {a: va, b: vb}
        for c in cols:
            if c in row:
                continue
            row[c] = max(table[c], key=lambda v: sum(1 for d in row if (d, row[d], c, v) in left or (c, v, d, row[d]) in left))
        covered = {(x, row[x], y, row[y]) for x, y in itertools.combinations(cols, 2)}
        left -= covered
        rows.append({c: row[c] for c in cols})
    return rows


def everything(table, cap=500):
    cols = [c for c, vs in table.items() if vs]
    out = []
    for combo in itertools.product(*(table[c] for c in cols)):
        out.append(dict(zip(cols, combo)))
        if len(out) >= cap:
            break
    return out


EXPECT = "المتوقع"      # a column the data runner reads: «رفض» = this row must be rejected by the ERP


def _num(x):
    x = float(x)
    return int(x) if x == int(x) else x


def boundary(table):
    """ISTQB boundary value analysis + equivalence classes (idea: AT*SQA / ISTQB test design techniques).
    A field written as «min..max» (e.g. 1..100) gives: min, min+1, max-1, max (must save) and min-1, max+1 (must be
    rejected); «..max» / «min..» work too. Other fields keep their first value. -> rows with an «المتوقع» column."""
    base, rows = {}, []
    ranges = {}
    for c, vs in table.items():
        v = vs[0]
        if ".." in v and len(vs) == 1:
            lo, hi = (x.strip() for x in v.split("..", 1))
            ranges[c] = (float(lo) if lo else None, float(hi) if hi else None)
            base[c] = str(_num(ranges[c][0] if lo else (ranges[c][1] if hi else 1)))
        else:
            base[c] = v
    rows.append({**base, EXPECT: "حفظ"})
    for c, (lo, hi) in ranges.items():
        step = 1
        ok_vals = [x for x in ([lo, lo + step] if lo is not None else []) + ([hi - step, hi] if hi is not None else [])]
        bad_vals = ([lo - step] if lo is not None else []) + ([hi + step] if hi is not None else [])
        for v in dict.fromkeys(ok_vals):
            if str(_num(v)) != base[c]:
                rows.append({**base, c: str(_num(v)), EXPECT: "حفظ"})
        for v in bad_vals:
            rows.append({**base, c: str(_num(v)), EXPECT: "رفض"})
        rows.append({**base, c: "", EXPECT: "رفض"})          # empty = the «missing» class
    for c, vs in table.items():                              # the other values of list-like fields, once each
        if c not in ranges:
            for v in vs[1:]:
                rows.append({**base, c: v, EXPECT: "حفظ"})
    return rows


METHODS = {"linear": linear, "pairwise": pairwise, "all": everything, "boundary": boundary}


def build(table, method="linear"):
    table = {str(k).strip(): [str(v).strip() for v in vs if str(v).strip()] for k, vs in (table or {}).items() if str(k).strip()}
    table = {k: list(dict.fromkeys(v)) for k, v in table.items() if v}
    if not table:
        raise ValueError("اكتبي حقل واحد على الأقل وقيمه")
    if method == "boundary" and not any(".." in v[0] for v in table.values()):
        raise ValueError("القيم الحدودية: اكتبي المدى في حقل واحد على الأقل بالشكل 1..100")
    rows = METHODS.get(method, linear)(table)
    total = 1
    for v in table.values():
        total *= len(v)
    return rows, total
