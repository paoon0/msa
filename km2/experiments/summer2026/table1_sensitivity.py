#!/usr/bin/env python3
"""FOSE2026 表1「必要台数の食い違い」が、必要台数 n の数え方に敏感かを確かめる感度分析。

table1_mismatch.py (表1の再現) と同じ組・分母・欠測の扱いで、n(s) の定義だけを変えて数え直す。
新しい実験はしない。results-mix.csv / results-mix2.csv と timeline-mix.csv / timeline-mix2.csv の再計算のみ。

n の定義 (分離 arm=normal の各 (cycle, view) について、サービス s の台数):
  (a) 窓の終わり   : results-*.csv の replicas 列 (現行。表1と同じ)
  (b) 窓の始め     : results-*.csv の replicas_at_window_start 列
  (c) 最頻値       : 計測窓 [180,420] 秒の時系列で最も長く続いた台数 (秒数で重み付け。同数なら大きい方)
  (d) 窓の途中     : 窓開始から 120 秒 (t_rel=300) に最も近いサンプルの台数
  (e) 時間平均     : 窓内の時間平均 (小数のまま n(A)<n(B) を判定)

計測窓の特定 (bundle-vs-loss2.sh の run_rate): t_rel = k6 Job の Pod が Running になった時刻 (t_run) からの秒。
  ウォームアップ WARM=180 秒 → 計測窓 [WARM, WARM+MEAS] = [180, 420] 秒 (mix.log / mix2.log の START 行: warm=180s meas=240s)。
  replicas_at_window_start は t=180 の kubectl 値、replicas は t=420 の kubectl 値。
  (mix / mix2 は -times.csv 導入前なので時刻表は無い。窓は WARM/MEAS からの推定)
時系列は約15秒ごとのサンプル (最後は t=412 前後)。台数は各サンプルの deploy ごとの ready_replicas
 (kubectl get deploy の AVAILABLE と同じ性質。CSV の列と比べるため) を使う。
  サンプルは「次のサンプルまで値が続く」階段として扱い、窓の外にはみ出す部分は切る。
  窓の始め (t=180) の値は t<=180 の最後のサンプル、最後のサンプルの値は t=420 まで続くとみなす。
  時系列が (cycle, view) について複数回測定された場合は最後の測定を採る (table1_mismatch.py と同じ「最後を採る」)。

使い方: python3 table1_sensitivity.py   (km2/experiments/summer2026/ で実行。出力は標準出力)
"""
import csv, collections, math

CYCLES = {'1', '2', '3', '4', '5'}
VIEWS = ['0', '100', '200', '300']
WARM, MEAS = 180.0, 240.0
LO, HI = WARM, WARM + MEAS
MID = WARM + 120.0
PAIRS = [  # table1_mismatch.py と同一
    ('frontend+reco',     'frontend',        'recommendationservice', 'frontreco',     'mix'),
    ('frontend+catalog',  'frontend',        'productcatalogservice', 'frontcatalog',  'mix'),
    ('checkout+email',    'checkoutservice', 'emailservice',          'checkoutemail', 'mix2'),
    ('frontend+checkout', 'frontend',        'checkoutservice',       'frontcheckout', 'mix2'),
    ('frontend+cart',     'frontend',        'cartservice',           'frontcart',     'mix'),
    ('frontend+email',    'frontend',        'emailservice',          'frontemail',    'mix2'),
    ('(catalog+checkout)', 'productcatalogservice', 'checkoutservice', 'catalogcheckout', 'mix2'),
]
CONSTANT_ROWS = {'frontend+reco', 'frontend+catalog', 'checkout+email'}   # 論文: 反転しない 3 組
FLIP_ROWS = {'frontend+checkout', 'frontend+cart', 'frontend+email'}      # 論文: 反転する 3 組
DEFS = ['a', 'b', 'c', 'd', 'e']
DEFNAME = {'a': '窓の終わり(replicas列)', 'b': '窓の始め(replicas_at_window_start列)',
           'c': '最頻値(窓内で最長)', 'd': '窓の途中(t=300 に最近接)', 'e': '時間平均(小数)'}


