#!/usr/bin/env python3
"""pdist-k3 本走の解析 (plan-pdist-k3.md §5 のとおり)。予測の的中率は出さない。

入力: summer2026/results-<NAME>.csv, timeline-<NAME>.csv (NAME 既定 pdistk3)、rightsizing/<枠表> (既定 rightsize-pdist-k3.csv)
計測窓 = t_rel ∈ [180, 420] s。

主判定 (同じ Pod の中で): サンプルごとに 希望 = n (|u/70 − 1| ≤ 0.1) / ceil(n·u/70) (1〜HPA_MAX)、
  窓内の最頻値 < n_st (窓内の current_replicas の最頻値) → 引きずられた。Δn = n_st − 希望。
副判定 (分離との比較): 同じサイクル・点・開始台数の normal の台数 n_x (最頻値)。n_x < n_st → 引きずられた。
  Δn' = n_st − n_x、損 = n_st(r_s + r_t) − (n_s r_s + n_t r_t) [m]。
印: 取りこぼし (窓) が目標周回数 × 240 s の 1% 超、Pending、Ready 落ち (窓内、そのペアのホスト Deployment / normal 側の 2 サービス)。

使い方: python3 analyze_pdist_k3.py [NAME] [枠表] > analysis-<NAME>.txt
"""
import csv, collections, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
S26 = os.path.join(HERE, '..', 'summer2026')
NAME = sys.argv[1] if len(sys.argv) > 1 else 'pdistk3'
TABLE = sys.argv[2] if len(sys.argv) > 2 else 'rightsize-pdist-k3.csv'
WARM, MEAS, HPA_MAX = 180, 240, 12
LO, HI = WARM, WARM + MEAS

# アーム → [(ペア名, ホスト Deployment, {コンテナ名: 短縮名}, (s, t))]
ARMS = {
    'pairsP1b': [('checkout+shipping', 'checkoutservice', {'checkout': 'checkout', 'shipping': 'shipping'}, ('checkout', 'shipping')),
                 ('catalog+reco', 'productcatalogservice', {'server': 'catalog', 'recommendation': 'reco'}, ('catalog', 'reco'))],
    'pairsP2': [('front+cart', 'frontend', {'server': 'front', 'cartservice': 'cart'}, ('front', 'cart')),
                ('catalog+checkout', 'productcatalogservice', {'server': 'catalog', 'checkout': 'checkout'}, ('catalog', 'checkout'))],
    'pairsP3': [('front+catalog', 'frontend', {'server': 'front', 'productcatalog': 'catalog'}, ('front', 'catalog')),
                ('currency+checkout', 'checkoutservice', {'checkout': 'checkout', 'currency': 'currency'}, ('currency', 'checkout'))],
    'pairsQ1': [('front+currency', 'frontend', {'server': 'front', 'currency': 'currency'}, ('front', 'currency')),
                ('checkout+cart', 'checkoutservice', {'checkout': 'checkout', 'cartservice': 'cart'}, ('checkout', 'cart'))],
    'pairsQ2': [('front+reco', 'frontend', {'server': 'front', 'recommendation': 'reco'}, ('front', 'reco'))],
    'pairsQ3': [('checkout+front', 'frontend', {'checkout': 'checkout', 'server': 'front'}, ('checkout', 'front'))],
}
# ρ (analysis-rho2.txt、1 台・全 17 点) と通信量 (edge-traffic、購入 100 のときのヘッダ込みバイト量の割合)
RHO = {'front': 0.35, 'catalog': 0.34, 'reco': 0.36, 'currency': 0.26, 'cart': 0.18, 'checkout': -0.02, 'shipping': -0.02}
TRAFFIC = {'checkout+shipping': 3.7, 'catalog+reco': 18.4, 'front+cart': 4.1, 'catalog+checkout': 2.3, 'front+catalog': 38.8,
           'currency+checkout': 2.6, 'front+currency': 8.5, 'checkout+cart': 2.7, 'front+reco': 4.8, 'checkout+front': 2.5}
