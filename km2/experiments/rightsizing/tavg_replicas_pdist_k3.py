#!/usr/bin/env python3
"""pdist-k3 の台数を「時間の平均」(小数) で出す (2026-11-23)。損はここでは数えない。

各回: 計測窓 (t_rel 310–590 s) の 15 s ごとの current_replicas の平均 (記録は 18〜19 個)。
分離: サービスごとに 12 サイクルの平均と sd、各サイクルの値。
同居: 組 (同居 Pod) ごとに 3 サイクルの平均と sd、各サイクルの値。
  同居 Pod の台数は、ホスト Deployment の 1 つのコンテナの行で読む (analyze_pdist_k3.py の ARMS と同じ)。

使い方: python3 tavg_replicas_pdist_k3.py [同居] [分離]   既定 = pdistk3pair3 pdistk3sep3
出力: 標準出力 (tavg-replicas-pdistk3-3.txt に保存する) と tavg-replicas-pdistk3-3.csv (BOM 付き、1 行 = 区分 × 対象 × 配合)、
      §3 の損の計算表 loss-table-pdistk3-3.csv (BOM 付き、1 行 = 組 × 配合)
"""
import csv, collections, statistics as st, sys

PAIR = sys.argv[1] if len(sys.argv) > 1 else 'pdistk3pair3'
SEP = sys.argv[2] if len(sys.argv) > 2 else 'pdistk3sep3'
S = '/home/mizuki/ダウンロード/msa/km2/experiments/summer2026/'
LO, HI = 310, 590
MIXES = ['b100v0', 'b50v150', 'b50v300', 'b75v200', 'b0v300']
SVC = [('front', 'frontend'), ('catalog', 'productcatalogservice'), ('reco', 'recommendationservice'),
       ('currency', 'currencyservice'), ('cart', 'cartservice'), ('checkout', 'checkoutservice'),
       ('shipping', 'shippingservice'), ('payment', 'paymentservice'), ('email', 'emailservice'), ('ad', 'adservice')]
# 組 → (アーム, 同居 Pod の Deployment, 台数を読むコンテナ)。Δρ の小さい順
HOST = [('checkout+shipping', 'pairsP1b', 'checkoutservice', 'checkout'),
        ('front+catalog', 'pairsP3', 'frontend', 'server'),
        ('front+reco', 'pairsQ2', 'frontend', 'server'),
        ('front+catalog+reco', 'frontrecocatalog', 'frontend', 'server'),
        ('catalog+reco', 'pairsP1b', 'productcatalogservice', 'server'),
        ('front+currency', 'pairsQ1', 'frontend', 'server'),
        ('front+cart', 'pairsP2', 'frontend', 'server'),
        ('checkout+cart', 'pairsQ1', 'checkoutservice', 'checkout'),
        ('currency+checkout', 'pairsP3', 'checkoutservice', 'checkout'),
        ('catalog+checkout', 'pairsP2', 'productcatalogservice', 'server'),
        ('checkout+front', 'pairsQ3', 'frontend', 'checkout')]


def tavg(name):
    g = collections.defaultdict(list)
    for r in csv.DictReader(open(S + f'timeline-{name}.csv')):
        if r['current_replicas'] and r['container'] != '-' and LO <= float(r['t_rel']) <= HI:
            g[(r['cycle'], r['arm'], r['point'], r['deploy'], r['container'])].append(int(r['current_replicas']))
    return {k: st.mean(v) for k, v in g.items()}


def first_cont(t, cyc, arm, mix, dep):
    # 分離はサービスごとにコンテナが 1 つ (checkout/payment/email は名前が server でない) なので、どのコンテナでもよい
    for k, v in t.items():
        if k[:4] == (cyc, arm, mix, dep):
            return v


sep, par = tavg(SEP), tavg(PAIR)
rows = []


def block(title, items, ncyc):
    print(f'\n{title}')
    print('  平均台数 (各回の時間平均を、サイクルで平均)')
    print('  | 対象 | ' + ' | '.join(MIXES) + ' |')
    for name, vals in items:
        print(f'  | {name} | ' + ' | '.join(f'{st.mean(vals[m]):.2f}' for m in MIXES) + ' |')
    print(f'  小数になった所 (sd > 0) のサイクルごとの値 c1〜c{ncyc}')
    for name, vals in items:
        for m in MIXES:
            v = vals[m]
            if st.stdev(v) > 0:
                print(f'    {m:8} {name:20} 平均 {st.mean(v):.2f}  sd {st.stdev(v):.2f}  ' + ' '.join(f'{x:.2f}' for x in v))


cy = sorted({k[0] for k in sep}, key=int)
items = []
for sh, dep in SVC:
    vals = {m: [first_cont(sep, c, 'normal', m, dep) for c in cy] for m in MIXES}
    items.append((sh, vals))
    for m in MIXES:
        rows.append({'区分': '分離', '対象': sh, '配合': m, 'サイクル数': len(cy), '平均台数': round(st.mean(vals[m]), 3),
                     'sd': round(st.stdev(vals[m]), 3), **{f'c{c}': round(x, 3) for c, x in zip(cy, vals[m])}})
