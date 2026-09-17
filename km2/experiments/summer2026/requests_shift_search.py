#!/usr/bin/env python3
"""FOSE2026 §5「向きが一定な3組は 5--9%，反転する3組は 28--48% のずらしを要した」の計算。

2026-09-13 20:27 に awk ワンライナーで計算し TeX に直接書いた値の Python 移植 (2026-09-18)。
元の awk はセッション記録 (~/.claude/projects/c--msa/8798bd8a-….jsonl 行 3211) にのみ残っていた。

方法 (元の awk と同じ):
  需要 D_s(cycle, view) = HPA 利用率/100 × 現在台数 を、timeline-*.csv の normal 行の
      全サンプル (t_rel の区間を限定しない) で平均したもの。
  組 (A, B) の予約枠をそれぞれ kA, kB 倍 (0.20〜4.00, 0.01 刻み) したときの必要台数を
      n_s(k) = max(1, ceil(D_s / k / 0.77))          θ = 0.77 = 目標 70% × 許容幅 1.1
  とし、両サービスとも観測がある全点で n_A == n_B となる (kA, kB) のうち
      max(|kA−1|, |kB−1|) が最小のものを「解」、その値を「ずらし」とする。

結果 (論文値):
  frontend+reco 9% / frontend+catalog 8% / checkout+email 5%   → 5--9%
  frontend+cart 28% / frontend+checkout 48% / frontend+email 47% → 28--48%

★注意 (2026-09-18 に判明): 元の awk は需要の平均に**ウォームアップ中 (0--180 s) のサンプルも含めて**いる。
  論文本文は「180 秒のウォームアップ後 240 秒を計測」と書いているので、記述と計算が食い違う。
  計測窓 180--420 s だけで同じ探索 (両側 2D・θ=0.77) をすると
    一定組: reco 7% / catalog 11% / checkout+email 8%   → 7--11%
    反転組: cart 24% / frontend+checkout 19% / frontend+email 42% → 19--42%
  となり、結論 (反転組は大きなずらしを要する) は変わらないが数値は変わる。
  カメラレディで本文と整合させるなら --window の値に差し替える。

使い方: python3 requests_shift_search.py            # 論文の方法 (全区間平均・θ=0.77・両側 2D)
        python3 requests_shift_search.py --window   # 計測窓 180--420 s のみ (本文の記述と整合する版)
        python3 requests_shift_search.py --variant  # 片側のみ・θ=0.70・計測窓のみ (再構成の別案、参考)
"""
import csv, math, collections, statistics as st, sys

THETA = 0.77
CYCLES = {'1', '2', '3', '4', '5'}
VIEWS = ['0', '100', '200', '300']
PAIRS = [
    ('frontend+reco',     'frontend',        'recommendationservice', 'mix'),
    ('frontend+catalog',  'frontend',        'productcatalogservice', 'mix'),
    ('checkout+email',    'checkoutservice', 'emailservice',          'mix2'),
    ('frontend+cart',     'frontend',        'cartservice',           'mix'),
    ('frontend+checkout', 'frontend',        'checkoutservice',       'mix2'),
    ('frontend+email',    'frontend',        'emailservice',          'mix2'),
]
WARM, MEAS = 180, 240


def demand(exp, window=False):
    """(cycle, view) -> {service: D}。window=True なら計測窓 180--420 s のサンプルだけ使う。"""
    acc = collections.defaultdict(list)
    for r in csv.DictReader(open(f'timeline-{exp}.csv', encoding='utf-8')):
        if r['arm'] != 'normal' or r['cycle'] not in CYCLES or not r['hpa_util_pct']:
            continue
        if window and not (WARM <= float(r['t_rel']) <= WARM + MEAS):
            continue
        acc[(r['cycle'], r['browse_rate'], r['deploy'])].append(
            float(r['hpa_util_pct']) / 100 * int(r['current_replicas']))
    out = collections.defaultdict(dict)
    for (c, v, s), vals in acc.items():
        out[(c, v)][s] = st.mean(vals)
    return out


def n_of(D, k, theta):
    return max(1, math.ceil(D / k / theta - 1e-12))


def search_2d(points, theta, ks):
    best = None
    for ka in ks:
        na = [n_of(Da, ka, theta) for Da, _ in points]
        for kb in ks:
            if all(n_of(Db, kb, theta) == a for (_, Db), a in zip(points, na)):
                m = max(abs(ka - 1), abs(kb - 1))
                if best is None or m < best[0]:
                    best = (m, ka, kb)
    return best


variant = '--variant' in sys.argv
window = variant or ('--window' in sys.argv)
ks = [round(i / 100, 2) for i in range(20, 401)]
dem = {e: demand(e, window=window) for e in ('mix', 'mix2')}
theta = 0.70 if variant else THETA
print('【variant: 計測窓のみ・θ=0.70・両側 2D】' if variant else
      ('【計測窓 180--420 s のみ・θ=0.77・両側 2D (本文の記述と整合する版)】' if window else
       '【論文の方法: 全区間平均・θ=0.77・両側 2D 探索】'))
print(f"{'組み合わせ':18s} {'点数':>4s} {'最小ずらし':>8s}   (kA, kB)")
for name, a, b, exp in PAIRS:
    pts = [(d[a], d[b]) for k, d in sorted(dem[exp].items()) if a in d and b in d]
    r = search_2d(pts, theta, ks)
    if r is None:
        print(f"{name:18s} {len(pts):4d}   解なし")
    else:
        print(f"{name:18s} {len(pts):4d} {r[0]*100:7.0f}%   ({a}×{r[1]:.2f}, {b}×{r[2]:.2f})")