DEP = {'front': 'frontend', 'catalog': 'productcatalogservice', 'reco': 'recommendationservice', 'currency': 'currencyservice',
       'cart': 'cartservice', 'checkout': 'checkoutservice', 'shipping': 'shippingservice'}
POINTS = ['b100v0', 'b50v150', 'b50v300']

R = {r['deploy']: float(r['request_m']) for r in csv.DictReader(open(os.path.join(HERE, TABLE)))}
res = {(r['cycle'], r['arm'], r['point'], r['start_replicas']): r
       for r in csv.DictReader(open(os.path.join(S26, f'results-{NAME}.csv')))}
tl = collections.defaultdict(list)
for r in csv.DictReader(open(os.path.join(S26, f'timeline-{NAME}.csv'))):
    if LO <= float(r['t_rel']) <= HI:
        tl[(r['cycle'], r['arm'], r['point'], r['start_replicas'])].append(r)
STARTS = sorted({k[3] for k in tl}, key=int)


def mode(xs):
    c = collections.Counter(xs); top = max(c.values())
    return max(k for k, v in c.items() if v == top)   # 同数なら大きい方


def want(n, u):
    q = u / 70.0
    return n if abs(q - 1) <= 0.10 else max(1, min(HPA_MAX, math.ceil(n * q)))


def series(rows, dep, cont):
    return sorted((float(r['t_rel']), int(r['current_replicas']), float(r['hpa_util_pct']))
                  for r in rows if r['deploy'] == dep and r['container'] == cont
                  and r['hpa_util_pct'] not in ('', None) and r['current_replicas'] not in ('', None))


def nrep(rows, dep):
    xs = [int(r['current_replicas']) for r in rows if r['deploy'] == dep and r['container'] != '-' and r['current_replicas']]
    return mode(xs) if xs else None


def marks(key, deps):
    r = res.get(key)
    if r is None:
        return ['結果なし']
    m = []
    b, v = float(r['target_rate']), float(r['browse_rate_target'] or 0)
    if float(r['dropped_win'] or 0) > 0.01 * b * MEAS:
        m.append('取りこぼし購入')
    if v > 0 and float(r['browse_dropped_win'] or 0) > 0.01 * v * MEAS:
        m.append('取りこぼし閲覧')
    rows = tl[key]
    if any(int(x['pending_pods'] or 0) > 0 for x in rows if x['deploy'] in deps):
        m.append('Pending')
    if any(x['current_replicas'] and int(x['ready_replicas'] or 0) < int(x['current_replicas'])
           for x in rows if x['deploy'] in deps and x['container'] != '-'):
        m.append('Ready落ち')
    return m


obs = []
for (cyc, arm, pt, n0), rows in sorted(tl.items()):
    if arm not in ARMS:
        continue
    nkey = (cyc, 'normal', pt, n0)
    for pair, dep, cmap, (s, t) in ARMS[arm]:
        nst = nrep(rows, dep)
        per = {}
        for cname, short in cmap.items():
            ser = series(rows, dep, cname)
            per[short] = dict(want=mode([want(n, u) for _, n, u in ser]), u=sum(u for *_, u in ser) / len(ser))
        dragged = [x for x in (s, t) if per[x]['want'] < nst]
        dn = max([nst - per[x]['want'] for x in (s, t)] + [0])
        ns_, nt_ = nrep(tl[nkey], DEP[s]), nrep(tl[nkey], DEP[t])
        ok2 = ns_ is not None and nt_ is not None
        dragged2 = [x for x, nx in ((s, ns_), (t, nt_)) if ok2 and nx < nst]
        dn2 = max([nst - nx for nx in (ns_, nt_)] + [0]) if ok2 else None
        loss = nst * (R[DEP[s]] + R[DEP[t]]) - (ns_ * R[DEP[s]] + nt_ * R[DEP[t]]) if ok2 else None
        mk = marks((cyc, arm, pt, n0), {dep}) + [f'normal:{x}' for x in marks(nkey, {DEP[s], DEP[t]})]
        obs.append(dict(cyc=cyc, arm=arm, pt=pt, n0=n0, pair=pair, s=s, t=t, nst=nst, ws=per[s]['want'], wt=per[t]['want'],
                        us=per[s]['u'], ut=per[t]['u'], dragged=dragged, dn=dn, ns=ns_, nt=nt_, dragged2=dragged2,
                        dn2=dn2, loss=loss, marks=mk))

