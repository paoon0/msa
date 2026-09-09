#!/usr/bin/env python3
"""枠(requests)の適正化テーブルを、実測の利用率カーブから作る。

規則(これ1つだけ):
    枠_s = (アイドル分_s + 1周あたりCPU_s × k) / 0.7
  * アイドル分 = 負荷ゼロでも食うCPU(直線の切片)。Pod 1台ごとにかかる。
  * 1周あたりCPU = 負荷を1周/秒 増やすと増えるCPU(直線の傾き)。
  * k = 1台に担当させたい負荷[周/秒]。既定100。
  ⇒ 「1台が k 周/秒 を担当している状態」で全サービスがちょうど 70% になる = 高さが揃う。
    高さが揃えば同じ負荷で一斉に台数が増えるので、粒度損は原理的にゼロになるはず。
    それでも残る損があれば、それは設定の粗さではなく「サービスの素性(アイドル分の重さ)」に由来する本質的な損。

入力: km2/experiments/results-perservice-cpu.csv (2026-08-18 の測定: 分離・1台固定・HPA無し・10〜150周/s)
出力: km2/experiments/summer2026/rightsize-requests.csv  (deploy,container,request_m)
      + 現状の枠との比較表を標準出力へ

使い方:
  python3 km2/experiments/summer2026/rightsize.py            # k=100
  python3 km2/experiments/summer2026/rightsize.py --k 120
"""
import csv, argparse, os
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('--src', default='km2/experiments/results-perservice-cpu.csv')
ap.add_argument('--out', default='km2/experiments/summer2026/rightsize-requests.csv')
ap.add_argument('--k', type=float, default=100.0, help='1台に担当させる負荷[周/秒]')
ap.add_argument('--target', type=float, default=0.70, help='HPA目標利用率')
ap.add_argument('--throttle-max', type=float, default=5.0, help='この%%を超えて絞られた点は捨てる')
ap.add_argument('--min-req', type=float, default=50.0, help='枠の下限[m](小さすぎるとスケジューラ判断が雑になる)')
a = ap.parse_args()

# 1台測定のCSV: 行 = (負荷, コンテナ, 使用m, 枠m, 絞り%)
pts = defaultdict(list)
cur_req = {}
for r in csv.DictReader(open(a.src)):
    key = (r['pod'], r['container'])
    try:
        rate = float(r['iter_rate']); use = float(r['usage_mc'])
        req = float(r['req_mc']); thr = float(r['throttle_pct'])
    except ValueError:
        continue
    if thr > a.throttle_max:      # 天井で絞られた点はカーブが寝ているので使わない
        continue
    pts[key].append((rate, use))
    cur_req[key] = req


def fit(xs, ys):
    """y = a*x + b の最小二乗。a=1周あたりCPU, b=アイドル分。"""
    n = len(xs)
    mx = sum(xs) / n; my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0, my
    s = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return s, my - s * mx


rows = []
for key, v in pts.items():
    if len(v) < 3:
        continue
    v.sort()
    slope, idle = fit([p[0] for p in v], [p[1] for p in v])
    slope = max(slope, 0.0)
    idle = max(idle, 0.0)
    req = (idle + slope * a.k) / a.target
    req = max(req, a.min_req)
    rows.append(dict(pod=key[0], container=key[1], slope=slope, idle=idle,
                     new=req, cur=cur_req[key], n=len(v)))

rows.sort(key=lambda d: -d['cur'])
print("規則: 枠 = (アイドル分 + 1周あたりCPU × k) / %.2f    k=%.0f 周/秒/台" % (a.target, a.k))
print("%-24s %-14s %10s %10s %9s %9s %8s" % ("deploy", "container", "1周CPU", "アイドルm", "現状枠m", "適正枠m", "変化"))
tot_c = tot_n = 0
for d in rows:
    tot_c += d['cur']; tot_n += d['new']
    print("%-24s %-14s %10.2f %10.0f %9.0f %9.0f %8.2f倍"
          % (d['pod'], d['container'], d['slope'], d['idle'], d['cur'], d['new'], d['new'] / d['cur']))
print("%-24s %-14s %10s %10s %9.0f %9.0f %8.2f倍" % ("合計(1台ずつの場合)", "", "", "", tot_c, tot_n, tot_n / tot_c))

os.makedirs(os.path.dirname(a.out), exist_ok=True)
with open(a.out, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['deploy', 'container', 'request_m', 'slope_mc_per_iter', 'idle_m', 'old_request_m'])
    for d in rows:
        w.writerow([d['pod'], d['container'], round(d['new']), round(d['slope'], 3), round(d['idle']), round(d['cur'])])
print("\n書き出し: %s" % a.out)
print("※ この表は『サービスごと』の値。束ねたPodでは中の各コンテナに同じ値をそのまま与える")
print("  (同居してもアプリのCPU消費は変わらないことは実測済み)。limits は変更しない=絞りの人工的な影響を入れないため。")
