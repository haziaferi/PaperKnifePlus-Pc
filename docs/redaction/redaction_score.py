"""Score the redaction strategies from redaction-bench.json, over every weighting.

Measured per strategy (from the bench, 8 cases):
  leak        worst case share of hidden ink still recoverable (0 best)
  collateral  mean share of visible ink damaged outside the boxes (0 best)
  search      mean share of outside words still extractable (1 best)
  size        worst output/input byte ratio (log-scaled, 1 = no growth)
Judged, and swept rather than fixed, because they are not measurements:
  precedent   1 if a leading redaction product defaults to this behaviour
              (Acrobat / PDF-XChange / Apryse clip; LibreOffice / PDF24 rasterise)
  risk        implementation risk in this codebase: 0 one-argument change,
              0.3 rasterise (reuses existing render code), 0.6 clip (new geometry code)
"""
import itertools
import json
import math
from collections import Counter
from pathlib import Path

rows = json.loads((Path(__file__).parent / "redaction-bench.json").read_text("utf-8"))
strategies = list(dict.fromkeys(r["strategy"] for r in rows))

measured = {}
for s in strategies:
    rs = [r for r in rows if r["strategy"] == s]
    measured[s] = {
        "leak": max(r["leak"] for r in rs),
        "collateral": sum(r["collateral"] for r in rs) / len(rs),
        "search": sum(r["search"] for r in rs) / len(rs),
        "size": max(r["size_ratio"] for r in rs),
    }
PRECEDENT = {"none (0)": 0, "covered (1, now)": 0, "touched (2)": 0,
             "clip at edge": 1, "rasterise page": 1}
RISK = {"none (0)": 0, "covered (1, now)": 0, "touched (2)": 0,
        "clip at edge": 0.6, "rasterise page": 0.3}


def goodness(s):
    m = measured[s]
    return {
        "leak": 1 - min(1, m["leak"]),
        "collateral": 1 - min(1, m["collateral"]),
        "search": m["search"],
        "size": 1 - min(1, math.log10(max(1, m["size"])) / 2),  # 100x growth -> 0
        "precedent": PRECEDENT[s],
        "risk": 1 - RISK[s],
    }


crit = ["leak", "collateral", "search", "size", "precedent", "risk"]
levels = [0, 1, 2, 3]
wins, total = Counter(), 0
leak_first = Counter()
for w in itertools.product(levels, repeat=len(crit)):
    if sum(w) == 0:
        continue
    total += 1
    score = {s: sum(wi * goodness(s)[c] for wi, c in zip(w, crit, strict=True)) / sum(w) for s in strategies}
    best = max(score.values())
    for s in strategies:
        if abs(score[s] - best) < 1e-9:
            wins[s] += 1
    if w[0] == max(w):  # weightings where leakage matters at least as much as anything
        leak_first[max(score, key=score.get)] += 1

print("measured:")
for s in strategies:
    m = measured[s]
    print(f"  {s:18} leak {m['leak']:.2f}  collateral {m['collateral']:.3f}  "
          f"search {m['search']:.2f}  size x{m['size']:.2f}")
print(f"\nwinner share over all {total} weightings (0-3 per criterion, ties count for each):")
for s, n in wins.most_common():
    print(f"  {s:18} {n / total:6.1%}")
n_lf = sum(leak_first.values())
print(f"\nwhen leakage weight is the highest weight ({n_lf} weightings):")
for s, n in leak_first.most_common():
    print(f"  {s:18} {n / n_lf:6.1%}")


def dominates(a, b):
    ga, gb = goodness(a), goodness(b)
    keys = ["leak", "collateral", "search", "size"]
    return all(ga[k] >= gb[k] for k in keys) and any(ga[k] > gb[k] for k in keys)


front = [s for s in strategies if not any(dominates(o, s) for o in strategies if o != s)]
print("\nPareto front on the four measured criteria:", front)
