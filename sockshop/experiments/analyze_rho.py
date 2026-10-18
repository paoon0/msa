#!/usr/bin/env python3
"""Sock Shop の ρ (2026-10-19 本測定 results-mix-cpu.csv)。手順は OB の analyze_rho2.py (plan-rho2.md §3) と同じ。

需要モデル: D = c + β·buy + ν·view  (D [m] = Deployment の CPU 使用量、buy/view [周/s])
  β, ν = 1 周あたりの CPU [CPU ミリ秒/周]。ρ = ν/β。
区間 = サイクル単位のブートストラップ (2000 回、パーセンタイル 95%、乱数種 20261019)。参考にサイクルごとの当てはめの t 区間。
除外 = 取りこぼし (窓) が目標 × MEAS の 1% 超 → その (点, サイクル) を全サービス除外。絞り > 5% → そのサービスだけ除外。
感度 = 交互作用 γ·buy·view を入れた当てはめ、CPU 周波数 [GHz] を説明変数に足した当てはめ。

使い方: python3 analyze_rho.py [results-mix-cpu.csv] > analysis-rho.txt
"""
import csv, collections, random, sys, math

PATH = sys.argv[1] if len(sys.argv) > 1 else 'results-mix-cpu.csv'
MEAS = 180
SVCS = ['front-end', 'catalogue', 'carts', 'orders', 'user', 'payment', 'shipping', 'queue-master',
        'catalogue-db', 'carts-db', 'orders-db', 'user-db', 'session-db', 'rabbitmq']
STATEFUL = {'catalogue-db', 'carts-db', 'orders-db', 'user-db', 'session-db', 'rabbitmq'}
NB = 2000
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571}


def solve(A, B):
    k = len(B); M = [A[i][:] + [B[i]] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]; M[r] = [M[r][j] - f * M[i][j] for j in range(k + 1)]
    return [M[i][k] / M[i][i] for i in range(k)]


def ols(X, y):
    k = len(X[0])
    A = [[sum(x[i] * x[j] for x in X) for j in range(k)] for i in range(k)]
    B = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(k)]
    return solve(A, B)


def fit(rows, mode='base'):
    if mode == 'base':
        X = [(1.0, b, v) for b, v, f, d in rows]
    elif mode == 'inter':
        X = [(1.0, b, v, b * v) for b, v, f, d in rows]
    else:  # freq
        X = [(1.0, b, v, f) for b, v, f, d in rows]
    return ols(X, [d for *_, d in rows])


rows = list(csv.DictReader(open(PATH)))
excl_pt, excl_svc = set(), []
for r in rows:
    b, v = float(r['buy_target']), float(r['view_target'])
    if float(r['buy_dropped_win'] or 0) > 0.01 * b * MEAS or float(r['view_dropped_win'] or 0) > 0.01 * v * MEAS:
        excl_pt.add((r['cycle'], r['point']))
data = collections.defaultdict(list)    # svc -> [(cycle, b, v, freq, D)]
for r in rows:
    if r['deploy'] not in SVCS or (r['cycle'], r['point']) in excl_pt:
        continue
    if float(r['throttle_pct']) > 5.0:
        excl_svc.append((r['deploy'], r['cycle'], r['point'])); continue
    data[r['deploy']].append((r['cycle'], float(r['buy_target']), float(r['view_target']),
                              float(r['freq_ghz']), float(r['usage_mc'])))
cycles = sorted({c for v in data.values() for c, *_ in v})
npts = len({(r['cycle'], r['point']) for r in rows})
print(f"# Sock Shop ρ  ({PATH})")
print(f"点×サイクル = {npts}、サイクル = {len(cycles)}。除外: 取りこぼし {len(excl_pt)} 件、絞り>5% {len(excl_svc)} 件 {excl_svc[:5]}")
print()

random.seed(20261019)
boots = [[random.choice(cycles) for _ in cycles] for _ in range(NB)]


def by_cycle(svc):
    g = collections.defaultdict(list)
    for c, b, v, f, d in data[svc]:
        g[c].append((b, v, f, d))
    return g


def pct(xs, q):
    xs = sorted(xs); i = (len(xs) - 1) * q; lo = math.floor(i)
    return xs[lo] + (xs[min(lo + 1, len(xs) - 1)] - xs[lo]) * (i - lo)


