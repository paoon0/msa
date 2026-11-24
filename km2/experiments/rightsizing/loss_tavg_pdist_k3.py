#!/usr/bin/env python3
"""pdist-k3 の損を「時間平均の台数」で数える (2026-11-17 にユーザと決めた数え方、2026-11-23 初めて実装)。

台数: 計測窓 (t_rel 310–590 s) の 15 s ごとの current_replicas の平均 (= 時間の平均、小数でよい)。
分離: サービスごとに 12 サイクルの時間平均台数の平均 n̄_s と sd。分かれ方 (各回を四捨五入した台数の回数) も併記。
同居: 回ごとの同居 Pod の時間平均台数 n_st。
損 (回ごと) = n_st × Σ r − Σ n̄_s r_s  [m]  (同居 − 分離。プラス = 同居の損、マイナス = 得)
  内訳: s の分 = r_s (n_st − n̄_s)。足すと損に戻る。プラスの側 = 余分に持たされた (引きずられた) 側。
ふれ幅: 分離の予約枠 (この組のメンバーだけ) の 12 回の sd = sd_sep。
  回ごとの判定: 損 > 2 sd_sep → 損 / 損 < −2 sd_sep → 得 / それ以外 → 区別できない。
  (sd_sep = 0 のときは |損| > 1m で判定)
組 × 配合ごと: 3 回の損の平均 ± 2 SE (SE = √(sd_同居²/3 + sd_sep²/12))。
内訳で「引きずられた」と数えるのは r_s (n_st − n̄_s) > 2 r_s sd_s かつ n_st − n̄_s > 0.1 台。

使い方: python3 loss_tavg_pdist_k3.py [同居] [分離] [枠表]   既定 = pdistk3pair3 pdistk3sep3 rightsize-pdist-k3-mc5.csv
出力: 標準出力 (analysis-pdistk3-3-tavg.txt に保存する) と loss-tavg-pdistk3-3.csv (BOM 付き、回ごと 1 行)
"""
import csv, collections, math, statistics as st, sys

PAIR = sys.argv[1] if len(sys.argv) > 1 else 'pdistk3pair3'
SEP = sys.argv[2] if len(sys.argv) > 2 else 'pdistk3sep3'
TABLE = sys.argv[3] if len(sys.argv) > 3 else 'rightsize-pdist-k3-mc5.csv'
S = '/home/mizuki/ダウンロード/msa/km2/experiments/summer2026/'
LO, HI = 310, 590
MIXES = ['b100v0', 'b50v150', 'b50v300', 'b75v200', 'b0v300']
DEP = {'front': ('frontend', 'server'), 'catalog': ('productcatalogservice', 'server'),
       'reco': ('recommendationservice', 'server'), 'currency': ('currencyservice', 'server'),
       'cart': ('cartservice', 'server'), 'checkout': ('checkoutservice', 'checkout'),
       'shipping': ('shippingservice', 'server')}
# 組 → (アーム, 同居 Pod の Deployment, 台数を読むコンテナ)。analyze_pdist_k3.py の ARMS と同じ。Δρ は analysis-pdistk3-3.txt §2
HOST = {'checkout+shipping': ('pairsP1b', 'checkoutservice', 'checkout', 0.005),
        'front+catalog': ('pairsP3', 'frontend', 'server', 0.006),
        'front+reco': ('pairsQ2', 'frontend', 'server', 0.007),
        'front+catalog+reco': ('frontrecocatalog', 'frontend', 'server', 0.013),
        'catalog+reco': ('pairsP1b', 'productcatalogservice', 'server', 0.013),
        'front+currency': ('pairsQ1', 'frontend', 'server', 0.050),
        'front+cart': ('pairsP2', 'frontend', 'server', 0.131),
        'checkout+cart': ('pairsQ1', 'checkoutservice', 'checkout', 0.179),
        'currency+checkout': ('pairsP3', 'checkoutservice', 'checkout', 0.260),
        'catalog+checkout': ('pairsP2', 'productcatalogservice', 'server', 0.304),
        'checkout+front': ('pairsQ3', 'frontend', 'checkout', 0.310)}

req = {(r['deploy'], r['container']): int(r['request_m']) for r in csv.DictReader(open(TABLE))}
R = {s: req[d] for s, d in DEP.items()}


def tavg(name):
    g = collections.defaultdict(list)
    for r in csv.DictReader(open(S + f'timeline-{name}.csv')):
        if r['current_replicas'] and r['container'] != '-' and LO <= float(r['t_rel']) <= HI:
            g[(r['cycle'], r['arm'], r['point'], r['deploy'], r['container'])].append(int(r['current_replicas']))
    return {k: (st.mean(v), len(v)) for k, v in g.items()}


sep, par = tavg(SEP), tavg(PAIR)
cycles = sorted({k[0] for k in sep}, key=int)
sepv = {(m, s): [sep[(c, 'normal', m) + DEP[s]][0] for c in cycles] for m in MIXES for s in DEP}
nbar = {k: st.mean(v) for k, v in sepv.items()}
nsd = {k: st.stdev(v) for k, v in sepv.items()}


def split(v):
    c = collections.Counter(round(x) for x in v)
    return ','.join(f'{n}台{k}回' for n, k in sorted(c.items()))