def parse(s):
    d = {}
    for t in s.split():
        k, _, v = t.rpartition(':')
        d[k] = int(v)
    return d


def load_results(name):
    """arm -> {(cycle, view): (replicas, replicas_at_window_start)}。最後を採る。"""
    out = collections.defaultdict(dict)
    for r in csv.DictReader(open(f'results-{name}.csv', encoding='utf-8')):
        if r['cycle'] not in CYCLES:
            continue
        out[r['arm']][(r['cycle'], r['browse_rate_target'])] = (parse(r['replicas']), parse(r['replicas_at_window_start']))
    return out


def load_timeline(name):
    """arm=normal の {(cycle, view): {service: [(t, ready, current), ...]}}。t が戻ったら新しい測定とみなし最後を採る。"""
    blocks = collections.defaultdict(list)   # key -> [dict(service -> {t: (ready, cur)})]
    prev = {}
    for r in csv.DictReader(open(f'timeline-{name}.csv', encoding='utf-8')):
        if r['arm'] != 'normal' or r['cycle'] not in CYCLES:
            continue
        k = (r['cycle'], r['browse_rate'])
        t = float(r['t_rel'])
        if k not in prev or t < prev[k]:
            blocks[k].append(collections.defaultdict(dict))
        prev[k] = t
        d = blocks[k][-1][r['deploy']]
        if t not in d:   # 同じ時刻の複数コンテナ行は 1 つだけ (台数は Deployment 単位で同じ)
            d[t] = (int(r['ready_replicas'] or 0), int(r['current_replicas'] or 0))
    out = {}
    for k, bl in blocks.items():
        out[k] = {s: sorted((t, v[0], v[1]) for t, v in d.items()) for s, d in bl[-1].items()}
    return out


def segments(samples, idx):
    """階段関数にして窓 [LO,HI] の (台数, 秒数) 列を返す。"""
    pts = [(t, v[idx - 1] if False else (v)) for t, *v in samples]
    # samples: (t, ready, cur)。idx: 1=ready, 2=current
    seq = [(t, (rdy if idx == 1 else cur)) for t, rdy, cur in samples]
    # 窓の始めの値 = t<=LO の最後のサンプル (無ければ最初)
    before = [x for x in seq if x[0] <= LO]
    start_val = before[-1][1] if before else seq[0][1]
    inside = [x for x in seq if LO < x[0] < HI]
    segs, t0, v0 = [], LO, start_val
    for t, v in inside:
        segs.append((v0, t - t0))
        t0, v0 = t, v
    segs.append((v0, HI - t0))
    return segs


def defs_from_timeline(samples, idx=1):
    seq = [(t, (rdy if idx == 1 else cur)) for t, rdy, cur in samples]
    segs = segments(samples, idx)
    dur = collections.defaultdict(float)
    for v, d in segs:
        dur[v] += d
    c = max(dur.items(), key=lambda kv: (round(kv[1], 6), kv[0]))[0]   # 最長 → 同数なら大きい方
    e = sum(v * d for v, d in segs) / (HI - LO)
    mid = min(seq, key=lambda x: (abs(x[0] - MID), -x[0]))[1]
    return c, mid, e


