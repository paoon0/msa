#!/usr/bin/env python3
"""pdist 本走の解析 (plan-pdist.md §4–5 のとおり)。

入力: summer2026/results-pdist.csv, timeline-pdist.csv, rightsizing/predictions-pdist.csv, rightsize-pdist.csv
計測窓 = t_rel ∈ [WARM, WARM+MEAS] = [180, 420] s (時系列は k6 起動時刻が 0)。

主判定 (同じ Pod の中で): 同居 Pod の各コンテナについて、サンプルごとに
  n = そのサンプルの current_replicas、u = hpa_util_pct
  希望 = n (|u/70 − 1| ≤ 0.1) / ceil(n·u/70) (1〜8)
  窓内の希望の最頻値 < n_st (窓内の current_replicas の最頻値) → 引きずられた。Δn = n_st − 希望。
副判定 (分離との比較): 同じサイクル・点・開始台数の normal アームの台数 (最頻値) n_s, n_t から
  損 = n_st(r_s + r_t) − (n_s r_s + n_t r_t) [m]。
印: 取りこぼし (窓) が目標周回数 × 240 s の 1% 超 (購入・閲覧それぞれ)、Pending (窓内)、Ready 落ち (窓内で ready < current)。
集計: (ペア, 点, 開始台数) のセルごとに 3 サイクルの多数決。front+ad は主集計から外して別記 (§追記)。

使い方: python3 analyze_pdist.py > analysis-pdist.txt
"""
import csv, collections, math, os

HERE = os.path.dirname(os.path.abspath(__file__))
S26 = os.path.join(HERE, '..', 'summer2026')
WARM, MEAS = 180, 240
LO, HI = WARM, WARM + MEAS

# アーム → [(ペア名, ホスト Deployment, {コンテナ名: 短縮名}, (s, t))]
ARMS = {
    'pairsP1': [('front+ad', 'frontend', {'server': 'front', 'ad': 'ad'}, ('front', 'ad')),
                ('checkout+shipping', 'checkoutservice', {'checkout': 'checkout', 'shipping': 'shipping'}, ('checkout', 'shipping')),
                ('catalog+reco', 'productcatalogservice', {'server': 'catalog', 'recommendation': 'reco'}, ('catalog', 'reco'))],
    'pairsP2': [('front+cart', 'frontend', {'server': 'front', 'cartservice': 'cart'}, ('front', 'cart')),
                ('catalog+checkout', 'productcatalogservice', {'server': 'catalog', 'checkout': 'checkout'}, ('catalog', 'checkout'))],
    'pairsP3': [('front+catalog', 'frontend', {'server': 'front', 'productcatalog': 'catalog'}, ('front', 'catalog')),
                ('currency+checkout', 'checkoutservice', {'checkout': 'checkout', 'currency': 'currency'}, ('currency', 'checkout'))],
}
ORDER = ['front+catalog', 'checkout+shipping', 'catalog+reco', 'front+cart', 'currency+checkout', 'catalog+checkout', 'front+ad']
CLASS = {'front+catalog': '近い', 'checkout+shipping': '近い', 'catalog+reco': '近い', 'front+cart': '中間',
         'currency+checkout': '遠い', 'catalog+checkout': '遠い', 'front+ad': 'R1と逆(別記)'}
DEP = {'front': 'frontend', 'catalog': 'productcatalogservice', 'reco': 'recommendationservice', 'ad': 'adservice',
       'currency': 'currencyservice', 'cart': 'cartservice', 'checkout': 'checkoutservice',
       'shipping': 'shippingservice'}
POINTS = ['b100v0', 'b50v150', 'b50v300']
STARTS = ['1', '2']

R = {r['deploy']: float(r['request_m']) for r in csv.DictReader(open(os.path.join(HERE, 'rightsize-pdist.csv')))}
PRED = {(r['pair'], r['point'], r['start']): r for r in csv.DictReader(open(os.path.join(HERE, 'predictions-pdist.csv')))}

res = {}
for r in csv.DictReader(open(os.path.join(S26, 'results-pdist.csv'))):
    res[(r['cycle'], r['arm'], r['point'], r['start_replicas'])] = r

tl = collections.defaultdict(list)   # (cyc, arm, pt, n0) -> rows in window
for r in csv.DictReader(open(os.path.join(S26, 'timeline-pdist.csv'))):
    t = float(r['t_rel'])
    if LO <= t <= HI:
        tl[(r['cycle'], r['arm'], r['point'], r['start_replicas'])].append(r)