print(f'pdist-k3 の損 (時間平均の台数)。同居 {PAIR}、分離 {SEP} ({len(cycles)} 回)、枠 {TABLE}、窓 t_rel {LO}–{HI} s')
print('損 = 同居の平均台数 × Σ枠 − Σ(分離 12 回の平均台数 × 枠) [m]。判定は分離の予約枠の 12 回の sd (sd_sep) の 2 倍と比べる\n')
print('§1 分離の時間平均台数 (12 回の平均 ± sd、分かれ方は各回を四捨五入した台数の回数。sd = 0 は分かれ方を省略)')
for s in DEP:
    print(f'  {s:9}' + '  '.join(f'{m}:{nbar[(m, s)]:.2f}' + (f'±{nsd[(m, s)]:.2f}({split(sepv[(m, s)])})' if nsd[(m, s)] > 0 else '')
                                   for m in MIXES))

rows, summ = [], []
print('\n§2 組 × 配合ごと (同居 3 回)。分離 = メンバー順の n̄、同居 = 回ごとの平均台数、損 = 3 回の平均 ± 2SE、判定 = 損/得/区別なし の回数')
for pair, (arm, dep, ct, drho) in HOST.items():
    mem = pair.split('+'); sumr = sum(R[s] for s in mem)
    allL, ncnt, gcnt, side = [], 0, 0, collections.Counter()
    print(f'\n{pair} (Δρ {drho:.3f}、枠 ' + ' + '.join(f'{s} {R[s]}m' for s in mem) + f' = {sumr}m)')
    for m in MIXES:
        sepres = [sum(sep[(c, 'normal', m) + DEP[s]][0] * R[s] for s in mem) for c in cycles]
        sepmean, sepsd = st.mean(sepres), st.stdev(sepres)
        Ls, ns, jud = [], [], []
        for c in '123':
            n, k = par[(c, arm, m, dep, ct)]
            L = n * sumr - sepmean
            parts = {s: R[s] * (n - nbar[(m, s)]) for s in mem}
            th = 2 * sepsd if sepsd > 0 else 1
            j = '損' if L > th else ('得' if L < -th else '区別なし')
            drag = [s for s in mem if n - nbar[(m, s)] > max(2 * nsd[(m, s)], 0.1)]
            for s in drag: side[s] += 1
            Ls.append(L); ns.append(n); jud.append(j)
            rows.append({'組': pair, 'Δρ': drho, '配合': m, '周': c, '同居の平均台数': round(n, 3), 'サンプル数': k,
                         **{f'分離の平均台数_{i + 1}': round(nbar[(m, s)], 3) for i, s in enumerate(mem)},
                         **{f'分離のsd_{i + 1}': round(nsd[(m, s)], 3) for i, s in enumerate(mem)},
                         '分離の予約枠(組)[m]': round(sepmean), '分離の予約枠のsd[m]': round(sepsd),
                         '同居の予約枠(組)[m]': round(n * sumr), '損[m]': round(L),
                         **{f'内訳_{i + 1}[m]': round(parts[s]) for i, s in enumerate(mem)},
                         'メンバー(順)': '・'.join(mem), '判定': j, '引きずられた側': '・'.join(drag)})
        allL += Ls; ncnt += jud.count('損'); gcnt += jud.count('得')
        se = math.sqrt((st.stdev(Ls) ** 2) / 3 + sepsd ** 2 / len(cycles))
        print(f'  {m:8} 分離 ' + '/'.join(f'{nbar[(m, s)]:.2f}' for s in mem) + f'  同居 ' + ' '.join(f'{x:.2f}' for x in ns)
              + f'  損 {st.mean(Ls):+6.0f} ± {2 * se:4.0f}m  (分離の sd {sepsd:3.0f}m)  判定 ' + ' '.join(jud))
    summ.append((pair, drho, ncnt, gcnt, st.mean(allL), side))

print('\n§3 まとめ (15 回 = 5 配合 × 3 回)')
print(f"  {'組':20}{'Δρ':>6}  損の回  得の回  損の平均[m]  引きずられた側 (回数)")
for pair, drho, ncnt, gcnt, ml, side in summ:
    print(f'  {pair:20}{drho:6.3f}  {ncnt:2d}/15  {gcnt:2d}/15  {ml:+9.0f}    ' + ' '.join(f'{s}×{v}' for s, v in side.items()))
near = [x for x in summ if x[1] <= 0.013]; far = [x for x in summ if x[1] >= 0.13]
print(f'\n  ρ が近い組 (Δρ ≤ 0.013): 損 {sum(x[2] for x in near)}/{15 * len(near)}、得 {sum(x[3] for x in near)}/{15 * len(near)}')
print(f'  ρ が遠い組 (Δρ ≥ 0.13): 損 {sum(x[2] for x in far)}/{15 * len(far)}、得 {sum(x[3] for x in far)}/{15 * len(far)}')

cols = []
for r in rows:
    for c in r:
        if c not in cols: cols.append(c)
with open('loss-tavg-pdistk3-3.csv', 'w', newline='', encoding='utf-8-sig') as f:   # BOM 付き = Excel で文字化けしない
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
