#!/usr/bin/env python3
"""perservice-cpu.sh の CSV から「利用率カーブの高さ」を要約する。

出すもの(判定平面の縦軸):
  * 1周(=1checkout)あたりCPU c_s [mコア秒]   … 負荷1単位でどれだけCPUを使うか(サービスの素性)
  * 枠 r_s [m]                                … マニフェストの requests(実験中は不変)
  * 傾き c_s / r_s [%/(周/秒)]                … 負荷を1増やすと利用率が何%上がるか = 高さの上がり方
  * 70%到達レート = 70 / (c_s/r_s) [周/秒]    … HPA が台数を増やし始める負荷。小さいほど「熱い」
  * スロットリング率の最大値                  … >0 の点があるとカーブが天井で寝ているので要注意

使い方: python3 km2/experiments/perservice-cpu-analyze.py [CSV] [--arm normal]
"""
import sys, csv, argparse
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("csv", nargs="?", default="km2/experiments/results-perservice-cpu.csv")
ap.add_argument("--arm", default=None, help="対象アーム(既定=CSVにある全部)")
ap.add_argument("--target", type=float, default=70.0, help="HPA目標利用率[%%](既定70)")
a = ap.parse_args()

rows = list(csv.DictReader(open(a.csv)))
if a.arm:
    rows = [r for r in rows if r["arm"] == a.arm]
if not rows:
    sys.exit("行がありません: %s" % a.csv)

# キー = (arm, pod, container)。pod名は既にハッシュ除去済み。
pts = defaultdict(list)   # -> [(achieved_rate, usage_mc, req_mc, throttle)]
for r in rows:
    try:
        rate = float(r["iter_rate"]); use = float(r["usage_mc"]); req = float(r["req_mc"])
        thr = float(r.get("throttle_pct") or 0)
    except ValueError:
        continue
    if rate <= 0:
        continue
    pts[(r["arm"], r["pod"], r["container"])].append((rate, use, req, thr))


def fit_slope(xs, ys):
    """原点を通らない直線 y = a*x + b を最小二乗で当てる。点が1つなら原点通しで代用。"""
    n = len(xs)
    if n == 1:
        return ys[0] / xs[0], 0.0
    mx = sum(xs) / n; my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return ys[0] / xs[0], 0.0
    a_ = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return a_, my - a_ * mx


out = []
for (arm, pod, cont), v in pts.items():
    v.sort()
    xs = [p[0] for p in v]; ys = [p[1] for p in v]
    req = max(p[2] for p in v)
    thr = max(p[3] for p in v)
    slope_mc, base = fit_slope(xs, ys)          # mコア / (周/秒) = 1周あたりCPU[mコア秒]
    if req <= 0:
        continue
    util_slope = slope_mc / req * 100.0          # %/(周/秒)
    # 利用率 = (base + slope*rate)/req*100 が target に届くレート
    hit = (a.target / 100.0 * req - base) / slope_mc if slope_mc > 0 else float("inf")
    out.append(dict(arm=arm, pod=pod, cont=cont, c=slope_mc, base=base, r=req,
                    us=util_slope, hit=hit, thr=thr, n=len(v),
                    umax=max(y / req * 100.0 for y in ys), rmax=max(xs)))

out.sort(key=lambda d: (d["arm"], d["hit"]))
cur = None
for d in out:
    if d["arm"] != cur:
        cur = d["arm"]
        print("\n=== arm=%s : 利用率カーブの高さ(%.0f%%到達が早い順=熱い順) ===" % (cur, a.target))
        print("%-24s %-18s %8s %7s %10s %12s %8s %7s" %
              ("pod", "container", "c[mc秒/周]", "枠[m]", "傾き%/(周/s)", "%d%%到達[周/s]" % a.target, "実測最大%", "絞り%"))
    print("%-24s %-18s %8.2f %7.0f %10.3f %12s %8.1f %7.1f" %
          (d["pod"], d["cont"], d["c"], d["r"], d["us"],
           ("%.0f" % d["hit"]) if d["hit"] < 1e5 else "-", d["umax"], d["thr"]))

# 束ね候補ペアの「高さのズレ」= 到達レート比(1に近いほど揃っている=損が小さい)
print("\n=== ペアごとの高さのズレ(到達レート比 = 冷たい方 ÷ 熱い方。1に近いほど束ねて損が小さい) ===")
svc = [d for d in out if d["hit"] < 1e5 and d["cont"] not in ("redis",)]
svc.sort(key=lambda d: d["hit"])
for i in range(len(svc)):
    for j in range(i + 1, len(svc)):
        a1, b1 = svc[i], svc[j]
        if a1["arm"] != b1["arm"]:
            continue
        ratio = b1["hit"] / a1["hit"]
        print("  %-20s + %-20s ズレ=%5.1f倍  (%s が先に%d%%到達)" %
              (a1["cont"], b1["cont"], ratio, a1["cont"], a.target))
