#!/usr/bin/env python3
"""pdist-k3 本走の解析 (plan-pdist-k3.md §5 と追記 2・3 のとおり)。予測の的中率は出さない。

入力: summer2026/results-<PAIR>.csv, timeline-<PAIR>.csv (同居、既定 pdistk3pair)
      summer2026/results-<SEP>.csv,  timeline-<SEP>.csv  (分離 12 サイクル、既定 pdistk3sep)
      rightsizing/<枠表> (既定 rightsize-pdist-k3.csv)
計測窓 = 時刻の表 -times.csv があるデータは CPU 秒・予約枠と同じ内側の区間 (3 回目は t_rel 310–590 s、window() 参照)、無ければ t_rel ∈ [180, 420] s。台数 = 窓内の current_replicas の最頻値 (同数なら大きい方)。

主判定 (追記 2): 同居 Pod の台数 n_st と、同じ配合の分離 12 回の台数の最頻値 n_x を比べる。
  n_x < n_st → その側は引きずられた。Δn = max(n_st − n_x, 0) (両側の大きい方)。
  損 = n_st(r_s + r_t) − (n_x,s r_s + n_x,t r_t) [m]。
回ごとの比較: 同じサイクル番号の分離の台数と比べた判定も併記する。
補助 (同じ Pod の中で): サンプルごとの希望台数 = n (|u/70 − 1| ≤ 0.1) / ceil(n·u/70) の窓内最頻値 < n_st。
ブレの印 (除かずに併記):
  回ごと = その配合で分離 12 回の台数が 1 種類にそろわないサービス (s または t)
  窓内   = 同居 Pod の台数が計測窓の中で変わった回
その他の印: 取りこぼし (窓) が目標周回数 × MEAS 秒の 1% 超、Pending (同居 Pod / 他、窓内の timeline。コンテナ作成中も含む)、
  載らない (2026-11-21 追加: events の FailedScheduling、ウォームアップ中も含む)、開始不良・枠不一致、Ready 落ち (同居 Pod、台数が動いていない
  サンプルで ready < current)、結果なし (k6 集計の回収失敗)。印付きを除いた集計を §4 に併記。
2026-10-16 修正 (アヌビス点検、pairsP1b の cyc1 b100v200 の 2 観測を見た後。主判定の規則は変えていない):
  Ready 落ちの定義を台数変更中以外に限定、Pending(他) を追加、§4 に印付きを除いた集計と事後の参考 (分離 12 回の最大値超え) を追加、
  コンテナの利用率や Pod の台数が取れない回で止まらないようにした。
2026-11-21 修正 (3 回目 pdistk3sep3 / pdistk3pair3 用、結果を見る前。アヌビス 11/20 の C):
  配合を 5 つ (b100v0 / b50v150 / b50v300 / b75v200 / b0v300) に、ρ を mix-cpu5 (生カウンタ、6 サイクル) に差し替え、
  3 つ同居 frontrecocatalog (front+catalog+reco) を 1 観測として扱う (メンバーが 3 つ。Δρ = 3 組の差の最大、
  損 = n_st·Σr − Σ n_x·r、引きずられた側 = n_x < n_st のメンバー全部)。start_ok / frames_ok が 0 の回に印を付ける。
  主判定の規則は変えていない。
  同日 追加 (アヌビスの実装点検): 引数の既定値を 3 回目に、events の FailedScheduling を「載らない」の印に、
  観測数を期待値 (アームのペア数 × 配合 × 同居サイクル) と並べて表示。

使い方 (3 回目): python3 analyze_pdist_k3.py pdistk3pair3 pdistk3sep3 rightsize-pdist-k3-mc5.csv > analysis-pdistk3-3.txt

使い方: python3 analyze_pdist_k3.py [PAIR] [SEP] [枠表] > analysis-pdistk3.txt
"""
import csv, datetime, collections, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
S26 = os.path.join(HERE, '..', 'summer2026')
PAIR = sys.argv[1] if len(sys.argv) > 1 else 'pdistk3pair3'
SEP = sys.argv[2] if len(sys.argv) > 2 else 'pdistk3sep3'
TABLE = sys.argv[3] if len(sys.argv) > 3 else 'rightsize-pdist-k3-mc5.csv'
WARM, MEAS, HPA_MAX = 180, 240, 12
LO, HI = WARM, WARM + MEAS   # 時刻の表が無いデータ (2026-11-04 より前) の窓。CPU 秒・予約枠もこの区間