def mode(xs):
    c = collections.Counter(xs)
    top = max(c.values())
    return max(k for k, v in c.items() if v == top)   # 同数なら大きい方 (HPA の安全側)


def want(n, u):
    q = u / 70.0
    return n if abs(q - 1) <= 0.10 else max(1, min(8, math.ceil(n * q)))


def deploy_series(rows, dep, cont):
    out = []
    for r in rows:
        if r['deploy'] == dep and r['container'] == cont and r['hpa_util_pct'] not in ('', None) and r['current_replicas'] not in ('', None):
            out.append((float(r['t_rel']), int(r['current_replicas']), float(r['hpa_util_pct']),
                        int(r['ready_replicas'] or 0), int(r['pending_pods'] or 0)))
    return sorted(out)


def nrep(rows, dep):
    xs = [int(r['current_replicas']) for r in rows if r['deploy'] == dep and r['container'] != '-' and r['current_replicas']]
    return mode(xs) if xs else None


def marks(key, deps):
    r = res.get(key); m = []
    if r is None:
        return ['結果なし']
    b, v = float(r['target_rate']), float(r['browse_rate_target'] or 0)
    if float(r['dropped_win'] or 0) > 0.01 * b * MEAS:
        m.append(f'取りこぼし購入{r["dropped_win"]}')
    if v > 0 and float(r['browse_dropped_win'] or 0) > 0.01 * v * MEAS:
        m.append(f'取りこぼし閲覧{r["browse_dropped_win"]}')
    rows = tl[key]
    if any(int(x['pending_pods'] or 0) > 0 for x in rows if x['deploy'] in deps):
        m.append('Pending')
    if any(x['current_replicas'] and int(x['ready_replicas'] or 0) < int(x['current_replicas'])
           for x in rows if x['deploy'] in deps and x['container'] != '-'):
        m.append('Ready落ち')
    return m


obs = []   # 1 回 × 1 ペアごと
for (cyc, arm, pt, n0), rows in sorted(tl.items()):
    if arm not in ARMS:
        continue
    nkey = (cyc, 'normal', pt, n0)
    for pair, dep, cmap, (s, t) in ARMS[arm]:
        nst = nrep(rows, dep)
        per = {}
        for cname, short in cmap.items():
            ser = deploy_series(rows, dep, cname)
            w = mode([want(n, u) for _, n, u, _, _ in ser])
            per[short] = dict(want=w, u=sum(u for _, _, u, _, _ in ser) / len(ser), ns=len(ser))
        dragged = [x for x in (s, t) if per[x]['want'] < nst]
        dn = max([nst - per[x]['want'] for x in (s, t)] + [0])
        ns_ = nrep(tl[nkey], DEP[s]); nt_ = nrep(tl[nkey], DEP[t])
        loss = None if ns_ is None or nt_ is None else nst * (R[DEP[s]] + R[DEP[t]]) - (ns_ * R[DEP[s]] + nt_ * R[DEP[t]])
        mk = marks((cyc, arm, pt, n0), {dep}) + [f'normal:{x}' for x in marks(nkey, {DEP[s], DEP[t]})]
        reps = [n for _, n, _, _, _ in deploy_series(rows, dep, list(cmap)[0])]
        obs.append(dict(cyc=cyc, arm=arm, pt=pt, n0=n0, pair=pair, s=s, t=t, nst=nst, ws=per[s]['want'], wt=per[t]['want'],
                        us=per[s]['u'], ut=per[t]['u'], dragged=dragged, dn=dn, ns=ns_, nt=nt_, loss=loss, marks=mk,
                        changed=len(set(reps)) > 1, nsamp=per[s]['ns']))

print('pdist 本走の解析 (plan-pdist.md §4–5)。窓 = t_rel 180–420 s、主判定 = 同じ Pod 内のコンテナ別希望台数')
print(f'回数: {len({(o["cyc"], o["arm"], o["pt"], o["n0"]) for o in obs})} 回 (同居アーム) × ペア → {len(obs)} 観測\n')

