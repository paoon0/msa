#!/usr/bin/env python3
"""台数を増やした点で、Pod ごとに負荷が乗っているかを確かめる (2026-11-20)。

CPU は -raw.csv の生カウンタから出す: Pod ごとに、計測窓の中の最初と最後のサンプルの
(累積 CPU 秒の差 ÷ 時刻差)。Prometheus の rate() は窓の端の間隔で過小に出るので使わない。
各 (サイクル, 点, 台数, サービス) で、Pod の CPU の 最大/最小 と 最小/平均 を出し、
最小/平均 < 0.5 (= 負荷がほぼ乗っていない Pod がある) の点を一覧にする。
アイドルに近いサービス (平均 < 30m) は比が意味を持たないので除く。

使い方: python3 check_pod_balance.py results-mix-cpu5   (拡張子なしのベース名。-raw.csv と -times.csv を読む)
"""
import csv, sys, collections, statistics as st

base = sys.argv[1]
raw = list(csv.DictReader(open(base + '-raw.csv')))
tim = {(x['cycle'], x['point'], x['replicas']): x for x in csv.DictReader(open(base + '-times.csv'))}

g = collections.defaultdict(list)   # (cycle, point, replicas, deploy, pod) -> [(t, cpu秒)]
for y in raw:
    if y['deploy'] in ('k6load', 'redis-cart'):   # redis-cart は設計上いつも 1 台 (measure-mix-cpu.sh:45)
        continue
    g[(y['cycle'], y['point'], y['replicas'], y['deploy'], y['pod'])].append((float(y['t_unix']), float(y['cpu_seconds_total'])))

pod_mc = collections.defaultdict(dict)   # (cycle, point, replicas, deploy) -> {pod: m}
for k, v in g.items():
    if len(v) < 2:
        continue
    v.sort()
    pod_mc[k[:4]][k[4]] = pod_mc[k[:4]].get(k[4], 0) + 1000 * (v[-1][1] - v[0][1]) / (v[-1][0] - v[0][0])

rows = []
for k, pods in sorted(pod_mc.items()):
    n = int(k[2])
    if n < 2:
        continue
    vals = list(pods.values()); m = st.mean(vals)
    if m < 30:
        continue
    rows.append((k, len(vals), n, max(vals) / min(vals) if min(vals) > 0 else float('inf'), min(vals) / m, vals))

print(f'台数 2 以上の点: {len(rows)} 件 (平均 30m 未満のサービスは除外)')
miss = [r for r in rows if r[1] != r[2]]
print(f'Pod 数が台数と合わない点: {len(miss)} 件')
for r in miss[:10]:
    print('  ', r[0], f'Pod {r[1]} / 台数 {r[2]}')
print('\nサービス別 最大/最小 (中央値 / 最大)、最小/平均 < 0.5 の件数')
by = collections.defaultdict(list)
for r in rows:
    by[r[0][3]].append(r)
for s, rs in sorted(by.items()):
    mm = [r[3] for r in rs]
    print(f'  {s:24} 中央値 {st.median(mm):5.2f}  最大 {max(mm):6.2f}  負荷の乗らない Pod {sum(1 for r in rs if r[4] < 0.5)}/{len(rs)}')
bad = [r for r in rows if r[4] < 0.5]
if bad:
    print('\n負荷がほぼ乗っていない Pod がある点:')
    for r in bad:
        print('  ', r[0], ' '.join(f'{x:.0f}' for x in sorted(r[5], reverse=True)), 'm')
