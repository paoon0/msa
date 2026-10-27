#!/usr/bin/env python3
"""ρ が測る範囲 (格子の縮尺) でどう動くか、と pdist-k3 のペアの近い・遠いが保たれるか (2026-10-19)。

背景: アヌビス点検 (2026-10-19) で、OB の ρ は格子の外側を落とすと大きく動くと指摘された
  (frontend 全点 0.35 → 半分の範囲 0.53)。区間 (±0.01) はサイクル間のばらつきだけで、範囲の取り方の揺れは含まない。
  ユーザ決定: 表は残し、ρ の値そのものより「近いペア・遠いペア」に意味がある、という立て付けにする。

データ: results-mix-cpu2.csv の 1 台固定の行。手順は analyze_rho2.py の主推定と同じ
  (D = c + β·buy + ν·view を最小二乗、ρ = ν/β、区間 = サイクル単位のブートストラップ 95%)。
範囲:  全点 (buy≤100, view≤300、17 点) / 3/4 (buy≤75, view≤150、11 点) / 半分 (buy≤50, view≤150、8 点)
補正:  CPU 時間 (主) と、CPU 時間 × ノード平均周波数 [GHz] (DVFS の補正の目安。周波数はノード全コアの平均なので近似)
ペア:  plan-pdist-k3.md の 10 組。Δρ = |ρ_s − ρ_t|。近い / 遠いの境目は NEAR (既定 0.05)。

使い方: python3 analyze_rho_scale.py > analysis-rho-scale.txt
"""
import csv, random, math, collections, sys

PATH = 'results-mix-cpu2.csv'
NB = 1000
NEAR = 0.05
SVC = [('frontend', 'front'), ('productcatalogservice', 'catalog'), ('recommendationservice', 'reco'),
       ('adservice', 'ad'), ('currencyservice', 'currency'), ('cartservice', 'cart'), ('checkoutservice', 'checkout'),
       ('paymentservice', 'payment'), ('shippingservice', 'shipping'), ('emailservice', 'email')]
RANGES = [('全点', lambda b, v: True), ('3/4', lambda b, v: b <= 75 and v <= 150), ('半分', lambda b, v: b <= 50 and v <= 150)]
PAIRS = [('checkout', 'shipping', 'P1b'), ('catalog', 'reco', 'P1b'), ('front', 'cart', 'P2'), ('catalog', 'checkout', 'P2'),
         ('front', 'catalog', 'P3'), ('currency', 'checkout', 'P3'), ('front', 'currency', 'Q1'), ('checkout', 'cart', 'Q1'),
         ('front', 'reco', 'Q2'), ('checkout', 'front', 'Q3')]


def solve(A, B):
    k = len(B); M = [A[i][:] + [B[i]] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]; M[r] = [M[r][j] - f * M[i][j] for j in range(k + 1)]
    return [M[i][k] / M[i][i] for i in range(k)]


def rho(rows):
    X = [(1.0, b, v) for b, v, d in rows]; y = [d for *_, d in rows]
    A = [[sum(x[i] * x[j] for x in X) for j in range(3)] for i in range(3)]
    B = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(3)]
    c, be, nu = solve(A, B)
    return nu / be


def pct(xs, q):
    xs = sorted(xs); i = (len(xs) - 1) * q; lo = math.floor(i)
    return xs[lo] + (xs[min(lo + 1, len(xs) - 1)] - xs[lo]) * (i - lo)


rows = [r for r in csv.DictReader(open(PATH)) if r['replicas'] == '1']
cycles = sorted({r['cycle'] for r in rows}, key=int)
random.seed(20261019)
boots = [[random.choice(cycles) for _ in cycles] for _ in range(NB)]
# data[(mode, range)][short] = {cycle: [(b, v, D)]}
est, ci, bs = {}, {}, {}
for mode in ('CPU時間', '×周波数'):
    for rn, f in RANGES:
        for dep, s in SVC:
            g = collections.defaultdict(list)
            for r in rows:
                b, v = float(r['buy_target']), float(r['view_target'])
                if r['deploy'] != dep or not f(b, v):
                    continue
                d = float(r['usage_mc']) * (float(r['freq_ghz']) if mode == '×周波数' else 1.0)
                g[r['cycle']].append((b, v, d))
            k = (mode, rn, s)
            est[k] = rho([x for c in cycles for x in g[c]])
            bs[k] = [rho([x for c in smp for x in g[c]]) for smp in boots]
            ci[k] = (pct(bs[k], .025), pct(bs[k], .975))

npts = {rn: len({(r['buy_target'], r['view_target']) for r in rows if f(float(r['buy_target']), float(r['view_target']))})
        for rn, f in RANGES}
print(f"# OB の ρ と測る範囲 ({PATH}、1 台固定、{len(cycles)} サイクル、ブートストラップ {NB} 回)")
print("範囲: " + " / ".join(f"{rn} {npts[rn]} 点" for rn, _ in RANGES))
print("[ ] = サイクル単位ブートストラップ 95% 区間 (サイクル間のばらつきだけ。範囲の取り方の揺れは列どうしの差に出る)\n")
for mode in ('CPU時間', '×周波数'):
    print(f"## 1. ρ ({mode})")
    print(f"{'サービス':<10}" + ''.join(f"{rn:>22}" for rn, _ in RANGES) + f"{'範囲による幅':>12}")
    for _, s in SVC:
        vals = [est[(mode, rn, s)] for rn, _ in RANGES]
        cells = ''.join(f"{est[(mode, rn, s)]:8.3f} [{ci[(mode, rn, s)][0]:5.2f},{ci[(mode, rn, s)][1]:5.2f}]" for rn, _ in RANGES)
        print(f"{s:<10}{cells}{max(vals) - min(vals):12.3f}")
    print()

print(f"## 2. pdist-k3 のペアの Δρ = |ρ_s − ρ_t| (近い = Δρ < {NEAR})")
print("   [ ] = 同じリサンプルどうしの差のブートストラップ 95% 区間")
for mode in ('CPU時間', '×周波数'):
    print(f"### {mode}")
    print(f"{'ペア':<20}{'アーム':<6}" + ''.join(f"{rn:>22}" for rn, _ in RANGES) + "  近い/遠い")
    for s, t, arm in PAIRS:
        cells, cls = '', []
        for rn, _ in RANGES:
            d = abs(est[(mode, rn, s)] - est[(mode, rn, t)])
            db = [abs(a - b) for a, b in zip(bs[(mode, rn, s)], bs[(mode, rn, t)])]
            cells += f"{d:8.3f} [{pct(db, .025):5.2f},{pct(db, .975):5.2f}]"
            cls.append('近' if d < NEAR else '遠')
        print(f"{s + '+' + t:<20}{arm:<6}{cells}  {'/'.join(cls)}{'' if len(set(cls)) == 1 else '  ← 範囲で入れ替わる'}")
    print()

print("## 3. ペアの Δρ の順位 (小さい = 近い順)")
for mode in ('CPU時間', '×周波数'):
    print(f"### {mode}")
    for rn, _ in RANGES:
        order = sorted(PAIRS, key=lambda p: abs(est[(mode, rn, p[0])] - est[(mode, rn, p[1])]))
        print(f"  {rn:<4} " + ' < '.join(f"{s}+{t}" for s, t, _ in order))
    print()