def window(name):
    """台数を数える区間 [LO, HI] (t_rel 秒) と MEAS を返す (2026-11-17 追加、ユーザ指示「両端をけずる方に合わせて」)。
    results-<name>-times.csv があれば、CPU 秒・予約枠と同じ Prometheus の区間 (prom_from〜prom_to = 窓の両端 10 秒を
    削った内側) に揃える。無ければ従来の [WARM, WARM+MEAS]。"""
    p = os.path.join(S26, f'results-{name}-times.csv')
    if not os.path.exists(p):
        return LO, HI, MEAS
    rows = list(csv.DictReader(open(p)))
    lo = {round(float(r['prom_from']) - float(r['t_run'])) for r in rows}
    hi = {round(float(r['prom_to']) - float(r['t_run'])) for r in rows}
    ms = {round(float(r['t_end']) - float(r['t_beg'])) for r in rows}
    assert len(lo) == len(hi) == len(ms) == 1, (name, lo, hi, ms)
    return lo.pop(), hi.pop(), ms.pop()

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
    'frontrecocatalog': [('front+catalog+reco', 'frontend',
                          {'server': 'front', 'productcatalog': 'catalog', 'recommendation': 'reco'}, ('front', 'catalog', 'reco'))],
}
# ρ = mix-cpu5 (CLOSE_EVERY=20、生カウンタ、6 サイクル、全 17 点。analysis-rho5.txt)。RHO = 1 台 (主)、RHO2 = 2 台 (参考)
# (旧: analysis-rho2.txt の 1 台 front 0.35 / catalog 0.34 / reco 0.36 / currency 0.26 / cart 0.18 / checkout −0.02 / shipping −0.02)
RHO = {'front': 0.3174, 'catalog': 0.3114, 'reco': 0.3246, 'currency': 0.2674, 'cart': 0.1864, 'checkout': 0.0076, 'shipping': 0.0027}
RHO2 = {'front': 0.3216, 'catalog': 0.3233, 'reco': 0.3241, 'currency': 0.2534, 'cart': 0.1978, 'checkout': 0.0172, 'shipping': 0.0083}
# 通信量 (edge-traffic、購入 100 のときのヘッダ込みバイト量の割合)。3 つ同居は Pod 内に入る 3 本の和 (38.8 + 18.4 + 4.8)
TRAFFIC = {'front+catalog+reco': 62.0, 'checkout+shipping': 3.7, 'catalog+reco': 18.4, 'front+cart': 4.1, 'catalog+checkout': 2.3, 'front+catalog': 38.8,
           'currency+checkout': 2.6, 'front+currency': 8.5, 'checkout+cart': 2.7, 'front+reco': 4.8, 'checkout+front': 2.5}
DEP = {'front': 'frontend', 'catalog': 'productcatalogservice', 'reco': 'recommendationservice', 'currency': 'currencyservice',
       'cart': 'cartservice', 'checkout': 'checkoutservice', 'shipping': 'shippingservice'}
POINTS = ['b100v0', 'b50v150', 'b50v300', 'b75v200', 'b0v300']

R = {r['deploy']: float(r['request_m']) for r in csv.DictReader(open(os.path.join(HERE, TABLE), newline=''))}


