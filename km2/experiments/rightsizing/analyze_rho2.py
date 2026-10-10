#!/usr/bin/env python3
"""mix-cpu2 の解析 (plan-rho2.md §3 のとおり)。

需要モデル: D = c + β·buy + ν·view  (D [m] = Deployment の Pod 合計の CPU 使用量、buy/view [周/s])
  β, ν = 1 周あたりの CPU [CPU ミリ秒/周]。ρ = ν/β、a = c/β。
区間 = サイクル単位のブートストラップ (2000 回、パーセンタイル 95%、乱数種 20261010)。
  参考に、サイクルごとに当てた値の t 区間 (自由度 = 有効サイクル数 − 1) も出す。
比較 = 同じリサンプル (同じサイクルの組) で ρ_s − ρ_t を出し、その 95% 区間が 0 を含まなければ「区別できる」。
除外 = 取りこぼし (窓) が目標 × 180 s の 1% 超 → その (点, サイクル, 台数) を全サービス除外。
       絞り > 5% → そのサービスだけ除外。summary が回収できなかった点 (achieved が空) も除外して件数を報告する。

使い方: python3 analyze_rho2.py [results-mix-cpu2.csv] [results-mix-cpu.csv]  > analysis-rho2.txt
"""
import csv, collections, random, sys, math

NEW = sys.argv[1] if len(sys.argv) > 1 else 'results-mix-cpu2.csv'
OLD = sys.argv[2] if len(sys.argv) > 2 else 'results-mix-cpu.csv'
SVCS = ['frontend', 'productcatalogservice', 'recommendationservice', 'adservice', 'currencyservice',
        'cartservice', 'checkoutservice', 'paymentservice', 'shippingservice', 'emailservice']
SHORT = {'frontend': 'front', 'productcatalogservice': 'catalog', 'recommendationservice': 'reco',
         'adservice': 'ad', 'currencyservice': 'currency', 'cartservice': 'cart', 'checkoutservice': 'checkout',
         'paymentservice': 'payment', 'shippingservice': 'shipping', 'emailservice': 'email'}
NB = 2000
REF = (50.0, 150.0)
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365}


def solve(A, B):
    k = len(B); M = [A[i][:] + [B[i]] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]; M[r] = [M[r][j] - f * M[i][j] for j in range(k + 1)]
    return [M[i][k] / M[i][i] for i in range(k)]


def ols(rows, inter=False):
    """rows = [(buy, view, D)] → [c, β, ν(, γ)]"""
    X = [(1.0, b, v, b * v) if inter else (1.0, b, v) for b, v, _ in rows]
    y = [d for *_, d in rows]; k = len(X[0])
    A = [[sum(x[i] * x[j] for x in X) for j in range(k)] for i in range(k)]
    B = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(k)]
    return solve(A, B)


def load(path, report=False):
    data = collections.defaultdict(list)   # (svc, n) -> [(cycle, buy, view, D)]
    excl_pt, excl_svc, nosum = set(), [], set()
    rows = list(csv.DictReader(open(path)))
    for r in rows:
        key = (r['cycle'], r['point'], r['replicas'])
        b, v = float(r['buy_target']), float(r['view_target'])
        if r['buy_achieved'] == '' and b > 0 or r['view_achieved'] == '' and v > 0:
            nosum.add(key); continue
        if float(r['buy_dropped_win'] or 0) > 0.01 * b * 180 or float(r['view_dropped_win'] or 0) > 0.01 * v * 180:
            excl_pt.add(key)
    for r in rows:
        key = (r['cycle'], r['point'], r['replicas'])
        if r['deploy'] not in SVCS or key in excl_pt or key in nosum:
            continue
        if float(r['throttle_pct'] or 0) > 5:
            excl_svc.append((key, r['deploy'])); continue
        data[(r['deploy'], r['replicas'])].append(
            (int(r['cycle']), float(r['buy_target']), float(r['view_target']), float(r['usage_mc'])))
    if report:
        print(f'除外: 取りこぼし超過の点 {len(excl_pt)} 件 {sorted(excl_pt)}')
        print(f'      summary 未回収の点 {len(nosum)} 件 {sorted(nosum)}')
        print(f'      絞り > 5% のサービス {len(excl_svc)} 件 {excl_svc[:10]}')
    return data


def params(rows, sel=lambda b, v: True, inter=False):
    p = ols([(b, v, d) for _, b, v, d in rows if sel(b, v)], inter)
    c, be, nu = p[:3]
    out = {'c': c, 'beta': be, 'nu': nu, 'rho': nu / be, 'a': c / be}
    if inter:
        out['gamma'] = p[3]
    return out


def boot(rows, fn, seed):
    cyc = sorted({x[0] for x in rows}); rnd = random.Random(seed); out = []
    by = {c: [x for x in rows if x[0] == c] for c in cyc}
    for _ in range(NB):
        pick = [rnd.choice(cyc) for _ in cyc]
        out.append(fn([x for c in pick for x in by[c]]))
    return out


def pct(xs, q):
    xs = sorted(xs); i = q * (len(xs) - 1); lo = int(math.floor(i)); hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def tint(vals):
    n = len(vals); m = sum(vals) / n; sd = (sum((x - m) ** 2 for x in vals) / (n - 1)) ** 0.5
    h = T975.get(n - 1, 2.0) * sd / n ** 0.5
    return m - h, m + h


SEED = 20261010
new = load(NEW, report=True)
old = load(OLD)
OLD_RHO = {'frontend': 0.29, 'productcatalogservice': 0.29, 'recommendationservice': 0.31, 'cartservice': 0.13,
           'currencyservice': 0.19, 'adservice': 0.76}