def main():
    res = {n: load_results(n) for n in ('mix', 'mix2')}
    tls = {n: load_timeline(n) for n in ('mix', 'mix2')}
    out = []
    P = out.append

    # n[def][(src, cycle, view)][service]
    # 組ごとの点で使う (cycle, view, service) の値
    def nval(src, c, v, svc, d):
        endv, startv = res[src]['normal'][(c, v)]
        if d == 'a': return endv[svc]
        if d == 'b': return startv[svc]
        samples = tls[src].get((c, v), {}).get(svc)
        if not samples: return None
        cc, mid, e = defs_from_timeline(samples)
        return {'c': cc, 'd': mid, 'e': e}[d]

    # --- 点検: 時系列と CSV の整合 ---
    P('=== 点検: 時系列 (ready_replicas) と results CSV の整合 (arm=normal, 全サービス, cycle1-5) ===')
    for src in ('mix', 'mix2'):
        nend = nendbad = nst = nstbad = ntot = 0
        nendcur = 0
        bad_end, bad_st = [], []
        nopt = 0
        for (c, v), (endv, startv) in sorted(res[src]['normal'].items()):
            tl = tls[src].get((c, v))
            if not tl:
                nopt += 1
                continue
            for svc in endv:
                if svc not in tl:
                    continue
                s = tl[svc]
                ntot += 1
                last = [x for x in s if x[0] <= HI][-1]
                # 窓の終わり: 最後のサンプル (t<=420)
                nend += 1
                if last[1] != endv[svc]:
                    nendbad += 1
                    bad_end.append((c, v, svc, endv[svc], last[1], last[0]))
                if last[2] != endv[svc]:
                    nendcur += 1
                nst += 1
                near = min(s, key=lambda x: abs(x[0] - LO))
                if near[1] != startv[svc]:
                    nstbad += 1
                    bad_st.append((c, v, svc, startv[svc], near[1], near[0]))
        P(f'[{src}] 比較数={ntot} (時系列が無い点={nopt})  終わり: CSV≠最後のサンプル(ready) {nendbad}件 / current_replicas 基準なら {nendcur}件'
          f'  始め: CSV≠t=180最近接サンプル {nstbad}件')
        for x in bad_end[:30]:
            P(f'    終わりずれ cyc{x[0]} view{x[1]} {x[2]}: CSV={x[3]} 時系列={x[4]} (t={x[5]:.0f})')
        for x in bad_st[:30]:
            P(f'    始めずれ  cyc{x[0]} view{x[1]} {x[2]}: CSV={x[3]} 時系列={x[4]} (t={x[5]:.0f})')

    # --- 台数が窓内で変わった点 (分離 normal の 40 点) ---
    changed = 0
    tot = 0
    for src in ('mix', 'mix2'):
        for (c, v), (endv, startv) in res[src]['normal'].items():
            tot += 1
            if endv != startv:
                changed += 1
    P(f'\n分離 normal で replicas_at_window_start != replicas の点: {changed} / {tot} (cycle1-5 の全サービス比較)')

    # --- 判定 ---
    verdict = {}   # (def, pair) -> {(cycle,view): -1/0/+1}
    table = {}
    for name, a, b, arm, src in PAIRS:
        for d in DEFS:
            cnt = {v: [0, 0] for v in VIEWS}
            seen = 0
            cells = {}
            for v in VIEWS:
                for c in sorted(CYCLES):
                    if (c, v) not in res[src]['normal'] or (c, v) not in res[src][arm]:
                        continue
                    na, nb = nval(src, c, v, a, d), nval(src, c, v, b, d)
                    if na is None or nb is None:
                        continue
                    seen += 1
                    s = -1 if na < nb - 1e-9 else (1 if na > nb + 1e-9 else 0)
                    # (e) は小数。同じ整数でも秒数で僅かに差が出るのを「食い違い」と数えないよう、別途 0.5 台未満の差も併記する
                    cells[(c, v)] = s
                    if s < 0: cnt[v][0] += 1
                    elif s > 0: cnt[v][1] += 1
            verdict[(d, name)] = cells
            table[(d, name)] = (cnt, seen)

    P('\n=== 表 (n< = n(左)<n(右) の点数, n> = n(左)>n(右) の点数。各 view の内訳は 0/100/200/300) ===')
    for d in DEFS:
        P(f'\n--- 定義 ({d}) {DEFNAME[d]} ---')
        P(f"{'組':20s} " + ' '.join(f"{'v'+v:>8s}" for v in VIEWS) + '   n<  n>   計/分母  向き')
        for name, *_ in PAIRS:
            cnt, seen = table[(d, name)]
            cs = []
            for v in VIEWS:
                lt, gt = cnt[v]
                cs.append(f'{lt}<{gt}>' if lt and gt else (f'{lt}<' if lt else (f'{gt}>' if gt else '---')))
            lt = sum(x[0] for x in cnt.values()); gt = sum(x[1] for x in cnt.values())
            kind = '両向き(反転)' if lt and gt else ('一定(<のみ)' if lt else ('一定(>のみ)' if gt else '食い違い無し'))
            P(f'{name:20s} ' + ' '.join(f'{x:>8s}' for x in cs) + f'  {lt:3d} {gt:3d}   {lt+gt}/{seen}   {kind}')
    # 向きの分類: 論文の定義は「全 view・全 cycle を通して n< か n> の片方だけか」ではなく、
    # 表 1 のセルが (view ごとに) 向きを替えるか。ここでは (i) 行内に <,> 両方があるか、
    # (ii) view ごとの主な向き(<,>)が view 間で替わるか、の 2 つを出す。
    P('\n=== 向きの分類 (論文: 上段 3 組=反転せず / 下段 3 組=反転) ===')
    P('  反転A = 行内に n< と n> の点が両方ある (cycle・view を通して)')
    P('  反転B = view ごとの向き (そのview内で多い方。同数・無しは除く) が view 間で替わる')
    for d in DEFS:
        row = []
        for name, *_ in PAIRS:
            cnt, seen = table[(d, name)]
            lt = sum(x[0] for x in cnt.values()); gt = sum(x[1] for x in cnt.values())
            A = bool(lt and gt)
            dirs = set()
            for v in VIEWS:
                l, g = cnt[v]
                if l > g: dirs.add('<')
                elif g > l: dirs.add('>')
            B = len(dirs) > 1
            row.append((name, A, B))
        P(f'({d}) ' + ' / '.join(f"{n}:A={'反転' if A else '一定'},B={'反転' if B else '一定'}" for n, A, B in row))
    P('\n  参考: 論文の分類 一定=' + ', '.join(sorted(CONSTANT_ROWS)) + ' / 反転=' + ', '.join(sorted(FLIP_ROWS)))

    # --- (a) と判定が変わったセル ---
    P('\n=== 判定が (a) 窓の終わり と変わったセル (cycle, view, 組)。符号: <は n(左)<n(右), >は n(左)>n(右), =は等しい ===')
    sym = {-1: '<', 0: '=', 1: '>'}
    for d in DEFS[1:]:
        P(f'\n--- 定義 ({d}) {DEFNAME[d]} ---')
        ndiff = 0
        for name, *_ in PAIRS:
            ca, cd = verdict[('a', name)], verdict[(d, name)]
            for k in sorted(ca):
                if k in cd and ca[k] != cd[k]:
                    ndiff += 1
                    P(f'  {name:20s} cyc{k[0]} view{k[1]:>3s}: (a){sym[ca[k]]} -> ({d}){sym[cd[k]]}')
        P(f'  変わったセル数: {ndiff}')
        for name, *_ in PAIRS:
            ca, cd = verdict[('a', name)], verdict[(d, name)]
            miss = [k for k in ca if k not in cd]
            if miss:
                P(f'  (注) {name}: 時系列が無く比較不能 {miss}')

    # (e) の補足: 小数判定で「ほぼ等しい」を食い違いに数えていないか (差が 0.25 台未満の食い違い点)
    P('\n=== 補足 (e): 小数判定で差が 0.25 台未満しかないのに食い違いと数えた点 (時間平均が整数にならない所為の可能性) ===')
    cnt_small = 0
    for name, a, b, arm, src in PAIRS:
        for (c, v), s in sorted(verdict[('e', name)].items()):
            if s != 0:
                na, nb = nval(src, c, v, a, 'e'), nval(src, c, v, b, 'e')
                if abs(na - nb) < 0.25:
                    cnt_small += 1
                    P(f'  {name:20s} cyc{c} view{v:>3s}: n(A)={na:.3f} n(B)={nb:.3f} (a)の判定={sym[verdict[("a", name)][(c, v)]]}')
    P(f'  件数: {cnt_small}')

    print('\n'.join(out))


if __name__ == '__main__':
    main()
