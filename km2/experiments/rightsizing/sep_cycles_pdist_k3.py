#!/usr/bin/env python3
"""pdist-k3 分離の 12 サイクルを 1 回ずつ並べる (2026-11-23、プレゼンで説明するサイクルを選ぶため)。

ペアの表の「分離の台数」は 1 つのサイクルではなく、12 回の窓内台数の最頻値 (analyze_pdist_k3.py と同じ規則:
窓 t_rel 310–590 s の current_replicas の最頻値、同数なら大きい方)。ここでは各サイクルの台数がその最頻値と
一致するか、窓の中で台数が動いたか、を (サイクル, 配合) ごとに出し、最頻値に最も近いサイクルを順位付けする。

使い方: python3 sep_cycles_pdist_k3.py [分離の名前] [出力の頭]   既定 = pdistk3sep3 sep-cycles-pdistk3-3
出力: <頭>.csv (BOM 付き、(サイクル, 配合) ごと 1 行) と <頭>.md (順位と表)
"""
import csv, collections, datetime, sys

SEP = sys.argv[1] if len(sys.argv) > 1 else 'pdistk3sep3'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'sep-cycles-pdistk3-3'
S = '/home/mizuki/ダウンロード/msa/km2/experiments/summer2026/'
LO, HI = 310, 590
MIXES = ['b100v0', 'b50v150', 'b50v300', 'b75v200', 'b0v300']
# ペアに出てくる 7 サービス (判定に使う) と、それ以外 (参考)
PAIRSVC = [('front', 'frontend'), ('catalog', 'productcatalogservice'), ('reco', 'recommendationservice'),
           ('currency', 'currencyservice'), ('cart', 'cartservice'), ('checkout', 'checkoutservice'),
           ('shipping', 'shippingservice')]
OTHER = [('payment', 'paymentservice'), ('email', 'emailservice'), ('ad', 'adservice')]
ALL = PAIRSVC + OTHER


def mode(xs):
    c = collections.Counter(xs)
    return max(c, key=lambda n: (c[n], n))


ser = collections.defaultdict(list)   # (cyc, mix, deploy) → [(t, n, ready)]
for r in csv.DictReader(open(S + f'timeline-{SEP}.csv')):
    if r['container'] == '-' or not r['current_replicas']:
        continue
    ser[(r['cycle'], r['point'], r['deploy'])].append((float(r['t_rel']), int(r['current_replicas']), int(r['ready_replicas'] or 0)))
res = {(x['cycle'], x['point']): x for x in csv.DictReader(open(S + f'results-{SEP}.csv'))}
trun = {(x['cycle'], x['point']): float(x['t_run']) for x in csv.DictReader(open(S + f'results-{SEP}-times.csv'))}
fs = collections.defaultdict(list)
for e in csv.DictReader(open(S + f'events-{SEP}.csv')):
    if 'nsufficient' not in e['message']:
        continue
    k = (e['cycle'], e['point'])
    if k in trun:
        t = datetime.datetime.fromisoformat(e['time'].replace('Z', '+00:00')).timestamp() - trun[k]
        fs[k].append(f"{e['object'].split('-')[0]}@{t:.0f}s")

cycles = sorted({k[0] for k in ser}, key=int)
n = {}      # (cyc, mix, short) → 窓内台数
chg = {}    # (cyc, mix, short) → 窓内の変化の文字列
for cyc in cycles:
    for mix in MIXES:
        for sh, dep in ALL:
            s = sorted(ser[(cyc, mix, dep)])
            w = [x for x in s if LO <= x[0] <= HI]
            n[(cyc, mix, sh)] = mode([x[1] for x in w])
            pre = [x for x in s if x[0] < LO]
            last = pre[-1][1] if pre else None
            c = []
            for t, k, _ in w:
                if last is not None and k != last:
                    c.append(f'{t:.0f}s {last}→{k}')
                last = k
            chg[(cyc, mix, sh)] = c
