#!/usr/bin/env python3
"""プレゼン用: pdist-k3 3 回目の「分離 c3 (代表サイクル)」と「同居の全回」を 1 つの CSV にまとめる (2026-11-23)。

1 行 = 分離 c3 の 1 配合 (5 行) または 同居の 1 組 × 1 配合 × 1 周 (165 行)。
  - 分離の行の窓内の変化は sep_cycles_pdist_k3.py の出力 sep-cycles-pdistk3-3.csv から。
  - 判定の列 (同居の台数・引きずり・損・窓内の動き …) は detail_pdist_k3.py の出力 detail-pdistk3-3.csv から。
  - 窓内の台数 (Deployment ごと) は timeline から、analyze_pdist_k3.py と同じ規則 (窓 310–590 s の最頻値、同数なら大きい方)。
    同居の行では、同居 Pod の Deployment の列がその Pod の台数 (例: pairsP2 の frontend = front+cart の Pod)。
  - 測定値の列 (予約枠・遅延・CPU 秒 …) は results-<名前>.csv と -times.csv の全列。同じアームの 2 組は 1 回の測定を共有するので同じ値。
分離 c3 を代表に選んだ理由: ペアの 7 サービス × 5 配合の台数が 12 回の最頻値と全部一致し、payment も一致 (sep-cycles-pdistk3-3.md)。

使い方: python3 present_pdist_k3.py [分離の周]   既定 = 3。出力 present-pdistk3-3.csv (BOM 付き)
"""
import csv, collections, sys

CYC = sys.argv[1] if len(sys.argv) > 1 else '3'
S = '/home/mizuki/ダウンロード/msa/km2/experiments/summer2026/'
SEP, PAIR = 'pdistk3sep3', 'pdistk3pair3'
OUT = 'present-pdistk3-3.csv' if CYC == '3' else f'present-pdistk3-3-c{CYC}.csv'
LO, HI = 310, 590
MIXES = ['b100v0', 'b50v150', 'b50v300', 'b75v200', 'b0v300']
DEPS = ['frontend', 'productcatalogservice', 'recommendationservice', 'currencyservice', 'cartservice',
        'checkoutservice', 'shippingservice', 'paymentservice', 'emailservice', 'adservice', 'redis-cart']
# 測定値の列のうち主なものに日本語の名前を付ける (残りは元の列名のまま)
JA = {'reserved_avg_cores': '予約枠の窓平均[コア]', 'p50': '購入p50[ms]', 'p99': '購入p99[ms]',
      'browse_p50': '閲覧p50[ms]', 'browse_p99': '閲覧p99[ms]', 'target_rate': '購入の目標[周/s]',
      'iter_rate': '購入の実績[周/s]', 'browse_rate_target': '閲覧の目標[周/s]', 'browse_rate': '閲覧の実績[周/s]',
      'dropped_win': '購入の取りこぼし(窓)', 'browse_dropped_win': '閲覧の取りこぼし(窓)',
      'failed_rate': '購入の失敗率', 'browse_failed_rate': '閲覧の失敗率', 'node_cpu_sec': 'ノードCPU秒(窓)',
      'softirq_cpu_sec': 'softirq CPU秒(窓)', 'k6_cpu_sec': 'k6 CPU秒(窓)', 'running_cores': '動作中の枠[コア]',
      'pods': 'Pod数', 'freq_ghz': '平均周波数[GHz]', 'temp_max_c': '最高温度[℃]'}
SKIP_TIMES = {'cycle', 'arm', 'point', 'start_replicas', 'target_rate', 'browse_rate'}


def mode(xs):
    c = collections.Counter(xs)
    return max(c, key=lambda n: (c[n], n)) if xs else ''


