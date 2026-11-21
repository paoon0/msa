#!/usr/bin/env python3
"""需要モデル D = c + β·buy + ν·view の当たり具合を、サービスごとに図で見る (2026-11-19)。

当て方・除外は analyze_rho2.py と同じ (全 17 点 × 有効サイクル、台数ごとに別に当てる)。
  除外 = 取りこぼし (窓) が目標 × 180 s の 1% 超 → その (点, サイクル, 台数) を全サービス除外 /
         絞り > 5% → そのサービスだけ除外 / summary 未回収の点も除外。
図の横軸 = 「購入に換算した負荷」 x = buy + ρ·view (ρ = ν/β はそのサービス・台数で当てた値)。
  こうすると平面 D = c + β·buy + ν·view が 1 本の直線 D = c + β·x になり、
  点と直線の縦のずれ = 回帰の残差 そのもの (平面で見たずれと同じ)。
% は基準の配合 b50v150 での直線の値 (枠の元になる D) に対する割合
  (予測で割ると、閲覧だけの配合で予測 ≈ 0 になる購入側サービスで発散するため)。
出力は 1 つの HTML (ブラウザで開く。外部ライブラリ不要)。

使い方: python3 plot_fit_mix.py results-mix-cpu4.csv fig-fit-mix-cpu4.html
"""
import csv, collections, json, sys, math

SRC = sys.argv[1] if len(sys.argv) > 1 else 'results-mix-cpu4.csv'
OUT = sys.argv[2] if len(sys.argv) > 2 else 'fig-fit-mix-cpu4.html'
SVCS = ['frontend', 'productcatalogservice', 'recommendationservice', 'adservice', 'currencyservice',
        'cartservice', 'checkoutservice', 'paymentservice', 'shippingservice', 'emailservice']
SHORT = {'frontend': 'frontend', 'productcatalogservice': 'catalog', 'recommendationservice': 'reco',
         'adservice': 'ad', 'currencyservice': 'currency', 'cartservice': 'cart', 'checkoutservice': 'checkout',
         'paymentservice': 'payment', 'shippingservice': 'shipping', 'emailservice': 'email'}


def solve(A, B):
    k = len(B); M = [A[i][:] + [B[i]] for i in range(k)]
    for i in range(k):
        p = max(range(i, k), key=lambda r: abs(M[r][i])); M[i], M[p] = M[p], M[i]
        for r in range(k):
            if r != i:
                f = M[r][i] / M[i][i]; M[r] = [M[r][j] - f * M[i][j] for j in range(k + 1)]
    return [M[i][k] / M[i][i] for i in range(k)]


def ols(rows):
    X = [(1.0, b, v) for b, v, _ in rows]; y = [d for *_, d in rows]
    A = [[sum(x[i] * x[j] for x in X) for j in range(3)] for i in range(3)]
    B = [sum(x[i] * yy for x, yy in zip(X, y)) for i in range(3)]
    return solve(A, B)


rows = list(csv.DictReader(open(SRC)))
excl_pt, nosum = set(), set()
for r in rows:
    key = (r['cycle'], r['point'], r['replicas'])
    b, v = float(r['buy_target']), float(r['view_target'])
    if r['buy_achieved'] == '' and b > 0 or r['view_achieved'] == '' and v > 0:
        nosum.add(key); continue
    if float(r['buy_dropped_win'] or 0) > 0.01 * b * 180 or float(r['view_dropped_win'] or 0) > 0.01 * v * 180:
        excl_pt.add(key)

pts = collections.defaultdict(list)   # (svc, n) -> [dict]
for r in rows:
    if r['deploy'] not in SVCS:
        continue
    key = (r['cycle'], r['point'], r['replicas'])
    why = ('取りこぼし超過' if key in excl_pt else 'summary 未回収' if key in nosum
           else '絞り > 5%' if float(r['throttle_pct'] or 0) > 5 else '')
    pts[(r['deploy'], r['replicas'])].append({
        'cyc': int(r['cycle']), 'pt': r['point'], 'b': float(r['buy_target']), 'v': float(r['view_target']),
        'D': float(r['usage_mc']), 'thr': float(r['throttle_pct'] or 0), 'ex': why,
        'p50b': r['buy_p50'], 'p50v': r['view_p50']})

out = {}
for (s, n), ps in sorted(pts.items()):
    use = [p for p in ps if not p['ex']]
    c, be, nu = ols([(p['b'], p['v'], p['D']) for p in use])
    rho = nu / be
    for p in ps:
        p['x'] = p['b'] + rho * p['v']
        p['pred'] = c + be * p['b'] + nu * p['v']
        p['res'] = p['D'] - p['pred']
    m = sum(p['D'] for p in use) / len(use)
    sse = sum(p['res'] ** 2 for p in use); sst = sum((p['D'] - m) ** 2 for p in use)
    # 点 (配合) ごとのサイクル平均の残差 = サイクル間のばらつきを除いた「形のずれ」
    bymix = collections.defaultdict(list)
    for p in use:
        bymix[p['pt']].append(p)
    mixres = [sum(q['res'] for q in g) / len(g) for g in bymix.values()]
    dref = c + be * 50 + nu * 150   # 枠を決めた基準の配合 b50v150 での直線の値。% の分母に使う
    mixrel = [100 * x / dref for x in mixres]
    out.setdefault(n, {})[s] = {
        'name': SHORT[s], 'c': c, 'beta': be, 'nu': nu, 'rho': rho, 'n_use': len(use), 'n_ex': len(ps) - len(use),
        'r2': 1 - sse / sst, 'dref': dref, 'rmse': math.sqrt(sse / len(use)), 'rmse_pct': 100 * math.sqrt(sse / len(use)) / dref,
        'mix_rmse': math.sqrt(sum(x * x for x in mixres) / len(mixres)),
        'mix_worst_pct': max(mixrel, key=abs),
        'pts': [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in p.items()} for p in ps]}

TEMPLATE = open(__file__.replace('plot_fit_mix.py', 'plot_fit_mix.template.html')).read()
open(OUT, 'w').write(TEMPLATE.replace('/*DATA*/null', json.dumps(out, ensure_ascii=False))
                     .replace('{{SRC}}', SRC))
for n in sorted(out):
    print(f'== {n} 台')
    for s in SVCS:
        f = out[n][s]
        print(f"{f['name']:9} ρ={f['rho']:.3f} R²={f['r2']:.4f} RMSE={f['rmse']:.1f}m ({f['rmse_pct']:.1f}%) "
              f"配合平均の RMSE={f['mix_rmse']:.1f}m 最大ずれ={f['mix_worst_pct']:+.1f}% 使用{f['n_use']} 除外{f['n_ex']}")
