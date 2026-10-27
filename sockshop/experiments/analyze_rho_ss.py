#!/usr/bin/env python3
"""Sock Shop の ρ (閲覧 1 周 ÷ 購入 1 周の CPU) を 1 台・2 台で出す (2026-10-21)。

データ: results-mix-cpu2b.csv (measure-mix-cpu.sh、15 点 × 1台/2台 × 6 サイクル、2026-10-20〜21)
手順:   OB の analyze_rho_scale.py と同じ。D = c + β·buy + ν·view を最小二乗、ρ = ν/β、
        区間 = サイクル単位のブートストラップ 95%。usage_mc は Pod の合計 (2 台なら 2 Pod の和)。
コンテナ: deploy と同名のコンテナだけ (rabbitmq の隣の rabbitmq-exporter は 0 m で、混ぜると式が歪む)。
除外:   取りこぼし > 1% または 絞り > 5% の行 (本走では該当なし。点検用に残す)。
事故:   cyc2 の 2 台ブロックの途中 (2026-10-20 21:08:04 と 21:27:59) に MicroK8s が自分で再起動した
        (journalctl: apiserver-kicker "cert change detected" → kubelite/containerd 停止 → 全 Pod 再起動。
         直前に wlo1 の IPv6 一時アドレスが入れ替わっている)。再起動後は利用者・住所・カードが消え、
        購入の 4 リクエスト中 2 つが失敗 (buy_failed_rate = 0.5)、注文は全滅。
        元の cyc2 × 2 台の 15 点は使わない (ユーザ決定 2026-10-26)。2 台 × 1 サイクルを取り直し、
        REDO (cycle=2 として記録) に差し替える。REDO がまだ無いときは cyc2 × 2 台を除いて出す。
        感度として「cyc2 × 2 台を除いた 5 サイクル」も出す。1 台ブロックは登録し直しているので影響なし。
b48v240: 1 台では front-end が約 1.04 コアで頭打ち (Node.js 1 プロセス、絞りは 0%)。
        ユーザ決定 (2026-10-20) で含めて測り、含めた場合と除いた場合の差を出す。

使い方: python3 analyze_rho_ss.py > analysis-rho-ss.txt
"""
import csv, random, math, collections, os

PATH = 'results-mix-cpu2b.csv'
REDO = 'results-mix-cpu2b-redo2.csv'    # cyc2 × 2 台の取り直し (2026-10-26〜)
NB = 1000
SVC = ['front-end', 'catalogue', 'carts', 'orders', 'payment', 'shipping', 'user', 'queue-master',
       'catalogue-db', 'carts-db', 'orders-db', 'user-db', 'session-db', 'rabbitmq']
INCIDENT = ('2', '2')                         # (cycle, replicas)
HEAVY = 'b48v240'


def solve(A, B):
    k = len(B); M = [A[i][:] + [B[i]] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]; M[r] = [M[r][j] - f * M[i][j] for j in range(k + 1)]
    return [M[i][k] / M[i][i] for i in range(k)]


def fit(rows):
    X = [(1.0, b, v) for b, v, d in rows]; y = [d for *_, d in rows]
    A = [[sum(x[i] * x[j] for x in X) for j in range(3)] for i in range(3)]
    B = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(3)]
    return solve(A, B)          # c, β, ν


def pct(xs, q):
    xs = sorted(xs); i = (len(xs) - 1) * q; lo = math.floor(i)
    return xs[lo] + (xs[min(lo + 1, len(xs) - 1)] - xs[lo]) * (i - lo)


rows = [r for r in csv.DictReader(open(PATH)) if (r['cycle'], r['replicas']) != INCIDENT]
has_redo = os.path.exists(REDO)
if has_redo:
    redo = list(csv.DictReader(open(REDO)))
    assert {(r['cycle'], r['replicas']) for r in redo} == {INCIDENT}, 'REDO は cycle=2・2 台だけのはず'
    rows += redo
fe = {(r['cycle'], r['replicas'], r['point']): r for r in rows if r['deploy'] == 'front-end'}