ORDER = sorted(TRAFFIC, key=lambda p: (abs(RHO[p.split('+')[0]] - RHO[p.split('+')[1]]), -TRAFFIC[p]))
drho = lambda p: abs(RHO[p.split('+')[0]] - RHO[p.split('+')[1]])
print(f'pdist-k3 の解析 ({NAME}、枠 {TABLE})。窓 = t_rel 180–420 s')
print(f'観測: {len(obs)} (= 同居アームの回 × ペア)、開始台数 {STARTS}\n')

print('§1 対照 (b50v150) で各サービスが何台になったか (normal、全回の最頻値の分布)')
for s, d in DEP.items():
    c = collections.Counter(nrep(rows, d) for k, rows in tl.items() if k[1] == 'normal' and k[2] == 'b50v150')
    print(f'  {s:9} {dict(sorted(c.items(), key=lambda x: (x[0] is None, x[0] or 0)))}')

print('\n§2 ρ の差の順に 10 組 (各 18 回 = 3 点 × 開始 2 × 3 サイクル)。主 = 同じ Pod 内、副 = 分離と比較')
print(f'{"pair":18} {"Δρ":>5} {"通信%":>6} | 主:回数 Δn平均 | 副:回数 Δn平均 損平均[m] | 点ごとの主の回数 b100v0/b50v150/b50v300')
for p in ORDER:
    os_ = [o for o in obs if o['pair'] == p]
    if not os_:
        print(f'{p:18} データなし'); continue
    k1 = sum(1 for o in os_ if o['dragged']); k2 = sum(1 for o in os_ if o['dragged2'])
    dn1 = sum(o['dn'] for o in os_) / len(os_)
    d2 = [o['dn2'] for o in os_ if o['dn2'] is not None]; ls = [o['loss'] for o in os_ if o['loss'] is not None]
    per = '/'.join(str(sum(1 for o in os_ if o['pt'] == pt and o['dragged'])) for pt in POINTS)
    print(f'{p:18} {drho(p):5.2f} {TRAFFIC[p]:6.1f} | {k1:2}/{len(os_)} {dn1:5.2f} | {k2:2}/{len(os_)} '
          f'{(sum(d2) / len(d2)) if d2 else float("nan"):5.2f} {(sum(ls) / len(ls)) if ls else float("nan"):8.0f} | {per}')

print('\n§3 セル (ペア × 点 × 開始台数) ごとの 3 サイクル: n_st (同居の台数)、主判定で引きずられた側と Δn、normal の n_s/n_t、損')
for p in ORDER:
    for pt in POINTS:
        for n0 in STARTS:
            os_ = [o for o in obs if o['pair'] == p and o['pt'] == pt and o['n0'] == n0]
            if not os_:
                continue
            cells = '  '.join(f'c{o["cyc"]}: {o["nst"]} [{"/".join(o["dragged"]) or "-"} {o["dn"]}] u{o["us"]:.0f}/{o["ut"]:.0f} '
                              f'| {o["ns"]}/{o["nt"]} {o["loss"] if o["loss"] is not None else float("nan"):+.0f}'
                              f'{" *" + ",".join(o["marks"]) if o["marks"] else ""}' for o in os_)
            print(f'{p:18} {pt:8} 開始{n0}  {cells}')
    print()

print('§4 印付きの観測と、印を除いた主判定の回数')
nmark = [o for o in obs if o['marks']]
print(f'  印付き {len(nmark)}/{len(obs)}  内訳 {dict(collections.Counter(m for o in nmark for m in o["marks"]))}')
for p in ORDER:
    cl = [o for o in obs if o['pair'] == p and not o['marks']]
    if cl:
        print(f'  {p:18} 印なし {len(cl):2} 回中 主 {sum(1 for o in cl if o["dragged"])} / 副 {sum(1 for o in cl if o["dragged2"])}')