for n in ['1', '2']:
    print(f'\n==================== {n} 台固定 ====================')
    print('§主推定 (全 17 点 × 有効サイクル)。[ ] = サイクルブートストラップ 95%、( ) = サイクル別の t 区間')
    print(f'{"svc":9} {"行":>4} {"c[m]":>7} {"β":>7} {"ν":>7} {"ρ=ν/β":>6} {"ρ boot95":>15} {"ρ t95":>15} {"a=c/β":>6} {"a boot95":>15}  10/07ρ(buy>0)')
    boots = {}
    for s in SVCS:
        rows = new[(s, n)]
        p = params(rows)
        bs = boot(rows, lambda rr: params(rr), SEED)
        boots[s] = bs
        per = [params([x for x in rows if x[0] == c])['rho'] for c in sorted({x[0] for x in rows})]
        tl, th = tint(per)
        o = params([x for x in old[(s, n)] if x[1] > 0])['rho'] if old.get((s, n)) else float('nan')
        rl, rh = pct([b['rho'] for b in bs], .025), pct([b['rho'] for b in bs], .975)
        al, ah = pct([b['a'] for b in bs], .025), pct([b['a'] for b in bs], .975)
        print(f'{SHORT[s]:9} {len(rows):4} {p["c"]:7.1f} {p["beta"]:7.2f} {p["nu"]:7.2f} {p["rho"]:6.2f} [{rl:5.2f},{rh:5.2f}] ({tl:5.2f},{th:5.2f}) {p["a"]:6.1f} [{al:6.1f},{ah:6.1f}]  {o:5.2f}')

    print('\n§サービス間の差 ρ_s − ρ_t (同じリサンプルどうしの差)。* = 95% 区間が 0 を含まない = 区別できる')
    keys = [s for s in SVCS if s not in ('checkoutservice', 'paymentservice', 'shippingservice', 'emailservice')]
    keys.append('checkoutservice')
    for i, s in enumerate(keys):
        for t in keys[i + 1:]:
            d = [a['rho'] - b['rho'] for a, b in zip(boots[s], boots[t])]
            pe = params(new[(s, n)])['rho'] - params(new[(t, n)])['rho']
            lo, hi = pct(d, .025), pct(d, .975)
            print(f'  {SHORT[s]:>8} − {SHORT[t]:<8} {pe:+6.3f} [{lo:+6.3f},{hi:+6.3f}] {"*" if lo > 0 or hi < 0 else ""}')
    print('  買う側どうし (checkout/payment/shipping/email) の ρ:',
          ' '.join(f'{SHORT[s]}={params(new[(s, n)])["rho"]:+.3f}' for s in SVCS[6:]))

    print('\n§感度: 当て直す範囲・交互作用 (ρ = ν/β、交互作用モデルは γ [m/(周/s)^2] と b=50 での実効 ρ=(ν+γ·50)/(β+γ·150) も)')
    print(f'{"svc":9} {"全点":>6} {"buy>0":>6} {"buy≤50":>7} {"buy≥50":>7} | {"交互:ρ":>6} {"γ×1e3":>7} {"γ boot95":>15} {"実効ρ@b50v150":>13}')
    for s in SVCS:
        rows = new[(s, n)]
        r0 = params(rows)['rho']; r1 = params(rows, lambda b, v: b > 0)['rho']
        r2 = params(rows, lambda b, v: b <= 50)['rho']; r3 = params(rows, lambda b, v: b >= 50)['rho']
        pi = params(rows, inter=True)
        gb = boot(rows, lambda rr: params(rr, inter=True)['gamma'], SEED)
        eff = (pi['nu'] + pi['gamma'] * REF[0]) / (pi['beta'] + pi['gamma'] * REF[1])
        print(f'{SHORT[s]:9} {r0:6.2f} {r1:6.2f} {r2:7.2f} {r3:7.2f} | {pi["rho"]:6.2f} {pi["gamma"]*1e3:7.2f} '
              f'[{pct(gb,.025)*1e3:6.2f},{pct(gb,.975)*1e3:6.2f}] {eff:13.2f}')

    print(f'\n§モデルを使わない比較: P_s(m) = D_s(m)/D_s(b50v150)、サイクル内で正規化して対の比 P_s/P_t。')
    print('  各点のサイクル平均 (最小〜最大)。1 から離れるほど「配合を変えたときに利用率が揃わない」')
    pts = sorted({(b, v) for _, b, v, _ in new[('frontend', n)]})
    pairs = [('frontend', 'productcatalogservice'), ('frontend', 'recommendationservice'),
             ('productcatalogservice', 'recommendationservice'), ('cartservice', 'currencyservice'),
             ('frontend', 'currencyservice'), ('frontend', 'cartservice'), ('frontend', 'checkoutservice'),
             ('cartservice', 'checkoutservice'), ('checkoutservice', 'paymentservice'),
             ('shippingservice', 'emailservice')]
    D = {s: {(c, b, v): d for c, b, v, d in new[(s, n)]} for s in SVCS}
    hdr = ' '.join(f'b{int(b)}v{int(v)}'.rjust(8) for b, v in pts)
    print(f'  {"pair":18} {hdr}   最大|ln|')
    for s, t in pairs:
        cells = []; worst = 0
        for b, v in pts:
            vals = []
            for c in range(1, 7):
                try:
                    ps = D[s][(c, b, v)] / D[s][(c,) + REF]; pt_ = D[t][(c, b, v)] / D[t][(c,) + REF]
                    vals.append(ps / pt_)
                except KeyError:
                    pass
            m = sum(vals) / len(vals); worst = max(worst, abs(math.log(m)))
            cells.append(f'{m:8.2f}')
        print(f'  {SHORT[s]+"/"+SHORT[t]:18} {" ".join(cells)}   {worst:.2f}')
