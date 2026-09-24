#!/usr/bin/env python3
"""FOSE2026 §3「単一ノードではバイト量がほとんど変わらない (実測 +2--4%)」を results-icter-affinity.csv から再計算する。

ICTer 2022 の affinity = サービス間で実際に流れた総バイト量 (カプセル化ヘッダ込み) を、
Pod の netns の /proc/net/dev (デバイス層 = ヘッダ込み) で測ったもの。
  - eth0 経由 = bridge (veth) を通る Pod 間通信、lo 経由 = 同居 Pod 内の loopback 通信
  - 全 Pod の eth0 受信バイトには k6→frontend のクライアント辺が混ざるので、k6 Pod の送信バイト
    (cAdvisor から取得、CSV の pod=k6load 行) を差し引く。受信側で引くのは、送信側 (k6 受信 32kB/周)
    より小さい量 (1.6kB/周) を引く方が窓ずれの誤差に強いため。
  - 1周あたりに直すには iters (k6 の実測レート [周/s]) × meas [秒] で割る。
  - affinity = (Σ eth0 受信 − k6 送信) + Σ lo 受信   … lo は片方向だけ数える (送受信が同じ量なので)

使い方: python3 icter_affinity_summary.py   (km2/experiments/ で実行)
"""
import csv, collections, statistics as st

rows = list(csv.DictReader(open('results-icter-affinity.csv', encoding='utf-8'),
                           fieldnames=['cycle', 'arm', 'pod', 'iface', 'rx_bytes', 'tx_bytes',
                                       'rx_pkts', 'tx_pkts', 'iters', 'meas']))
per = collections.defaultdict(lambda: collections.defaultdict(float))   # (arm,cycle) -> 集計
for r in rows:
    if r['cycle'] == 'cycle':
        continue
    k = (r['arm'], r['cycle'])
    n_iter = float(r['iters']) * float(r['meas'])
    per[k]['iters'] = n_iter
    if r['pod'].startswith('k6load'):
        per[k]['k6_tx'] += float(r['tx_bytes']); per[k]['k6_txp'] += float(r['tx_pkts'])
    elif r['iface'] == 'eth0':
        per[k]['eth_rx'] += float(r['rx_bytes']); per[k]['eth_rxp'] += float(r['rx_pkts'])
    elif r['iface'] == 'lo':
        per[k]['lo_rx'] += float(r['rx_bytes']); per[k]['lo_rxp'] += float(r['rx_pkts'])

res = collections.defaultdict(list)
for (arm, cyc), d in sorted(per.items()):
    n = d['iters']
    bridge = (d['eth_rx'] - d['k6_tx']) / n
    lo = d['lo_rx'] / n
    pk = (d['eth_rxp'] - d['k6_txp'] + d['lo_rxp']) / n
    res[arm].append((bridge, lo, bridge + lo, pk))

base = st.mean(x[2] for x in res['normal'])
print(f"{'構成':8s} {'bridge[B/周]':>12s} {'loopback[B/周]':>14s} {'合計=affinity':>14s} {'normal比':>8s} {'パケット/周':>10s}")
for arm in ('normal', 'front3', 'mega'):
    b, l, t, p = (st.mean(x[i] for x in res[arm]) for i in range(4))
    print(f"{arm:8s} {b:12.0f} {l:14.0f} {t:14.0f} {100*(t/base-1):+7.1f}% {p:10.1f}   (n={len(res[arm])})")
