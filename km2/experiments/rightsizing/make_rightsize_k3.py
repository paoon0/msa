#!/usr/bin/env python3
"""基準の配合で 3 台になる枠の表を作る (plan-pdist-k3.md 2 節の式、2026-11-04 スクリプト化)。

枠 r = D1 / 1.5。D1 = 結果 CSV の point=b50v150・replicas=1 の usage_mc の全サイクル平均。
ad は 800m、redis-cart は 300m の決め打ち (計画どおり)。
使い方: python3 make_rightsize_k3.py <結果 CSV> <出力 CSV>
  例: python3 make_rightsize_k3.py results-mix-cpu2.csv /dev/stdout  → rightsize-pdist-k3.csv と一致することを確認済み
"""
import sys, csv, statistics as st

src, out = sys.argv[1:3]
BASE, REPS, DIV = 'b50v150', '1', 1.5
ORDER = [('frontend', 'server'), ('checkoutservice', 'checkout'), ('cartservice', 'server'),
         ('productcatalogservice', 'server'), ('currencyservice', 'server'), ('paymentservice', 'payment'),
         ('shippingservice', 'server'), ('emailservice', 'email'), ('recommendationservice', 'server')]
FIXED = [('adservice', 'server', 800), ('redis-cart', 'redis', 300)]

vals = {}
for r in csv.DictReader(open(src)):
    if r['point'] == BASE and r['replicas'] == REPS:
        vals.setdefault((r['deploy'], r['container']), []).append(float(r['usage_mc']))

with open(out, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['deploy', 'container', 'request_m'])
    for k in ORDER:
        v = vals[k]
        r = round(st.mean(v) / DIV)
        print('%-24s D1 = %6.1f m (sd %.1f, n=%d) / %.1f = %d m' % (k[0], st.mean(v), st.stdev(v), len(v), DIV, r), file=sys.stderr)
        w.writerow([k[0], k[1], r])
    for d, c, m in FIXED:
        w.writerow([d, c, m])