def load(name):
    # 2026-11-21 (アヌビス指摘・ユーザ指示「そうならないようにして」): 同じ (cycle, arm, point) を測り直して追記したとき、
    #   2 回分が 1 つの窓に混ざらないよう、どのファイルも「最後の測定」だけを使う。
    #   results は辞書の上書きで最後の行が残る。timeline は t_rel が戻った所 (= 次の測定の始まり) で区切り、最後の区切りだけを残す
    res, nres = {}, collections.Counter()
    for r in csv.DictReader(open(os.path.join(S26, f'results-{name}.csv'))):
        k = (r['cycle'], r['arm'], r['point']); res[k] = r; nres[k] += 1
    seg = collections.defaultdict(list)   # key -> [[行, ...] (測定 1 回分), ...]
    last_t = {}
    for r in csv.DictReader(open(os.path.join(S26, f'timeline-{name}.csv'))):
        k = (r['cycle'], r['arm'], r['point']); t = float(r['t_rel'])
        if k not in last_t or t < last_t[k] - 1:
            seg[k].append([])
        last_t[k] = t
        seg[k][-1].append(r)
    lo, hi, _ = window(name)
    tl = collections.defaultdict(list)
    for k, ss in seg.items():
        tl[k] = [r for r in ss[-1] if lo <= float(r['t_rel']) <= hi]
    dup = sorted(k for k in set(nres) | set(seg) if nres[k] > 1 or len(seg.get(k, [])) > 1)
    if dup:
        print(f'注意: 同じ (cycle, arm, point) の測定が複数ある点 {len(dup)} 件 → 最後の測定だけを使う: '
              + ', '.join('/'.join(k) + f' (results {nres[k]} 回・timeline {len(seg.get(k, []))} 回)' for k in dup))
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


def failed_sched(name):
    """events-<name>.csv の FailedScheduling (collect_events.py が message の頭に付ける) を (cycle, arm, point) ごとに数える。
    2026-11-21 より前のファイルには無いので空になる"""
    p = os.path.join(S26, f'events-{name}.csv'); c = collections.Counter()
    # 測り直しで追記された前の測定のイベントを数えないよう、times.csv の最後の測定の t_run より前のイベントは捨てる (2026-11-21)
    t0 = {}
    tp = os.path.join(S26, f'results-{name}-times.csv')
    if os.path.exists(tp):
        for r in csv.DictReader(open(tp)):
            t0[(r['cycle'], r['arm'], r['point'])] = float(r['t_run'])
    if os.path.exists(p):
        for r in csv.DictReader(open(p)):
            if (r.get('message') or '').startswith('FailedScheduling:'):
                k = (r['cycle'], r['arm'], r.get('point'))
                if k in t0 and r.get('time'):
                    te = datetime.datetime.fromisoformat(r['time'].replace('Z', '+00:00')).timestamp()
                    if te < t0[k] - 60:   # ドライバは HPA 作成の少し前から回収する (SINCE) ので 60 秒の余裕
                        continue
                c[k] += 1
    return c


FS = {}