def replicas(name):
    ser = collections.defaultdict(list)
    for r in csv.DictReader(open(S + f'timeline-{name}.csv')):
        if r['current_replicas'] and LO <= float(r['t_rel']) <= HI:
            # 同居 Pod は Deployment に複数コンテナ行があるが current_replicas は同じ。'-' 行は redis-cart 用
            if r['container'] != '-' or r['deploy'] == 'redis-cart':
                ser[(r['cycle'], r['arm'], r['point'], r['deploy'], r['container'])].append(int(r['current_replicas']))
    out = collections.defaultdict(dict)
    for (c, a, p, d, ct), v in ser.items():
        out[(c, a, p)].setdefault(d, mode(v))
    return out


def measures(name):
    res = {(x['cycle'], x['arm'], x['point']): x for x in csv.DictReader(open(S + f'results-{name}.csv'))}
    tim = {(x['cycle'], x['arm'], x['point']): x for x in csv.DictReader(open(S + f'results-{name}-times.csv'))}
    return res, tim


def meas_cols(r, t):
    d = {}
    for k, v in r.items():
        if k in ('cycle', 'arm', 'point'):
            continue
        d[JA.get(k, k)] = v
    for k, v in t.items():
        if k not in SKIP_TIMES:
            d[JA.get(k, 'times_' + k)] = v
    return d


sepc = {(x['周'], x['配合']): x for x in csv.DictReader(open('sep-cycles-pdistk3-3.csv', encoding='utf-8-sig'))}
rows = []
rs, ts = measures(SEP); rp = replicas(SEP)
for mix in MIXES:
    k = (CYC, 'normal', mix)
    d = {'区分': f'分離 c{CYC}', 'アーム': 'normal', '組': '', 'メンバー(順)': '', 'Δρ': '', '配合': mix, '周': CYC}
    d.update({f'窓内の台数_{x}': rp[k].get(x, '') for x in DEPS})
    sc = sepc[(CYC, mix)]   # 分離の窓内の変化と最頻値との違いは sep_cycles_pdist_k3.py の出力から
    d['窓内の台数変化'] = sc['窓内の台数変化']; d['分離: 12 回の最頻値と違う(ペアの7サービス)'] = sc['最頻値と違う(ペアの7サービス)']
    d['_meas'] = meas_cols(rs[k], ts[k])
    rows.append(d)

rs, ts = measures(PAIR); rp = replicas(PAIR)
ARM = {'checkout+shipping': 'pairsP1b', 'catalog+reco': 'pairsP1b', 'front+cart': 'pairsP2', 'catalog+checkout': 'pairsP2',
       'front+catalog': 'pairsP3', 'currency+checkout': 'pairsP3', 'front+currency': 'pairsQ1', 'checkout+cart': 'pairsQ1',
       'front+reco': 'pairsQ2', 'checkout+front': 'pairsQ3', 'front+catalog+reco': 'frontrecocatalog'}
det = list(csv.DictReader(open('detail-pdistk3-3.csv', encoding='utf-8-sig')))
for x in det:
    arm = ARM[x['組']]; k = (x['周'], arm, x['配合'])
    d = {'区分': '同居', 'アーム': arm}
    d.update(x)
    d.update({f'窓内の台数_{y}': rp[k].get(y, '') for y in DEPS})
    d['_meas'] = meas_cols(rs[k], ts[k])
    rows.append(d)

# 列: 識別 → 判定 (detail の列) → 窓内の台数 → 測定値
cols = []
for r in rows:
    for c in r:
        if c != '_meas' and c not in cols:
            cols.append(c)
mcols = []
for r in rows:
    for c in r['_meas']:
        if c not in mcols:
            mcols.append(c)
with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:   # BOM 付き = Excel で文字化けしない
    w = csv.writer(f)
    w.writerow(cols + mcols)
    for r in rows:
        w.writerow([r.get(c, '') for c in cols] + [r['_meas'].get(c, '') for c in mcols])
print(f'{len(rows)} 行 ({sum(r["区分"] != "同居" for r in rows)} 分離 + {sum(r["区分"] == "同居" for r in rows)} 同居)、{len(cols) + len(mcols)} 列 → {OUT}')
