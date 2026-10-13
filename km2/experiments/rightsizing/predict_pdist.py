#!/usr/bin/env python3
"""pdist 実験 (plan-pdist.md) の事前予測表を作る。同居実験の前にコミットして固定する。

入力:
  results-mix-cpu2.csv  分離・HPA無し・1台/2台固定の CPU 実測 (17 点 × 6 サイクル)。
  rightsize-pdist.csv   枠 r = D1(b50v150)/0.50。
需要 (モデルを使わない): D_s(n, m) = 点 m・n 台の usage_mc の全サイクル平均 (Deployment の Pod 合計)。
  b50v250 は測っていないので、同じ n の b50v150 と b50v300 から view について直線で内挿する (重み 1/3 : 2/3)。
  n ≥ 3 は外挿 D_n = D2 + (n−2)(D2 − D1) (predict_pairs.py と同じ)。
HPA: u = D_n/(n·r)、|u/0.70 − 1| ≤ 0.10 なら n のまま、外なら ceil(n·u/0.70) (min 1 / max 8)。
  同居 Pod は 2 コンテナの希望の最大。開始台数から固定点まで反復 (振動したら flag)。
出力列: pair, point, start, n_s, n_t, n_st, drag (あり/なし), dragged (引きずられた側。両方 n_st なら '-'),
  dn (引きずられた側の余分な台数), loss_m, u1_s, u1_t (1 台時の利用率), R1 (クラス規則の予想), flag
加えて「ワークロード成分」の表: 配合の範囲 W ごとの近さ M_W = max_{m∈W} |ln P_s(m) − ln P_t(m)| を標準出力に出す。

使い方: python3 predict_pdist.py > predictions-pdist.txt   (CSV は predictions-pdist.csv)
"""
import csv, collections, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
SH = {'frontend': 'front', 'productcatalogservice': 'catalog', 'recommendationservice': 'reco', 'adservice': 'ad',
      'currencyservice': 'currency', 'cartservice': 'cart', 'checkoutservice': 'checkout',
      'paymentservice': 'payment', 'shippingservice': 'shipping', 'emailservice': 'email'}
INV = {v: k for k, v in SH.items()}
BUY_ONLY = {'checkout', 'payment', 'shipping', 'email'}
PAIRS = [('front', 'ad', 'pairsP1'), ('checkout', 'shipping', 'pairsP1'), ('catalog', 'reco', 'pairsP1'),
         ('front', 'cart', 'pairsP2'), ('catalog', 'checkout', 'pairsP2'),
         ('front', 'catalog', 'pairsP3'), ('currency', 'checkout', 'pairsP3')]
POINTS = ['b100v0', 'b50v150', 'b50v300']   # 2026-10-13 ユーザ決定: 見る寄りは実測点 b50v300 (b50v250 案は不採用)
STARTS = [1, 2]
REF = 'b50v150'

acc = collections.defaultdict(list)
for r in csv.DictReader(open(os.path.join(HERE, 'results-mix-cpu2.csv'))):
    if r['deploy'] in SH:
        acc[(SH[r['deploy']], int(r['replicas']), r['point'])].append(float(r['usage_mc']))
D = {k: sum(v) / len(v) for k, v in acc.items()}
for s in SH.values():
    for n in (1, 2):
        D[(s, n, 'b100v0')] = D[(s, n, 'b100')]   # 測定の点名は b100 (= buy 100, view 0)
        D[(s, n, 'b50v250')] = D[(s, n, 'b50v150')] + (D[(s, n, 'b50v300')] - D[(s, n, 'b50v150')]) * 100 / 150
R = {SH[r['deploy']]: float(r['request_m']) for r in csv.DictReader(open(os.path.join(HERE, 'rightsize-pdist.csv')))
     if r['deploy'] in SH}


def Dn(s, n, p):
    d1, d2 = D[(s, 1, p)], D[(s, 2, p)]
    return d1 if n == 1 else d2 + (n - 2) * (d2 - d1)


def want(s, n, p):
    u = Dn(s, n, p) / (n * R[s]); q = u / 0.70
    return n if abs(q - 1) <= 0.10 else max(1, min(8, math.ceil(n * q)))


