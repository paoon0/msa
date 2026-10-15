#!/usr/bin/env python3
"""pdist-k3 本走の解析 (plan-pdist-k3.md §5 と追記 2・3 のとおり)。予測の的中率は出さない。

入力: summer2026/results-<PAIR>.csv, timeline-<PAIR>.csv (同居、既定 pdistk3pair)
      summer2026/results-<SEP>.csv,  timeline-<SEP>.csv  (分離 12 サイクル、既定 pdistk3sep)
      rightsizing/<枠表> (既定 rightsize-pdist-k3.csv)
計測窓 = t_rel ∈ [180, 420] s。台数 = 窓内の current_replicas の最頻値 (同数なら大きい方)。

主判定 (追記 2): 同居 Pod の台数 n_st と、同じ配合の分離 12 回の台数の最頻値 n_x を比べる。
  n_x < n_st → その側は引きずられた。Δn = max(n_st − n_x, 0) (両側の大きい方)。
  損 = n_st(r_s + r_t) − (n_x,s r_s + n_x,t r_t) [m]。
回ごとの比較: 同じサイクル番号の分離の台数と比べた判定も併記する。
補助 (同じ Pod の中で): サンプルごとの希望台数 = n (|u/70 − 1| ≤ 0.1) / ceil(n·u/70) の窓内最頻値 < n_st。
ブレの印 (除かずに併記):
  回ごと = その配合で分離 12 回の台数が 1 種類にそろわないサービス (s または t)
  窓内   = 同居 Pod の台数が計測窓の中で変わった回
その他の印: 取りこぼし (窓) が目標周回数 × 240 s の 1% 超、Pending、Ready 落ち (同居 Pod)、結果なし (k6 集計の回収失敗)。

使い方: python3 analyze_pdist_k3.py [PAIR] [SEP] [枠表] > analysis-pdistk3.txt
"""
import csv, collections, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
S26 = os.path.join(HERE, '..', 'summer2026')
PAIR = sys.argv[1] if len(sys.argv) > 1 else 'pdistk3pair'
SEP = sys.argv[2] if len(sys.argv) > 2 else 'pdistk3sep'
TABLE = sys.argv[3] if len(sys.argv) > 3 else 'rightsize-pdist-k3.csv'
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
POINTS = ['b100v0', 'b50v150', 'b50v300', 'b100v200']

R = {r['deploy']: float(r['request_m']) for r in csv.DictReader(open(os.path.join(HERE, TABLE), newline=''))}


def load(name):
    res = {(r['cycle'], r['arm'], r['point']): r
           for r in csv.DictReader(open(os.path.join(S26, f'results-{name}.csv')))}
    tl = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(S26, f'timeline-{name}.csv'))):
        if LO <= float(r['t_rel']) <= HI:
            tl[(r['cycle'], r['arm'], r['point'])].append(r)
    return res, tl


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


def reps(rows, dep):
    return [int(r['current_replicas']) for r in sorted(rows, key=lambda r: float(r['t_rel']))
            if r['deploy'] == dep and r['container'] != '-' and r['current_replicas']]


def nrep(rows, dep):
    xs = reps(rows, dep)
    return mode(xs) if xs else None


def changes(rows, dep):
    """窓内の台数の変化を 't秒:a→b' の列で返す (1 Deployment 内の複数コンテナ行は同じ台数なので先頭コンテナだけ見る)"""
    conts = sorted({r['container'] for r in rows if r['deploy'] == dep and r['container'] != '-'})
    if not conts:
        return []
    ser = sorted((float(r['t_rel']), int(r['current_replicas'])) for r in rows
                 if r['deploy'] == dep and r['container'] == conts[0] and r['current_replicas'])
    return [f'{int(t)}s:{a}→{b}' for (_, a), (t, b) in zip(ser, ser[1:]) if a != b]


def marks(res, tl, key, deps):
    m = []
    r = res.get(key)
    if r is None:
        m.append('結果なし')
    else:
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


pres, ptl = load(PAIR)
sres, stl = load(SEP)

# 分離: 配合 × サービスごとの 12 回の台数と最頻値
sep_n = collections.defaultdict(dict)      # (pt, short) -> {cycle: n}
for (cyc, arm, pt), rows in stl.items():
    if arm != 'normal':
        continue
    for short, d in DEP.items():
        n = nrep(rows, d)
        if n is not None:
            sep_n[(pt, short)][cyc] = n
sep_mode = {k: mode(list(v.values())) for k, v in sep_n.items()}
sep_bure = {k: len(set(v.values())) > 1 for k, v in sep_n.items()}

