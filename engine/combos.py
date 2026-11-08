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


METHODS = {"linear": linear, "pairwise": pairwise, "all": everything}


def build(table, method="linear"):
    table = {str(k).strip(): [str(v).strip() for v in vs if str(v).strip()] for k, vs in (table or {}).items() if str(k).strip()}
    table = {k: list(dict.fromkeys(v)) for k, v in table.items() if v}
    if not table:
        raise ValueError("اكتبي حقل واحد على الأقل وقيمه")
    rows = METHODS.get(method, linear)(table)
    total = 1
    for v in table.values():
        total *= len(v)
    return rows, total