def marks(res, tl, key, deps, name=None):
    m = []
    if name is not None:
        if name not in FS:
            FS[name] = failed_sched(name)
        if FS[name].get(key):
            m.append('載らない')
    r = res.get(key)
    if r is None:
        m.append('結果なし')
    else:
        b, v = float(r['target_rate']), float(r['browse_rate_target'] or 0)
        if float(r['dropped_win'] or 0) > 0.01 * b * window(PAIR)[2]:
            m.append('取りこぼし購入')
        if v > 0 and float(r['browse_dropped_win'] or 0) > 0.01 * v * window(PAIR)[2]:
            m.append('取りこぼし閲覧')
        if r.get('start_ok') == '0':    # 開始 15 秒以内に全 Deployment が開始台数でなかった
            m.append('開始不良')
        if r.get('frames_ok') == '0':   # 枠 (requests) の検査で表と不一致
            m.append('枠不一致')
    rows = tl[key]
    if any(int(x['pending_pods'] or 0) > 0 for x in rows if x['deploy'] in deps):
        m.append('Pending')
    elif any(int(x['pending_pods'] or 0) > 0 for x in rows):
        m.append('Pending(他)')
    # 2026-10-16 修正 (アヌビス指摘、pairsP1b の 2 観測を見た後): ready は Deployment、current は HPA の status なので
    # 台数変更の途中は ready < current になる (分離で ready<current の 107 サンプル中 106 が current≠desired)。
    # 台数が動いていないサンプル (current = desired かつ直前のサンプルと同じ current) に限る。
    for d in deps:
        ser = sorted((float(x['t_rel']), int(x['current_replicas']), x['desired_replicas'], int(x['ready_replicas'] or 0))
                     for x in rows if x['deploy'] == d and x['container'] != '-' and x['current_replicas'])
        ser = list({x[0]: x for x in ser}.values())   # 同居 Pod の 2 コンテナ行を 1 サンプルに
        if any(cur == prev[1] and str(cur) == des and rdy < cur for prev, (_, cur, des, rdy) in zip(ser, ser[1:])):
            m.append('Ready落ち'); break
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
    for pair, dep, cmap, mem in ARMS[arm]:
        nst = nrep(rows, dep)
        if nst is None:
            print(f'!! 台数なし: c{cyc} {arm} {pt} {pair}', file=sys.stderr); continue
        per = {}
        for cname, short in cmap.items():
            ser = series(rows, dep, cname)
            per[short] = (dict(want=mode([want(n, u) for _, n, u in ser]), u=sum(u for *_, u in ser) / len(ser)) if ser
                          else dict(want=nst, u=float('nan')))
        nx = {x: sep_mode[(pt, x)] for x in mem}
        dragged = [x for x in mem if nx[x] < nst]
        dn = max([nst - nx[x] for x in mem] + [0])
        loss = nst * sum(R[DEP[x]] for x in mem) - sum(nx[x] * R[DEP[x]] for x in mem)
        nc = {x: sep_n[(pt, x)].get(cyc) for x in mem}          # 同じサイクル番号の分離 (点の順番が同じ。測定日時は別)
        dragged_c = [x for x in mem if nc[x] is not None and nc[x] < nst]
        over_max = [x for x in mem if max(sep_n[(pt, x)].values()) < nst]   # 事後の参考: 分離 12 回の最大値を超えた側
        aux = [x for x in mem if per[x]['want'] < nst]
        bure = [x for x in mem if sep_bure[(pt, x)]]
        chg = changes(rows, dep)
        mk = marks(pres, ptl, (cyc, arm, pt), {dep}, PAIR)
        obs.append(dict(cyc=cyc, arm=arm, pt=pt, pair=pair, mem=mem, nst=nst, nx=nx, dragged=dragged, dn=dn, loss=loss,
                        nc=nc, dragged_c=dragged_c, over_max=over_max, aux=aux, u={x: per[x]['u'] for x in mem},
                        bure=bure, chg=chg, marks=mk))


def drho(p, rho=RHO):
    """メンバーどうしの ρ の差の最大 (ペアならその差そのもの)"""
    xs = [rho[x] for x in p.split('+')]
    return max(xs) - min(xs)

ORDER = sorted(TRAFFIC, key=lambda p: (drho(p), -TRAFFIC[p]))
print(f'pdist-k3 の解析 (同居 {PAIR}、分離 {SEP}、枠 {TABLE})。台数を数える区間 = t_rel 同居 {window(PAIR)[0]}–{window(PAIR)[1]} s / 分離 {window(SEP)[0]}–{window(SEP)[1]} s')
ncyc = len({o['cyc'] for o in obs})
print(f'観測: {len(obs)} (= 同居アームの回 × ペア)。期待値 = ペア数 × 配合 × 同居サイクル = '
      f'{sum(len(v) for a, v in ARMS.items() if any(o["arm"] == a for o in obs))} × {len(POINTS)} × {ncyc} = '
      f'{sum(len(v) for a, v in ARMS.items() if any(o["arm"] == a for o in obs)) * len(POINTS) * ncyc} (足りなければ点の中止か台数なし)')


print('§1 分離の台数 (配合ごとの 12 回の分布。* = 回ごとのブレ)')
print(f'  {"":9} ' + ' '.join(f'{pt:>16}' for pt in POINTS))
for x in DEP:
    cells = []
    for pt in POINTS:
        c = collections.Counter(sep_n[(pt, x)].values())
        cells.append(('*' if sep_bure.get((pt, x)) else ' ') + ','.join(f'{k}×{v}' for k, v in sorted(c.items())))
    print(f'  {x:9} ' + ' '.join(f'{c:>16}' for c in cells))

