#!/usr/bin/env python3
"""pdist-k3 の同居を (組, 配合, サイクル) ごとに 1 行で並べる詳細表 (2026-11-23)。

入力:
  - analyze_pdist_k3.py の出力 (既定 analysis-pdistk3-3.txt): §1 分離の台数の分布、§3 の判定 (台数・引きずり・損・利用率・印)
  - summer2026/timeline-<pair>.csv: 計測窓 (t_rel 310–590 s) の中の同居 Pod の台数の動き・Ready 不足・HPA の望む台数
  - summer2026/events-<pair>.csv と results-<pair>-times.csv: 載らない Pod (FailedScheduling) の t_rel と、窓の中か外か
出力: detail-pdistk3-3.csv と detail-pdistk3-3.md (同じ内容。md は人が読む用)

使い方: python3 detail_pdist_k3.py [解析出力] [同居の名前] [出力の頭]
  既定 = analysis-pdistk3-3.txt pdistk3pair3 detail-pdistk3-3
"""
import csv, collections, datetime, re, sys

ANA = sys.argv[1] if len(sys.argv) > 1 else 'analysis-pdistk3-3.txt'
PAIR = sys.argv[2] if len(sys.argv) > 2 else 'pdistk3pair3'
OUT = sys.argv[3] if len(sys.argv) > 3 else 'detail-pdistk3-3'
S = '/home/mizuki/ダウンロード/msa/km2/experiments/summer2026/'
LO, HI = 310, 590
MIXES = ['b100v0', 'b50v150', 'b50v300', 'b75v200', 'b0v300']

# 組 → (アーム, ホスト Deployment, 台数を読むコンテナ)。analyze_pdist_k3.py の ARMS と同じ対応
HOST = {'checkout+shipping': ('pairsP1b', 'checkoutservice', 'checkout'),
        'catalog+reco': ('pairsP1b', 'productcatalogservice', 'server'),
        'front+cart': ('pairsP2', 'frontend', 'server'),
        'catalog+checkout': ('pairsP2', 'productcatalogservice', 'server'),
        'front+catalog': ('pairsP3', 'frontend', 'server'),
        'currency+checkout': ('pairsP3', 'checkoutservice', 'checkout'),
        'front+currency': ('pairsQ1', 'frontend', 'server'),
        'checkout+cart': ('pairsQ1', 'checkoutservice', 'checkout'),
        'front+reco': ('pairsQ2', 'frontend', 'server'),
        'checkout+front': ('pairsQ3', 'frontend', 'checkout'),
        'front+catalog+reco': ('frontrecocatalog', 'frontend', 'server')}
POD_PREFIX = {'checkoutservice': 'checkoutservice-', 'productcatalogservice': 'productcatalogservice-', 'frontend': 'frontend-'}

# ---- 解析出力を読む ----
txt = open(ANA).read().split('\n')
sepdist = {}   # 短縮名 → [配合ごとの分布文字列]
rho = {}       # 組 → Δρ
judge = {}     # (組, 配合, cyc) → dict
sec = 0
for l in txt:
    if l.startswith('§1'): sec = 1; continue
    if l.startswith('§2'): sec = 2; continue
    if l.startswith('§3'): sec = 3; continue
    if l.startswith('§4'): sec = 4; continue
    if sec == 1:
        p = l.split()
        if len(p) == 6 and p[0] not in ('b100v0',):
            sepdist[p[0]] = [x.lstrip('*') for x in p[1:]]
    elif sec == 2:
        m = re.match(r'^(\S+\+\S+)\s+([\d.]+)\s', l)
        if m: rho[m.group(1)] = float(m.group(2))
    elif sec == 3:
        m = re.match(r'^(\S+)\s+(b\d+v\d+)\s+分離 (\S+)( B:\S+)?\s+(.*)$', l)
        if not m: continue
        pair, mix, sepmode, b, rest = m.groups()
        for c in re.split(r'\s+(?=c\d: )', rest):
            mm = re.match(r'c(\d): (\d+) \[(\S+) (\d+)\] ([+-]\d+)m u(\S+) \(c ([^)]+)\)(.*)$', c)
            if not mm: continue
            cyc, nst, side, dn, loss, u, samec, tail = mm.groups()
            judge[(pair, mix, cyc)] = dict(sep_mode=sepmode, sep_flap=(b or '').replace(' B:', ''),
                                           n_st=int(nst), dragged=side if side != '-' else '', dn=int(dn),
                                           loss_m=int(loss), util=u, sep_samecycle=samec,
                                           marks=tail.strip().lstrip('*') if '*' in tail else '')

# ---- 時系列 ----
tl = collections.defaultdict(list)
for r in csv.DictReader(open(S + f'timeline-{PAIR}.csv')):
    tl[(r['cycle'], r['arm'], r['point'], r['deploy'], r['container'])].append(r)