print(f'pdist-k3 3 回目の台数 (時間の平均)。窓 t_rel {LO}–{HI} s、15 s ごとの current_replicas の平均。同居 {PAIR}、分離 {SEP}')
block(f'§1 分離 ({len(cy)} サイクル、サービスごと)', items, len(cy))

cp = sorted({k[0] for k in par}, key=int)
items = []
for pair, arm, dep, ct in HOST:
    vals = {m: [par[(c, arm, m, dep, ct)] for c in cp] for m in MIXES}
    items.append((pair, vals))
    for m in MIXES:
        rows.append({'区分': '同居', '対象': pair, '配合': m, 'サイクル数': len(cp), '平均台数': round(st.mean(vals[m]), 3),
                     'sd': round(st.stdev(vals[m]), 3), **{f'c{c}': round(x, 3) for c, x in zip(cp, vals[m])}})
block(f'§2 同居 ({len(cp)} サイクル、同居 Pod ごと)', items, len(cp))

# §3 損の計算表 (2026-11-23 追加): 同居 3 回の平均台数と分離 12 回の平均台数の差に枠を掛けて足す。
# 損 = Σ_s r_s (n̄_同居 − n̄_分離,s) = n̄_同居 Σr − Σ r_s n̄_分離,s。平均どうしの差なので、回ごとの損の平均と一致する。
req = {(r['deploy'], r['container']): int(r['request_m']) for r in csv.DictReader(open('rightsize-pdist-k3-mc5.csv'))}
CONT = {'frontend': 'server', 'productcatalogservice': 'server', 'recommendationservice': 'server', 'currencyservice': 'server',
        'cartservice': 'server', 'checkoutservice': 'checkout', 'shippingservice': 'server'}
D = dict(SVC)
R = {sh: req[(D[sh], CONT[D[sh]])] for sh in D if D[sh] in CONT}
# ρ = ν/β (1 台、mix-cpu5、analysis-rho5.txt)。analyze_pdist_k3.py の RHO と同じ値。Δρ = メンバーどうしの差の最大
RHO = {'front': 0.3174, 'catalog': 0.3114, 'reco': 0.3246, 'currency': 0.2674, 'cart': 0.1864, 'checkout': 0.0076, 'shipping': 0.0027}
navg = {(r['区分'], r['対象'], r['配合']): r['平均台数'] for r in rows}
lrows = []
print('\n§3 損の計算 (同居 3 回の平均台数 − 分離 12 回の平均台数) × 枠 を足す [m]。プラス = 同居の損 (その側が余分に持たされた)')
print('  | 組 | Δρ | ρ (メンバー順) | 配合 | 同居の台数 | メンバー: 分離の台数 → 差 × 枠 = 内訳 | 損 |')
for pair, arm, dep, ct in HOST:
    mem = pair.split('+')
    drho = max(RHO[a] for a in mem) - min(RHO[a] for a in mem)
    for m in MIXES:
        nc = st.mean([par[(c, arm, m, dep, ct)] for c in cp])
        parts = []
        for s in mem:
            ns = st.mean([first_cont(sep, c, 'normal', m, D[s]) for c in cy])
            parts.append((s, ns, nc - ns, R[s], R[s] * (nc - ns)))
        loss = sum(x[4] for x in parts)
        print(f'  | {pair} | {drho:.3f} | ' + ' / '.join(f'{RHO[a]:.3f}' for a in mem) + f' | {m} | {nc:.2f} | ' + '; '.join(f'{s}: {ns:.2f} → {d:+.2f} × {r} = {v:+.0f}' for s, ns, d, r, v in parts) + f' | {loss:+.0f} |')
        d = {'組': pair, 'Δρ': round(drho, 4), **{f'ρ_{i}': RHO[a] for i, a in enumerate(mem, 1)}, '配合': m, '同居の平均台数': round(nc, 3)}
        for i, (s, ns, dd, r, v) in enumerate(parts, 1):
            d.update({f'メンバー{i}': s, f'分離の平均台数_{i}': round(ns, 3), f'差_{i}[台]': round(dd, 3), f'枠_{i}[m]': r, f'内訳_{i}[m]': round(v)})
        d['損[m]'] = round(loss)
        lrows.append(d)
lcols = []
for r in lrows:
    for c in r:
        if c not in lcols: lcols.append(c)
with open('loss-table-pdistk3-3.csv', 'w', newline='', encoding='utf-8-sig') as f:   # BOM 付き
    w = csv.DictWriter(f, fieldnames=lcols); w.writeheader(); w.writerows(lrows)

cols = []
for r in rows:
    for c in r:
        if c not in cols: cols.append(c)
with open('tavg-replicas-pdistk3-3.csv', 'w', newline='', encoding='utf-8-sig') as f:   # BOM 付き = Excel で文字化けしない
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