obs = []
for (cyc, arm, pt), rows in sorted(ptl.items()):
    if arm not in ARMS:
        continue
    for pair, dep, cmap, (s, t) in ARMS[arm]:
        nst = nrep(rows, dep)
        per = {}
        for cname, short in cmap.items():
            ser = series(rows, dep, cname)
            per[short] = dict(want=mode([want(n, u) for _, n, u in ser]), u=sum(u for *_, u in ser) / len(ser))
        nx = {x: sep_mode[(pt, x)] for x in (s, t)}
        dragged = [x for x in (s, t) if nx[x] < nst]
        dn = max([nst - nx[x] for x in (s, t)] + [0])
        loss = nst * (R[DEP[s]] + R[DEP[t]]) - (nx[s] * R[DEP[s]] + nx[t] * R[DEP[t]])
        nc = {x: sep_n[(pt, x)].get(cyc) for x in (s, t)}          # 同じサイクル番号の分離
        dragged_c = [x for x in (s, t) if nc[x] is not None and nc[x] < nst]
        aux = [x for x in (s, t) if per[x]['want'] < nst]
        bure = [x for x in (s, t) if sep_bure[(pt, x)]]
        chg = changes(rows, dep)
        mk = marks(pres, ptl, (cyc, arm, pt), {dep})
        obs.append(dict(cyc=cyc, arm=arm, pt=pt, pair=pair, s=s, t=t, nst=nst, nx=nx, dragged=dragged, dn=dn, loss=loss,
                        nc=nc, dragged_c=dragged_c, aux=aux, us=per[s]['u'], ut=per[t]['u'], bure=bure, chg=chg, marks=mk))

drho = lambda p: abs(RHO[p.split('+')[0]] - RHO[p.split('+')[1]])
ORDER = sorted(TRAFFIC, key=lambda p: (drho(p), -TRAFFIC[p]))
print(f'pdist-k3 の解析 (同居 {PAIR}、分離 {SEP}、枠 {TABLE})。窓 = t_rel 180–420 s')
print(f'観測: {len(obs)} (= 同居アームの回 × ペア)\n')

print('§1 分離の台数 (配合ごとの 12 回の分布。* = 回ごとのブレ)')
print(f'  {"":9} ' + ' '.join(f'{pt:>16}' for pt in POINTS))
for x in DEP:
    cells = []
    for pt in POINTS:
        c = collections.Counter(sep_n[(pt, x)].values())
        cells.append(('*' if sep_bure[(pt, x)] else ' ') + ','.join(f'{k}×{v}' for k, v in sorted(c.items())))
    print(f'  {x:9} ' + ' '.join(f'{c:>16}' for c in cells))

print('\n§2 ρ の差の順に 10 組 (各 12 回 = 4 配合 × 3 サイクル)。主 = 分離 12 回の最頻値と比較')
print(f'{"pair":18} {"Δρ":>5} {"通信%":>6} | 主:回数 Δn平均 損平均[m] | 回ごと比較 | 補助(Pod内) | ブレ印付き 窓内変化 | 配合ごとの主の回数 ' + '/'.join(POINTS))
for p in ORDER:
    os_ = [o for o in obs if o['pair'] == p]
    if not os_:
        print(f'{p:18} データなし'); continue
    k = sum(1 for o in os_ if o['dragged']); kc = sum(1 for o in os_ if o['dragged_c']); ka = sum(1 for o in os_ if o['aux'])
    kb = sum(1 for o in os_ if o['bure']); kw = sum(1 for o in os_ if o['chg'])
    per = '/'.join(str(sum(1 for o in os_ if o['pt'] == pt and o['dragged'])) for pt in POINTS)
    print(f'{p:18} {drho(p):5.2f} {TRAFFIC[p]:6.1f} | {k:2}/{len(os_)} {sum(o["dn"] for o in os_) / len(os_):5.2f} '
          f'{sum(o["loss"] for o in os_) / len(os_):8.0f} | {kc:2}/{len(os_)} | {ka:2}/{len(os_)} | {kb:2} {kw:2} | {per}')

print('\n§3 ペア × 配合ごと: 分離の最頻値 n_x(s)/n_x(t) と、各サイクルの同居 Pod の台数 n_st [引きずられた側 Δn] 損')
print('   B = 回ごとのブレのある側、W = 窓内の変化、u = 窓平均の利用率 s/t、(c n/n) = 同じサイクルの分離')
for p in ORDER:
    for pt in POINTS:
        os_ = [o for o in obs if o['pair'] == p and o['pt'] == pt]
        if not os_:
            continue
        o0 = os_[0]
        head = f'{p:18} {pt:8} 分離 {o0["nx"][o0["s"]]}/{o0["nx"][o0["t"]]}' + (f' B:{"/".join(o0["bure"])}' if o0['bure'] else '')
        cells = '  '.join(f'c{o["cyc"]}: {o["nst"]} [{"/".join(o["dragged"]) or "-"} {o["dn"]}] {o["loss"]:+.0f}m '
                          f'u{o["us"]:.0f}/{o["ut"]:.0f} (c {o["nc"][o["s"]]}/{o["nc"][o["t"]]})'
                          f'{" W:" + ",".join(o["chg"]) if o["chg"] else ""}'
                          f'{" *" + ",".join(o["marks"]) if o["marks"] else ""}' for o in os_)
        print(f'{head}  {cells}')
    print()

print('§4 印')
nmark = [o for o in obs if o['marks']]
print(f'  その他の印付き {len(nmark)}/{len(obs)}  内訳 {dict(collections.Counter(m for o in nmark for m in o["marks"]))}')
for p in ORDER:
    cl = [o for o in obs if o['pair'] == p and not o['bure'] and not o['chg']]
    if cl:
        print(f'  {p:18} ブレの印なし {len(cl):2} 回中 主 {sum(1 for o in cl if o["dragged"])}')