def settle(f, n0):
    n, seen = n0, []
    for _ in range(30):
        m = f(n)
        if m == n:
            return n, ''
        if m in seen:
            return max(n, m), '振動'
        seen.append(n); n = m
    return n, '収束せず'


rows = []
for s, t, arm in PAIRS:
    for p in POINTS:
        for n0 in STARTS:
            ns, f1 = settle(lambda n: want(s, n, p), n0)
            nt, f2 = settle(lambda n: want(t, n, p), n0)
            nst, f3 = settle(lambda n: max(want(s, n, p), want(t, n, p)), n0)
            dragged = [x for x, nx in ((s, ns), (t, nt)) if nx < nst]
            dn = max([nst - nx for nx in (ns, nt)])
            loss = nst * (R[s] + R[t]) - (ns * R[s] + nt * R[t])
            r1 = '損あり' if ((s in BUY_ONLY) != (t in BUY_ONLY)) and p.startswith('b100') else '損なし'
            rows.append(dict(pair=f'{s}+{t}', arm=arm, point=p, start=n0, n_s=ns, n_t=nt, n_st=nst,
                             drag='あり' if dragged else 'なし', dragged='/'.join(dragged) or '-', dn=dn,
                             loss_m=round(loss), u1_s=round(D[(s, 1, p)] / R[s], 3), u1_t=round(D[(t, 1, p)] / R[t], 3),
                             R1=r1, flag=' '.join(x for x in (f1, f2, f3) if x)))
with open(os.path.join(HERE, 'predictions-pdist.csv'), 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

print('事前予測 (枠 rightsize-pdist.csv、θ=0.50 基準 b50v150。点に b50v250 があればそれは内挿)')
print(f'{"pair":18} {"arm":8} {"point":8} 開始  n_s n_t n_st  引きずり 引きずられた側  Δn  損[m]  u1_s  u1_t  R1    flag')
for r in rows:
    print(f'{r["pair"]:18} {r["arm"]:8} {r["point"]:8} {r["start"]:3} {r["n_s"]:4} {r["n_t"]:3} {r["n_st"]:4}  {r["drag"]:6} '
          f'{r["dragged"]:14} {r["dn"]:3} {r["loss_m"]:6} {r["u1_s"]:5.2f} {r["u1_t"]:5.2f}  {r["R1"]:4} {r["flag"]}')
print('\n予測と R1 が食い違うセル (識別セル):')
for r in rows:
    if (r['drag'] == 'あり') != (r['R1'] == '損あり'):
        print(f'  {r["pair"]} {r["point"]} 開始{r["start"]}: 予測 引きずり{r["drag"]} / R1 {r["R1"]}')

# --- ワークロード成分: 配合の範囲 W ごとの近さ M_W ---
meas = sorted({k[2] for k in D if k[2] not in ('b50v250', 'b100v0')})
def bv(p):
    b = int(p[1:].split('v')[0]) if p.startswith('b') else 0
    v = int(p.split('v')[1]) if 'v' in p else 0
    return b, v
W = {
    '買い寄り (view/buy≤1)': [p for p in meas if bv(p)[0] > 0 and bv(p)[1] <= bv(p)[0]],
    '中間 (1<view/buy≤3)': [p for p in meas if bv(p)[0] > 0 and bv(p)[0] < bv(p)[1] <= 3 * bv(p)[0]],
    '見る寄り (view/buy>3)': [p for p in meas if bv(p)[0] > 0 and bv(p)[1] > 3 * bv(p)[0]],
    '全域 (buy>0)': [p for p in meas if bv(p)[0] > 0],
}
print('\nワークロード成分ごとの近さ M_W (1 台、P は b50v150 で正規化。ln(0.77/0.50) = %.2f が 1 台→2 台の境目の目安)' % math.log(0.77 / 0.50))
for k, v in W.items():
    print(f'  {k}: {" ".join(v)}')
print(f'{"pair":18} ' + ' '.join(f'{k[:6]:>8}' for k in W))
for s, t, _ in PAIRS:
    lp = lambda p: math.log(D[(s, 1, p)] / D[(s, 1, REF)]) - math.log(D[(t, 1, p)] / D[(t, 1, REF)])
    print(f'{s+"+"+t:18} ' + ' '.join(f'{max(abs(lp(p)) for p in v):8.2f}' for v in W.values()))