print(f'\n§2 ρ の差 (1 台) の順に 10 組 + 3 つ同居 (各 {len(POINTS)} 配合 × 3 サイクル)。主 = 分離 12 回の最頻値と比較。Δρ2 = 2 台の ρ の差 (参考)')
print(f'{"pair":18} {"Δρ":>6} {"Δρ2":>6} {"通信%":>6} | 主:回数 Δn平均 損平均[m] | 回ごと比較 | 補助(Pod内) | ブレ印付き 窓内変化 | 配合ごとの主の回数 ' + '/'.join(POINTS))
for p in ORDER:
    os_ = [o for o in obs if o['pair'] == p]
    if not os_:
        print(f'{p:18} データなし'); continue
    k = sum(1 for o in os_ if o['dragged']); kc = sum(1 for o in os_ if o['dragged_c']); ka = sum(1 for o in os_ if o['aux'])
    kb = sum(1 for o in os_ if o['bure']); kw = sum(1 for o in os_ if o['chg'])
    per = '/'.join(str(sum(1 for o in os_ if o['pt'] == pt and o['dragged'])) for pt in POINTS)
    print(f'{p:18} {drho(p):6.3f} {drho(p, RHO2):6.3f} {TRAFFIC[p]:6.1f} | {k:2}/{len(os_)} {sum(o["dn"] for o in os_) / len(os_):5.2f} '
          f'{sum(o["loss"] for o in os_) / len(os_):8.0f} | {kc:2}/{len(os_)} | {ka:2}/{len(os_)} | {kb:2} {kw:2} | {per}')

print('\n§3 ペア × 配合ごと: 分離の最頻値 n_x (メンバー順に /) と、各サイクルの同居 Pod の台数 n_st [引きずられた側 Δn] 損')
print('   B = 回ごとのブレのある側、W = 窓内の変化、u = 窓平均の利用率 (メンバー順)、(c n/n) = 点の順番が同じサイクル番号の分離 (測定日時は別)')
for p in ORDER:
    for pt in POINTS:
        os_ = [o for o in obs if o['pair'] == p and o['pt'] == pt]
        if not os_:
            continue
        o0 = os_[0]
        head = f'{p:18} {pt:8} 分離 {"/".join(str(o0["nx"][x]) for x in o0["mem"])}' + (f' B:{"/".join(o0["bure"])}' if o0['bure'] else '')
        cells = '  '.join(f'c{o["cyc"]}: {o["nst"]} [{"/".join(o["dragged"]) or "-"} {o["dn"]}] {o["loss"]:+.0f}m '
                          f'u{"/".join(format(o["u"][x], ".0f") for x in o["mem"])} (c {"/".join(str(o["nc"][x]) for x in o["mem"])})'
                          f'{" W:" + ",".join(o["chg"]) if o["chg"] else ""}'
                          f'{" *" + ",".join(o["marks"]) if o["marks"] else ""}' for o in os_)
        print(f'{head}  {cells}')
    print()

print('§4 印')
nmark = [o for o in obs if o['marks']]
print(f'  その他の印付き {len(nmark)}/{len(obs)}  内訳 {dict(collections.Counter(m for o in nmark for m in o["marks"]))}')
print('  ペアごと: 主判定の回数を (a) 全回 (b) その他の印 (取りこぼし・Pending・載らない・Ready落ち・結果なし・開始不良・枠不一致) のない回 (c) ブレの印のない回 で。')
print('  (d) は事後の参考 (2026-10-16、pairsP1b の 2 観測を見た後に追加): 分離 12 回の最大値を超えた回数')
for p in ORDER:
    os_ = [o for o in obs if o['pair'] == p]
    if not os_:
        continue
    a = [o for o in os_ if not o['marks']]
    c = [o for o in os_ if not o['bure'] and not o['chg']]
    k = lambda xs: sum(1 for o in xs if o['dragged'])
    print(f'  {p:18} (a) {k(os_)}/{len(os_)}  (b) {k(a)}/{len(a)}  (c) {k(c)}/{len(c)}  '
          f'(d) {sum(1 for o in os_ if o["over_max"])}/{len(os_)}')