res = {}
print("## 1. 主推定 D = c + β·buy + ν·view (1 台、全点)")
print(f"{'サービス':<14}{'c[m]':>7}{'β[m/周]':>9}{'ν[m/周]':>9}{'ρ=ν/β':>8}  {'ρ 95%区間 (ブートストラップ)':<28}{'ρ t区間 (サイクル別)':<22}{'R²':>6}")
for s in SVCS:
    g = by_cycle(s); allr = [x for c in cycles for x in g[c]]
    c0, be, nu = fit(allr)
    y = [d for *_, d in allr]; ym = sum(y) / len(y)
    pred = [c0 + be * b + nu * v for b, v, f, d in allr]
    r2 = 1 - sum((a - p) ** 2 for a, p in zip(y, pred)) / max(sum((a - ym) ** 2 for a in y), 1e-9)
    br = []
    bb = []
    for samp in boots:
        rr = [x for c in samp for x in g[c]]
        _, b1, n1 = fit(rr)
        br.append(n1 / b1 if b1 != 0 else float('inf')); bb.append((b1, n1))
    pc = []
    for c in cycles:
        _, b1, n1 = fit(g[c]); pc.append(n1 / b1 if b1 != 0 else float('nan'))
    m = sum(pc) / len(pc); sd = (sum((x - m) ** 2 for x in pc) / (len(pc) - 1)) ** .5
    h = T975[len(pc) - 1] * sd / len(pc) ** .5
    res[s] = dict(c=c0, b=be, n=nu, rho=nu / be if be else float('inf'), boot=br, bb=bb, g=g)
    lo, hi = pct(br, .025), pct(br, .975)
    tag = ' (状態)' if s in STATEFUL else ''
    print(f"{s + tag:<14}{c0:7.1f}{be:9.2f}{nu:9.3f}{res[s]['rho']:8.3f}  [{lo:7.3f}, {hi:7.3f}]{'':<10}[{m - h:6.3f}, {m + h:6.3f}]{'':<6}{r2:6.3f}")
print()
print("β と ν の 95% 区間 (ブートストラップ)")
for s in SVCS:
    bb = res[s]['bb']
    print(f"  {s:<14} β [{pct([x[0] for x in bb], .025):7.2f}, {pct([x[0] for x in bb], .975):7.2f}]   ν [{pct([x[1] for x in bb], .025):7.3f}, {pct([x[1] for x in bb], .975):7.3f}]")
print()

print("## 2. 感度: 交互作用 γ·buy·view、周波数 [GHz] を足した当てはめでの ρ")
print(f"{'サービス':<14}{'ρ 主':>8}{'ρ 交互作用':>11}{'γ[m/(周/s)²]':>14}{'ρ 周波数込み':>12}{'周波数係数[m/GHz]':>18}")
for s in SVCS:
    allr = [x for c in cycles for x in res[s]['g'][c]]
    c1, b1, n1, ga = fit(allr, 'inter')
    c2, b2, n2, fq = fit(allr, 'freq')
    print(f"{s:<14}{res[s]['rho']:8.3f}{n1 / b1:11.3f}{ga:14.4f}{n2 / b2:12.3f}{fq:18.1f}")
print()

APP = [s for s in SVCS if s not in STATEFUL]
print("## 3. アプリのサービスどうしの ρ の差 (同じリサンプルで ρ_s − ρ_t、95% 区間が 0 を含まなければ「区別できる」)")
for i, s in enumerate(APP):
    for t in APP[i + 1:]:
        d = [a - b for a, b in zip(res[s]['boot'], res[t]['boot'])]
        lo, hi = pct(d, .025), pct(d, .975)
        print(f"  {s:<13} − {t:<13} {res[s]['rho'] - res[t]['rho']:8.3f}  [{lo:7.3f}, {hi:7.3f}]  {'区別できる' if lo > 0 or hi < 0 else '区別できない'}")
print()
print("## 4. 感度: CPU 周波数で割り戻した仕事量 W = D × 周波数 [m·GHz] で当てはめた ρ")
print("   (負荷が増えるとノードの平均周波数が 1.4→2.8 GHz に上がり、同じ仕事の CPU 時間が縮む。周波数はノード全コアの平均で近似)")
print(f"{'サービス':<14}{'ρ 主 (CPU時間)':>14}{'ρ 仕事量':>10}{'  ρ 仕事量 95%区間':<24}{'β_W':>8}{'ν_W':>8}{'R² 時間→仕事量':>16}")
def r2(rows, co):
    y = [d for *_, d in rows]; ym = sum(y) / len(y)
    return 1 - sum((d - (co[0] + co[1] * b + co[2] * v)) ** 2 for b, v, f, d in rows) / max(sum((a - ym) ** 2 for a in y), 1e-9)
for s in SVCS:
    g = res[s]['g']
    gw = {c: [(b, v, f, d * f) for b, v, f, d in g[c]] for c in cycles}
    allw = [x for c in cycles for x in gw[c]]; allt = [x for c in cycles for x in g[c]]
    cw, bw, nw = fit(allw)
    br = []
    for samp in boots:
        _, b1, n1 = fit([x for c in samp for x in gw[c]]); br.append(n1 / b1 if b1 else float('inf'))
    print(f"{s:<14}{res[s]['rho']:14.3f}{nw / bw:10.3f}  [{pct(br, .025):7.3f}, {pct(br, .975):7.3f}]{'':<4}{bw:8.2f}{nw:8.3f}{r2(allt, fit(allt)):8.3f}→{r2(allw, (cw, bw, nw)):.3f}")