# ---- 載らない Pod ----
trun = {}
for x in csv.DictReader(open(S + f'results-{PAIR}-times.csv')):
    trun[(x['cycle'], x['arm'], x['point'])] = float(x['t_run'])
fs = collections.defaultdict(list)   # (cyc, arm, point) → [(t_rel, Deployment 名)]
for e in csv.DictReader(open(S + f'events-{PAIR}.csv')):
    if 'nsufficient' not in e['message'] and 'schedul' not in e['message'].lower():
        continue
    k = (e['cycle'], e['arm'], e['point'])
    if k not in trun: continue
    t = datetime.datetime.fromisoformat(e['time'].replace('Z', '+00:00')).timestamp() - trun[k]
    dep = re.sub(r'-[0-9a-f]{8,10}-[0-9a-z]{5}$', '', e['object'])
    fs[k].append((round(t), dep))

rows = []
for pair, (arm, dep, cont) in HOST.items():
    members = pair.split('+')
    for mix in MIXES:
        for cyc in '123':
            j = judge.get((pair, mix, cyc))
            if j is None: continue
            s = sorted((float(x['t_rel']), int(x['current_replicas']), x['desired_replicas'], int(x['ready_replicas'] or 0))
                       for x in tl[(cyc, arm, mix, dep, cont)] if x['current_replicas'])
            w = [x for x in s if LO <= x[0] <= HI]
            before = [x for x in s if x[0] < LO]
            last = before[-1][1] if before else None
            ch = []
            for t, n, d, rd in w:
                if last is not None and n != last: ch.append(f'{t:.0f}s {last}→{n}')
                last = n
            short = [f'{t:.0f}s' for t, n, d, rd in w if rd < n]
            want = [f'{t:.0f}s→{d}' for t, n, d, rd in w if d not in ('', None) and int(d) > n]
            # 台数ごとの窓内の滞在サンプル数
            stay = collections.Counter(n for _, n, _, _ in w)
            ev = fs.get((cyc, arm, mix), [])
            own = [f'{t}s' for t, d in ev if d == dep]
            oth = [f'{d}@{t}s' for t, d in ev if d != dep]
            inwin = [t for t, d in ev if d == dep and LO <= t <= HI]
            rows.append({
                '組': pair, 'Δρ': rho.get(pair, ''), '配合': mix, '周': cyc,
                '分離の台数(最頻)': j['sep_mode'],
                '分離12回の分布': ' / '.join(f'{m}:{sepdist[m][MIXES.index(mix)]}' for m in members if m in sepdist),
                '分離の同じ番号の周': j['sep_samecycle'],
                '同居の台数(判定)': j['n_st'],
                '窓の始め': w[0][1] if w else '', '窓の終わり': w[-1][1] if w else '',
                '台数ごとのサンプル数': ' '.join(f'{n}台×{c}' for n, c in sorted(stay.items())),
                '窓内の台数変化': ', '.join(ch),
                'HPAが今より多く望んだ時刻': ', '.join(want),
                'Ready不足の時刻': ', '.join(short),
                '引きずられた側': j['dragged'], 'Δn': j['dn'], '損[m]': j['loss_m'],
                '窓平均の利用率%(メンバー順)': j['util'],
                '同居Podが載らない(t_rel)': ', '.join(own), 'うち窓の中': 'あり' if inwin else '',
                '他のPodが載らない': ', '.join(oth),
                '解析の印': j['marks'],
            })

cols = list(rows[0].keys())
with open(OUT + '.csv', 'w', newline='', encoding='utf-8-sig') as f:   # BOM 付き = Excel で文字化けしない
    wr = csv.DictWriter(f, fieldnames=cols); wr.writeheader(); wr.writerows(rows)
with open(OUT + '.md', 'w') as f:
    f.write(f'# pdist-k3 3 回目 同居の全サイクル詳細\n\n生成: `python3 detail_pdist_k3.py {ANA} {PAIR} {OUT}` (入力 `{ANA}`、'
            f'`../summer2026/timeline-{PAIR}.csv`、`../summer2026/events-{PAIR}.csv`、`../summer2026/results-{PAIR}-times.csv`)。'
            f'計測窓 = t_rel {LO}–{HI} s (15 s ごとのサンプル)。台数・損・利用率は解析出力と同じ値。\n\n')
    f.write('| ' + ' | '.join(cols) + ' |\n|' + '---|' * len(cols) + '\n')
    for r in rows:
        f.write('| ' + ' | '.join(str(r[c]) for c in cols) + ' |\n')
print(f'{len(rows)} 行 → {OUT}.csv, {OUT}.md')