print('§1 各回の観測 (u = 窓平均の利用率 %、希望 = コンテナ単独の希望台数の最頻値、n_s/n_t = 同じ回の normal の台数)')
print(f'{"pair":18} {"pt":8} 開始 cyc  n_st  u_s  u_t 希望s 希望t 引きずられた  Δn | n_s n_t  損[m] 窓内変化 印')
for p in ORDER:
    for pt in POINTS:
        for n0 in STARTS:
            for o in [o for o in obs if o['pair'] == p and o['pt'] == pt and o['n0'] == n0]:
                print(f'{p:18} {pt:8} {n0:>3} {o["cyc"]:>3} {o["nst"]:5} {o["us"]:4.0f} {o["ut"]:4.0f} {o["ws"]:5} {o["wt"]:5}  '
                      f'{"/".join(o["dragged"]) or "-":12} {o["dn"]:2} | {o["ns"]!s:>3} {o["nt"]!s:>3} {o["loss"] if o["loss"] is not None else "":>6.0f} '
                      f'{"あり" if o["changed"] else "":4} {" ".join(o["marks"])}')
    print()

print('§2 セル (3 サイクルの多数決) と予測・R1 の答え合わせ')
print(f'{"pair":18} {"区分":10} {"pt":8} 開始  実測(引きずり/側 [回数])        予測(側)           R1      予測 R1  損平均[m]')
cells = []
for p in ORDER:
    for pt in POINTS:
        for n0 in STARTS:
            os_ = [o for o in obs if o['pair'] == p and o['pt'] == pt and o['n0'] == n0]
            k = sum(1 for o in os_ if o['dragged'])
            yes = k * 2 > len(os_)
            sides = collections.Counter('/'.join(o['dragged']) for o in os_ if o['dragged'])
            side = sides.most_common(1)[0][0] if yes else '-'
            pr = PRED[(p, pt, n0)]
            pyes = pr['drag'] == 'あり'; r1 = pr['R1'] == '損あり'
            hit_p = (yes == pyes) and (not yes or side == pr['dragged'])
            hit_r1 = yes == r1
            ls = [o['loss'] for o in os_ if o['loss'] is not None]
            lm = sum(ls) / len(ls) if ls else float('nan')
            disc = (pyes != r1)
            cells.append(dict(pair=p, pt=pt, n0=n0, yes=yes, side=side, k=k, n=len(os_), pyes=pyes, pside=pr['dragged'],
                              r1=r1, hit_p=hit_p, hit_r1=hit_r1, lm=lm, disc=disc,
                              clean=[o for o in os_ if not o['marks']]))
            det = ' '.join(sorted('/'.join(o['dragged']) or '-' for o in os_))
            print(f'{p:18} {CLASS[p]:10} {pt:8} {n0:>3}  {"あり" if yes else "なし"} {side:9} [{k}/{len(os_)}: {det:16}] '
                  f'{pr["drag"]}({pr["dragged"]:9}) {pr["R1"]:6} {"○" if hit_p else "×":>3} {"○" if hit_r1 else "×":>3} {lm:8.0f}'
                  f'{"  ←識別セル" if disc else ""}')
    print()


def tally(sel, label):
    cs = [c for c in cells if sel(c)]
    if not cs:
        return
    hp = sum(c['hit_p'] for c in cs); hr = sum(c['hit_r1'] for c in cs)
    print(f'  {label:40} セル {len(cs):2}  予測 {hp:2}/{len(cs)}  R1 {hr:2}/{len(cs)}')


main = lambda c: c['pair'] != 'front+ad'
print('§3 的中率 (主集計 = front+ad を除く 6 組 × 3 点 × 2 開始 = 36 セル)')
tally(main, '主集計 全点')
tally(lambda c: main(c) and c['pt'] != 'b50v300', '  b100v0 + b50v150 (境目の点を除く)')
tally(lambda c: main(c) and c['pt'] == 'b50v300', '  b50v300 (境目付近、別集計)')
tally(lambda c: main(c) and c['pt'] == 'b50v150', '  b50v150 (対照)')
tally(lambda c: main(c) and c['disc'], '  識別セル (予測と R1 が食い違う)')
for cls in ['近い', '中間', '遠い']:
    tally(lambda c, cls=cls: main(c) and CLASS[c['pair']] == cls, f'  区分 {cls}')
tally(lambda c: c['pair'] == 'front+ad', '別記 front+ad')

print('\n§3b 印付きの回を除いた多数決 (印なしの回が 2 回以上あるセルのみ)')
chg = 0
for c in cells:
    cl = c['clean']
    if len(cl) < 2 or len(cl) == c['n']:
        continue
    k = sum(1 for o in cl if o['dragged'])
    yes = k * 2 > len(cl)
    if yes != c['yes']:
        chg += 1
        print(f'  {c["pair"]} {c["pt"]} 開始{c["n0"]}: 全回 {"あり" if c["yes"] else "なし"} → 印なし {k}/{len(cl)}')
