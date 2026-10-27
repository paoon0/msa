#!/usr/bin/env python3
"""限界 (OB: km2/experiments/rightsizing/measure-limit.sh、Sock Shop: sockshop/experiments/measure-limit.sh の CSV) を出す (2026-10-19)。

限界 = 取りこぼし (窓) が 目標×計測秒 の 1% 以下に収まる、いちばん高い段。
  サイクルごとに、下から順に見て初めて 1% を超えた段の 1 つ手前 (下の段がすべて 1% 以下であること)。
  1 段目から超えたら「下限未満」、最後まで超えなければ「最上段以上」と出す。複数サイクルなら中央値。
各段のボトルネック候補の CPU (使用量の上位 2 サービス)、ノード全体の CPU、k6 の CPU、p99 も並べる。
無効な段 (判定から外す): k6 の CPU が 1800m 超 (上限 2000m。k6 側が詰まった疑い) か、どれかのサービスの絞りが 5% 超
  (CPU 上限が先に効いていて、アプリの限界ではない)。無効な段で打ち切られていたら、限界は「判定不能」と出す。

使い方: python3 analyze_limit.py results-limit-coarse.csv [MEAS=120]     (OB も Sock Shop も同じ)
"""
import csv, sys, collections, statistics
PATH = sys.argv[1]
MEAS = float(sys.argv[2]) if len(sys.argv) > 2 else 120.0
LIM = 1.0
rows = [r for r in csv.DictReader(open(PATH)) if r['replicas'] == '1']   # 限界は 1 台で測る
pt = collections.OrderedDict()     # (cycle, point) -> info
for r in rows:
    k = (r['cycle'], r['point'])
    d = pt.setdefault(k, dict(b=float(r['buy_target']), v=float(r['view_target']), cpu={}))
    d['drop'] = max(float(r['buy_dropped_win'] or 0) / (d['b'] * MEAS) * 100 if d['b'] else 0,
                    float(r['view_dropped_win'] or 0) / (d['v'] * MEAS) * 100 if d['v'] else 0)
    d['p99'] = r['buy_p99'] if d['b'] else r['view_p99']
    d['node'] = r['node_cores']; d['temp'] = r['temp_max_c']
    d['cpu'][r['deploy']] = float(r['usage_mc'])
    if r['deploy'] != 'k6load':
        d['thr'] = max(d.get('thr', 0.0), float(r['throttle_pct'] or 0))
print(f"# 限界 ({PATH}、計測 {MEAS:.0f} s、基準 = 取りこぼし {LIM}% 以下)\n")
lims = collections.defaultdict(list)
for kind in ('buy', 'view'):
    print(f"## {'購入だけ' if kind == 'buy' else '閲覧だけ'}")
    print(f"{'cycle':>5} {'段':>6} {'取りこぼし%':>10} {'p99[ms]':>8}  {'CPU 上位 2 サービス [m]':<34} {'絞り最大%':>8} {'ノード[コア]':>11} {'k6[m]':>7} {'温度':>5}")
    for c in sorted({k[0] for k in pt}, key=int):
        steps = sorted([(d['b'] if kind == 'buy' else d['v'], k, d) for k, d in pt.items()
                        if k[0] == c and ((d['b'] > 0) == (kind == 'buy')) and ((d['v'] > 0) == (kind == 'view'))])
        if not steps:
            continue
        last_ok, verdict = None, None
        for x, k, d in steps:
            cp = d['cpu']
            top = sorted(((m, n) for n, m in cp.items() if n != 'k6load'), reverse=True)[:2]
            bad = cp.get('k6load', 0) > 1800 or d.get('thr', 0) > 5.0
            print(f"{c:>5} {k[1]:>6} {d['drop']:10.3f} {float(d['p99'] or 0):8.0f}  "
                  f"{', '.join(f'{n} {m:.0f}' for m, n in top):<34} {d.get('thr', 0):8.1f} {float(d['node'] or 0):11.2f} "
                  f"{cp.get('k6load', 0):7.0f} {d['temp']:>5}{'  ← 無効 (k6 か絞り)' if bad else ''}")
            if verdict is None and bad:
                verdict = f'判定不能 ({k[1]} が無効)'
            elif verdict is None:
                if d['drop'] > LIM:
                    verdict = last_ok if last_ok is not None else f'< {x:g} (最下段で超過)'
                else:
                    last_ok = x
        if verdict is None:
            verdict = f'>= {last_ok:g} (最上段まで超えず)'
        print(f"  → cycle {c} の限界: {verdict}")
        lims[kind].append(verdict)
    nums = [x for x in lims[kind] if isinstance(x, float)]
    if nums and len(nums) == len(lims[kind]):
        print(f"  ⇒ 限界 (中央値、{len(nums)} サイクル): {statistics.median(nums):g} 周/秒  各サイクル {nums}")
    print()