md = {(mix, sh): mode([n[(c, mix, sh)] for c in cycles]) for mix in MIXES for sh, _ in ALL}

rows, score = [], {}
for cyc in cycles:
    off = 0; moved = 0
    for mix in MIXES:
        r = res[(cyc, mix)]
        d = {'周': cyc, '配合': mix}
        miss = []
        for sh, _ in ALL:
            v = n[(cyc, mix, sh)]
            mark = '' if v == md[(mix, sh)] else f'({md[(mix, sh)]})'
            d[sh] = f'{v}{mark}'
            if sh in dict(PAIRSVC) and mark:
                miss.append(f'{sh} {v}≠{md[(mix, sh)]}')
        mv = [f'{sh}: ' + ', '.join(chg[(cyc, mix, sh)]) for sh, _ in ALL if chg[(cyc, mix, sh)]]
        mvp = [m for m in mv if m.split(':')[0] in dict(PAIRSVC)]
        off += len(miss); moved += len(mvp)
        d.update({'最頻値と違う(ペアの7サービス)': ', '.join(miss), '窓内の台数変化': ' / '.join(mv),
                  '予約枠の平均[コア]': f"{float(r['reserved_avg_cores']):.3f}",
                  '購入p50/p99[ms]': f"{float(r['p50']):.0f}/{float(r['p99']):.0f}",
                  '閲覧p50/p99[ms]': f"{float(r['browse_p50']):.0f}/{float(r['browse_p99']):.0f}" if r['browse_p50'] else '',
                  '取りこぼし(窓)': r['dropped_win'], '失敗率': r['failed_rate'],
                  '載らないPod(t_rel)': ', '.join(fs.get((cyc, mix), []))})
        rows.append(d)
    score[cyc] = (off, moved)

cols = list(rows[0].keys())
with open(OUT + '.csv', 'w', newline='', encoding='utf-8-sig') as f:   # BOM 付き = Excel で文字化けしない
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
with open(OUT + '.md', 'w') as f:
    f.write(f'# pdist-k3 3 回目 分離 12 サイクルの詳細\n\n生成: `python3 sep_cycles_pdist_k3.py {SEP} {OUT}` (入力 `../summer2026/timeline-{SEP}.csv`、'
            f'`../summer2026/results-{SEP}.csv`、`-times.csv`、`events-{SEP}.csv`)。台数 = 窓 t_rel {LO}–{HI} s の最頻値。'
            '括弧 = 12 回の最頻値 (違うときだけ)。\n\n## 12 回の最頻値 (ペアの表の「分離の台数」)\n\n')
    f.write('| 配合 | ' + ' | '.join(sh for sh, _ in ALL) + ' |\n|' + '---|' * (len(ALL) + 1) + '\n')
    for mix in MIXES:
        f.write(f'| {mix} | ' + ' | '.join(str(md[(mix, sh)]) for sh, _ in ALL) + ' |\n')
    f.write('\n## サイクルの順位 (ペアの 7 サービス × 5 配合 = 35 セルのうち最頻値と違う数、窓内で台数が動いた数)\n\n| 周 | 最頻値と違う | 窓内で動いた |\n|---|---|---|\n')
    for cyc in sorted(cycles, key=lambda c: (score[c], int(c))):
        f.write(f'| c{cyc} | {score[cyc][0]}/35 | {score[cyc][1]} |\n')
    f.write('\n## 全行\n\n| ' + ' | '.join(cols) + ' |\n|' + '---|' * len(cols) + '\n')
    for r in rows:
        f.write('| ' + ' | '.join(str(r[c]) for c in cols) + ' |\n')
for cyc in sorted(cycles, key=lambda c: (score[c], int(c))):
    print(f'c{cyc}: 最頻値と違う {score[cyc][0]}/35  窓内で動いた {score[cyc][1]}')
print(f'{len(rows)} 行 → {OUT}.csv, {OUT}.md')
