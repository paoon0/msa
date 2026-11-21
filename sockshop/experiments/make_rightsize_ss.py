#!/usr/bin/env python3
"""Sock Shop: 基準の配合で 3 台になる枠の表を作る (2026-11-10、OB の km2/experiments/rightsizing/make_rightsize_k3.py と同じ式)。

枠 r = D1 / 1.5。D1 = 結果 CSV の point=BASE・replicas=1 の usage_mc の全サイクル平均。
  1 台なら利用率 150% → HPA (目標 70%) が 1 × 150/70 = 2.14 を切り上げて 3 台にする。
対象は HPA をかけるアプリ 8 つ。DB 5 つと rabbitmq は表に入れない (マニフェストの 100m のまま、HPA 無しで 1 台)。
基準 b32v160 は 2026-11-09 の提案 (ρ の格子の真ん中)。ユーザの最終確認はまだ (2026-11-10 スモーク用)。
使い方: python3 make_rightsize_ss.py results-mix-cpu3b.csv rightsize-ss-k3.csv
"""
import sys, csv, statistics as st

src, out = sys.argv[1:3]
BASE, REPS, DIV = 'b32v160', '1', 1.5
APPS = ['front-end', 'catalogue', 'carts', 'orders', 'payment', 'shipping', 'user', 'queue-master']
vals = {}
for r in csv.DictReader(open(src)):
    if r['point'] == BASE and r['replicas'] == REPS and r['deploy'] == r['container']:
        vals.setdefault(r['deploy'], []).append(float(r['usage_mc']))
with open(out, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['container', 'request_m'])
    for s in APPS:
        v = vals[s]; r = max(1, round(st.mean(v) / DIV))
        print('%-13s D1 = %6.1f m (sd %.1f, n=%d) / %.1f = %d m' % (s, st.mean(v), st.stdev(v), len(v), DIV, r), file=sys.stderr)
        w.writerow([s, r])
