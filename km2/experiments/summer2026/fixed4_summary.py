#!/usr/bin/env python3
"""FOSE2026 §3.1 予備実験 (台数4固定・HPA無し) の本文数値を fixed4-all-points.csv から再計算する。

fixed4-all-points.csv は results-fixed4.csv (基本帯 150--300, 3 サイクル) と
results-fixed4b.csv (飽和帯 350--450, cycle 1--6) を 1 点 1 行にまとめた表
(softirq[ms/周] = softirq[コア秒] / (目標レート[周/s] × 計測 **120** 秒) × 1000。
 fixed4 / fixed4b は warm 90 s / meas 120 s で実行した (fixed4.log 1 行目)。§4 本実験の 180/240 s とは別)。
飽和帯 350/400 には別走の cycle 7--12 (2026-09-10 17:26 JST、450 を含まない) が results-fixed4b.csv に
あるが、450 と一緒に測った cycle 1--6 に統一した (ユーザ判断 2026-09-13)。fixed4-all-points.csv は
その 6 サイクルだけを含む。

  - 基本帯: softirq[ms/周] の cycle 平均を分離と比べた削減率 → 本文「front3 17--23%，mega 43--51%」
  - 飽和帯 buy(450): 実測[周/s] の平均±標準偏差 → 本文「同居 約440，分離 359.6±22.9」
  - 取りこぼし窓: 基本帯で 0 か → 本文「3構成とも目標レートを達成」

使い方: python3 fixed4_summary.py   (summer2026/ で実行)
"""
import csv, collections, statistics as st

rows = list(csv.DictReader(open('fixed4-all-points.csv', encoding='utf-8')))
by = collections.defaultdict(list)
for r in rows:
    by[(r['構成'], int(r['目標[周/s]']))].append(r)

print("基本帯: softirq [ms/周] (cycle 平均) と分離比の削減率")
for rate in (150, 200, 250, 300):
    base = st.mean(float(r['softirq[ms/周]']) for r in by[('分離', rate)])
    line = f"  buy({rate}): 分離 {base:.3f}"
    for arm in ('front3', 'mega'):
        v = st.mean(float(r['softirq[ms/周]']) for r in by[(arm, rate)])
        line += f"  {arm} {v:.3f} (−{100*(1-v/base):.1f}%)"
    drops = sum(int(float(r['取りこぼし窓'])) for a in ('分離', 'front3', 'mega') for r in by[(a, rate)])
    print(line + f"   取りこぼし窓の合計 {drops}")

print("\n飽和帯: 実測スループット [周/s] (平均±sd, n) と取りこぼし窓>0 の回数")
for rate in (350, 400, 450):
    line = f"  buy({rate}):"
    for arm in ('分離', 'front3', 'mega'):
        v = [float(r['実測[周/s]']) for r in by[(arm, rate)]]
        nd = sum(1 for r in by[(arm, rate)] if float(r['取りこぼし窓']) > 0)
        line += f"  {arm} {st.mean(v):.1f}±{st.stdev(v):.1f} (n={len(v)}, 取りこぼし{nd}回)"
    print(line)