print(f'  多数決が変わったセル: {chg}')
nmark = sum(1 for o in obs if o['marks'])
print(f'  印付きの観測: {nmark}/{len(obs)}')
mc = collections.Counter(m.split(':')[-1].rstrip('0123456789.') for o in obs for m in o['marks'])
print('  内訳:', dict(mc))

print('\n§4 遠い 2 組: 引きずる側の入れ替わり (多数決の引きずられた側)')
for p in ['currency+checkout', 'catalog+checkout']:
    print(f'  {p}: ' + '  '.join(f'{c["pt"]}/開始{c["n0"]}={c["side"]}' for c in cells if c['pair'] == p))

print('\n§5 front+ad (別記): ホスト Pod の台数推移と ad / front の利用率 (窓内、15 s ごと)')
for (cyc, arm, pt, n0), rows in sorted(tl.items()):
    if arm != 'pairsP1':
        continue
    sa = deploy_series(rows, 'frontend', 'ad'); sf = deploy_series(rows, 'frontend', 'server')
    rep = ''.join(str(n) for _, n, _, _, _ in sa)
    ua = ' '.join(f'{u:.0f}' for _, _, u, _, _ in sa)
    nad = ''.join(str(int(r['current_replicas'])) for r in sorted(tl[(cyc, 'normal', pt, n0)], key=lambda r: float(r['t_rel']))
                  if r['deploy'] == 'adservice' and r['container'] == 'server' and r['current_replicas'])
    print(f'  c{cyc} {pt:8} 開始{n0}: 同居台数 {rep}  ad u%: {ua}')
    print(f'  {"":22} 分離 ad 台数 {nad}  front u% 平均 {sum(u for *_, u, _, _ in [(a, b, c, d, e) for a, b, c, d, e in sf]) / max(1, len(sf)):.0f}')

# --- §6 (解析時に追加、計画 §4 の副判定をセル単位に多数決したもの。事前に決めた集計ではない) ---
print('\n§6 副判定 (分離との比較) のセル多数決: 同じ回の normal の台数 n_x < n_st の側を「引きずられた」とする')
print('  主判定 (同じ Pod 内) は「2 台になったら u<35% まで 1 台に戻らない」HPA の履歴効果を引きずりと数えられない。')
print('  予測 (predictions-pdist.csv) は「単独で開始台数から落ち着く台数 < 同居の台数」で定義したので、こちらが定義として対応する。')
print(f'{"pair":18} {"pt":8} 開始  副判定 [回数: 各回]                    予測       主判定  予測一致')
sec = []
for p in ORDER:
    for pt in POINTS:
        for n0 in STARTS:
            os_ = [o for o in obs if o['pair'] == p and o['pt'] == pt and o['n0'] == n0]
            d2 = ['/'.join(x for x, nx in ((o['s'], o['ns']), (o['t'], o['nt'])) if nx is not None and nx < o['nst'])
                  for o in os_]
            k = sum(1 for d in d2 if d)
            yes = k * 2 > len(os_)
            side = collections.Counter(d for d in d2 if d).most_common(1)[0][0] if yes else '-'
            pr = PRED[(p, pt, n0)]
            hit = (yes == (pr['drag'] == 'あり')) and (not yes or side == pr['dragged'])
            c1 = [c for c in cells if c['pair'] == p and c['pt'] == pt and c['n0'] == n0][0]
            sec.append(dict(pair=p, pt=pt, hit=hit, disc=c1['disc'], r1=c1['r1'], yes=yes))
            print(f'{p:18} {pt:8} {n0:>3}  {"あり" if yes else "なし"} {side:9} [{k}/{len(os_)}: {" ".join(d or "-" for d in d2):24}] '
                  f'{pr["drag"]}({pr["dragged"]:8}) {"あり" if c1["yes"] else "なし":4} {"○" if hit else "×"}')
for lab, f in [('主集計 36 セル', lambda c: c['pair'] != 'front+ad'),
               ('  うち b50v300', lambda c: c['pair'] != 'front+ad' and c['pt'] == 'b50v300'),
               ('  うち b50v300 以外', lambda c: c['pair'] != 'front+ad' and c['pt'] != 'b50v300'),
               ('  識別セル', lambda c: c['pair'] != 'front+ad' and c['disc']),
               ('別記 front+ad', lambda c: c['pair'] == 'front+ad')]:
    cs = [c for c in sec if f(c)]
    print(f'  {lab:22} 予測 {sum(c["hit"] for c in cs)}/{len(cs)}  R1 {sum(c["yes"] == c["r1"] for c in cs)}/{len(cs)}')