def bad(r):
    k = fe[(r['cycle'], r['replicas'], r['point'])]
    b, v = float(k['buy_target']), float(k['view_target'])
    drop = max(float(k['buy_dropped_win']) / (b * 180) if b else 0, float(k['view_dropped_win']) / (v * 180) if v else 0)
    return drop > 0.01 or float(r['throttle_pct'] or 0) > 5


nbad = sum(1 for r in rows if r['deploy'] in SVC and bad(r))
VARIANTS = [
    ('1台 全15点', '1', lambda r: True),
    ('1台 b48v240除く', '1', lambda r: r['point'] != HEAVY),
    ('2台 主', '2', lambda r: True),
    ('2台 cyc2除く (5サイクル)', '2', lambda r: r['cycle'] != INCIDENT[0]),
    ('2台 主 b48v240除く', '2', lambda r: r['point'] != HEAVY),
]
random.seed(20261021)
cycles = sorted({r['cycle'] for r in rows}, key=int)
boots = [[random.choice(cycles) for _ in cycles] for _ in range(NB)]
res = {}
for vn, rep, keep in VARIANTS:
    for s in SVC:
        g = collections.defaultdict(list)
        for r in rows:
            if r['deploy'] == s and r['container'] == s and r['replicas'] == rep and keep(r) and not bad(r):
                g[r['cycle']].append((float(r['buy_target']), float(r['view_target']), float(r['usage_mc'])))
        c, be, nu = fit([x for cy in cycles for x in g[cy]])
        bs = []
        for smp in boots:
            pts = [x for cy in smp for x in g[cy]]
            if len({(b, v) for b, v, _ in pts}) >= 3:
                _, b2, n2 = fit(pts); bs.append(n2 / b2)
        res[(vn, s)] = (c, be, nu, nu / be, pct(bs, .025), pct(bs, .975), sum(len(x) for x in g.values()))

print(f"# Sock Shop の ρ ({PATH}、ブートストラップ {NB} 回、サイクル単位)")
print(f"cyc2 × 2 台: " + (f"取り直し ({REDO}) に差し替え" if has_redo else "取り直し未実施のため除外 (「2台 主」は 5 サイクル)"))
print(f"除外 (取りこぼし>1% か 絞り>5%): {nbad} 行")
print("ρ = 閲覧 1 周の CPU ÷ 購入 1 周の CPU。β = 購入 1 周あたり [m・秒/周]、ν = 閲覧 1 周あたり、c = 切片 [m]\n")
for vn, rep, _ in VARIANTS:
    print(f"## {vn}")
    print(f"{'サービス':<14}{'行数':>5}{'c':>8}{'β':>8}{'ν':>8}{'ρ':>9}   95%区間")
    for s in SVC:
        c, be, nu, rho, lo, hi, n = res[(vn, s)]
        print(f"{s:<14}{n:>5}{c:8.1f}{be:8.3f}{nu:8.3f}{rho:9.3f}   [{lo:.3f}, {hi:.3f}]")
    print()

print("## b48v240 を含めた場合と除いた場合の ρ の差 (含めた − 除いた)")
for a, b in [('1台 全15点', '1台 b48v240除く'), ('2台 主', '2台 主 b48v240除く')]:
    print(f"### {a} − {b}")
    for s in SVC:
        ra, rb = res[(a, s)][3], res[(b, s)][3]
        print(f"  {s:<14}{ra:8.3f} {rb:8.3f}  差 {ra - rb:+.3f} ({(ra - rb) / rb * 100 if rb else float('nan'):+.1f}%)")
    print()

print("## front-end の頭打ちの点検: b48v240 を除いた式で b48v240 を予測し、実測と比べる")
for rep in ('1', '2'):
    vn = '1台 b48v240除く' if rep == '1' else '2台 主 b48v240除く'
    c, be, nu = res[(vn, 'front-end')][:3]
    pred = c + be * 48 + nu * 240
    obs = [float(r['usage_mc']) for r in rows if r['deploy'] == 'front-end' and r['replicas'] == rep
           and r['point'] == HEAVY]
    m = sum(obs) / len(obs)
    print(f"  {rep}台: 予測 {pred:.0f} m / 実測平均 {m:.0f} m (n={len(obs)}, {min(obs):.0f}〜{max(obs):.0f})  実測−予測 {m - pred:+.0f} m")
