#!/usr/bin/env python3
"""同居ペアの「損」を、分離構成の測定だけから前向きに予測する (前向き検証用の予測表を作る)。

目的:
  2つのサービスを1 Pod に同居させると、HPA は「各コンテナの metric の desired の最大」で台数を決める。
  必要台数の違う相手と束ねると、冷たい側も余分に複製され、予約枠 (requests × 台数) が増える = 「損」。
  どのペアが buy:view の配合を変えても台数が揃ったままか (= 損が出ないか) を、同居実験を見ずに予測し、
  この予測表 (predictions-pairs.csv) を固定 (コミット) してから、同居実験で答え合わせする。

入力 (分離構成・HPA無し・全サービス台数固定、2026-10-07 実測。measure-mix-cpu.sh の出力):
  results-mix-cpu.csv  1行 = 1点(配合) × 1 Deployment。usage_mc = その Deployment 全 Pod 合計の CPU [m]。
  deploy=k6load (負荷生成器) は除く。redis-cart は常に1台なので予測対象から除く (10 サービスが対象)。

モデル (n = 台数 1 または 2。n ごとに別々に最小二乗):
  D_n(b, v) = c_n + β_n·b + ν_n·v     [m]   (b = buy 周/s, v = view 周/s, 全 Pod 合計の CPU)
  当てはめは (旧: 全10点 / 既定: buy>0 の8点) × 3サイクルの生の行から直接 (サイクル平均の平均は取らない)。正規方程式を純 Python で解く。
  n≥3 は外挿  D_n = D2 + (n-2)(D2 - D1)  で、使ったら「外挿」フラグ。負の値は 0 に切る。
  (補足: D2 > D1 になるのは、2台目のアイドル分に加え、台数が増えると1台あたりの効率が落ちるため。κ=(D2-D1)/D1)

不確かさ δ (旧定義 independent の説明。既定の common は上の (2) を参照):
  δ_{s,n} = leave-one-point-out (1点を全サイクル分抜いて残りで当て、抜いた点の各行の相対誤差) の RMS。
  n≥3 の D には δ_{s,2} を使う (外挿は別途フラグで「不明」にする)。

枠 (予約枠):
  r_s = D1_s(b_ref, v_ref) / θ  を整数 m に丸める。θ 既定 0.70、基準ミックス既定 buy100 / view0 (FOSE と同じ)。
  rightsize3-requests.csv に出す。bundle-vs-loss2.sh の RSTABLE (RIGHTSIZE=1) と apply_rightsize.py は
  列 deploy, container, request_m だけを読み、余分な列は無視する (確認済)。redis-cart は表に無いと
  apply_rightsize.py が警告を出してマニフェストの枠のまま使うので、既存 summer2026/rightsize-requests.csv
  の値 (50m) を1行だけ転記する (予測対象外、--redis-m で変更可)。

HPA 定常状態のシミュレーション (安定化窓は定常に影響しないので無視):
  現台数 n、metric ごとに u = D_n / (n·r)  (Pod 平均利用率)、ratio = u / 0.70。
  |ratio - 1| ≤ 0.1 なら desired = n (許容幅)、そうでなければ desired = ceil(n·ratio)。
  同居 Pod は2コンテナの desired の最大。min 1 / max 8。開始台数 n0 から n ← desired(n) を固定点まで反復。
  振動 (固定点に着かず周期に入る) なら「振動」フラグ。
  ※ 同居による通信 CPU の減少は無視する (各コンテナの D はそれぞれのサービスの分離時の D_n をそのまま使う)。
  開始台数 n0 = 1 と 2 を別々に予測する。

損:
  loss_m = n_st·(r_s + r_t) - (n_s·r_s + n_t·r_t)  [m]   (n_st = 同居 Pod の台数)

判定:
  D に不確かさの倍率をかけたケース (既定は上の 27 通り、independent なら 9 通り) を計算する。全ケースで loss=0 → 「損なし」、全ケースで loss>0 → 「損あり」、
  混在 → 「不明」。外挿・振動が1ケースでも絡めば「不明」。
  (注: loss<0 になるケースは理論上ほぼ無いが、出たら「損なし」でも「損あり」でもなく混在扱いになる)

★2026-10-08 の定義変更 (実験結果を見る前の前向き検証の範囲内。予測表を固定する前に行った):
  (1) 当てはめの範囲: 既定は buy>0 の8点だけで当てる (v100, v200 を当てはめにも δ にも使わない)。
      理由: 予測格子は buy=100 固定・view 0〜150 なので、関係する領域で当てたい。checkout/payment/shipping/email
      は view だけの点では呼ばれず CPU がほぼ 0 (b=0 で原点に戻る非線形) で、直線モデルが合わず、相対誤差の δ が
      100〜270% に膨らんで判定がほぼ全部「不明」になっていた。旧定義 (全10点) は --fit-all-points で残す。
  (2) 不確かさの分解 (既定 --delta-mode common): 点ごとに全サービスがそろって同じ倍率で動く (暫定解析で 0.90〜1.05)
      ので、それをサービスごとに独立に振るのは過大。そこで leave-one-point-out の予測 pred と実測 meas から
        g_{p,c} = median_s(meas/pred)  (点 p・サイクル c ごとの共通倍率。median は U_ref ≥ 100m の主要サービスだけで取る)
        δ_common   = RMS(g - 1)                       (n=1, n=2 別。全点・全サイクル)
        δ_indiv,s  = RMS(meas/(pred·g) - 1)           (サービス別。n=1, n=2 別)
      に分け、D を (1+kc·δ_common)(1+ki·δ_indiv,s) 倍して判定する: kc ∈ {-1,0,1} × 同居ペアの2サービスの ki ∈ {-1,0,1}
      の 27 通り (分離の n_s, n_t も同じ 27 通りの中で、同じ kc・そのサービスの ki で計算)。
      旧定義 (サービスごとに独立に δ を振る9通り) は --delta-mode independent で残す。
  (3) ポート衝突: 同居 Pod では同じポートを2コンテナが使えないため、km2/normal/*.yaml の containerPort と PORT 環境変数から
      各サービスの待ち受けポート表 (PORTS) を持ち、ペアごとに衝突を判定して port_conflict 列に出す (判定 category には混ぜない)。

使い方 (実行ディレクトリは問わない。既定値で動く):
  python3 predict_pairs.py
  python3 predict_pairs.py --fit-all-points --delta-mode independent   (2026-10-08 以前の旧定義)
  python3 predict_pairs.py --theta 0.70 --ref-buy 100 --ref-view 0 --grid-buy 100 --grid-view 0 50 100 150

出力: predictions-pairs.csv, rightsize3-requests.csv, 標準出力 (係数・判定一覧・集計)。
"""
import argparse, csv, math, os, itertools
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser()
ap.add_argument('--input', default=os.path.join(HERE, 'results-mix-cpu.csv'))
ap.add_argument('--theta', type=float, default=0.70)
ap.add_argument('--ref-buy', type=float, default=100)
ap.add_argument('--ref-view', type=float, default=0)
ap.add_argument('--grid-buy', type=float, nargs='+', default=[100])
ap.add_argument('--grid-view', type=float, nargs='+', default=[0, 50, 100, 150])
ap.add_argument('--target', type=float, default=0.70, help='HPA の目標利用率')
ap.add_argument('--tol', type=float, default=0.10, help='HPA の許容幅')
ap.add_argument('--nmin', type=int, default=1)
ap.add_argument('--nmax', type=int, default=8)
ap.add_argument('--fit-all-points', action='store_true', help='旧定義: buy=0 の点 (v100, v200) も当てはめと δ に使う')
ap.add_argument('--delta-mode', choices=['common', 'independent'], default='common')
ap.add_argument('--major-min-m', type=float, default=100, help='共通倍率 g の median を取るサービスの U_ref 下限 [m]')
ap.add_argument('--redis-m', type=int, default=50)
ap.add_argument('--delta-k', type=float, default=1.0, help='不確かさの幅の倍率 K (±K·δ で振る)。2026-10-08 の事前登録で主評価 K=1、副評価 K=2')
ap.add_argument('--out-pred', default=os.path.join(HERE, 'predictions-pairs.csv'))
ap.add_argument('--out-req', default=os.path.join(HERE, 'rightsize3-requests.csv'))
a = ap.parse_args()

SERVICES = ['frontend', 'checkoutservice', 'cartservice', 'productcatalogservice', 'currencyservice',
            'paymentservice', 'shippingservice', 'emailservice', 'recommendationservice', 'adservice']
ABBR = {'frontend': 'front', 'checkoutservice': 'checkout', 'cartservice': 'cart',
        'productcatalogservice': 'catalog', 'currencyservice': 'currency', 'paymentservice': 'payment',
        'shippingservice': 'shipping', 'emailservice': 'email', 'recommendationservice': 'reco',
        'adservice': 'ad'}

# ---------- 読み込み ----------
rows = defaultdict(list)       # (deploy, n) -> [(point, cycle, b, v, usage)]
container = {}
for r in csv.DictReader(open(a.input)):
    d = r['deploy']
    if d not in SERVICES:
        continue                # k6load, redis-cart を除く
    container[d] = r['container']
    rows[(d, int(r['replicas']))].append(
        (r['point'], int(r['cycle']), float(r['buy_target']), float(r['view_target']), float(r['usage_mc'])))


def solve3(A, y):
    """正規方程式 (XtX)w = Xty を 3x3 のガウス消去で解く。A の各行は (1, b, v)。"""
    M = [[sum(x[i] * x[j] for x in A) for j in range(3)] + [sum(x[i] * yy for x, yy in zip(A, y))] for i in range(3)]
    for i in range(3):
        p = max(range(i, 3), key=lambda k: abs(M[k][i]))
        M[i], M[p] = M[p], M[i]
        for k in range(3):
            if k != i:
                f = M[k][i] / M[i][i]
                M[k] = [M[k][j] - f * M[i][j] for j in range(4)]
    return [M[i][3] / M[i][i] for i in range(3)]


def fit(data):
    return solve3([(1.0, b, v) for _, _, b, v, _ in data], [u for *_, u in data])


def used(data):
    return data if a.fit_all_points else [x for x in data if x[2] > 0]


coef = {}
loo = {}          # (s, n) -> [(点, サイクル, 予測, 実測)]  leave-one-point-out
for s in SERVICES:
    for n in (1, 2):
        data = used(rows[(s, n)])
        coef[(s, n)] = fit(data)
        out = []
        for p in sorted({x[0] for x in data}):
            w = fit([x for x in data if x[0] != p])
            for pp, cy, b, v, u in data:
                if pp == p:
                    out.append((p, cy, w[0] + w[1] * b + w[2] * v, u))
        loo[(s, n)] = out

def D(s, n, b, v):
    """n 台のときのサービス s の全 Pod 合計 CPU [m]。n≥3 は外挿。戻り値 (値, 外挿したか)。"""
    f = lambda k: max(0.0, coef[(s, k)][0] + coef[(s, k)][1] * b + coef[(s, k)][2] * v)
    if n <= 2:
        return f(n), False
    return max(0.0, f(2) + (n - 2) * (f(2) - f(1))), True


# ---------- 枠 ----------
req = {}
U_ref = {}
for s in SERVICES:
    U_ref[s] = D(s, 1, a.ref_buy, a.ref_view)[0]
    req[s] = int(round(U_ref[s] / a.theta))

# ---------- 不確かさ δ ----------
MAJOR = [s for s in SERVICES if U_ref[s] >= a.major_min_m]
delta = {}                  # independent 用: (s, n) -> RMS(meas/pred-1)
for s in SERVICES:
    for n in (1, 2):
        e = [(m - pr) / m for _, _, pr, m in loo[(s, n)]]
        delta[(s, n)] = math.sqrt(sum(x * x for x in e) / len(e))
dcom, dind = {}, {}         # common 用: dcom[n], dind[(s, n)]
for n in (1, 2):
    g = {}
    for s in MAJOR:
        for p, cy, pr, m in loo[(s, n)]:
            g.setdefault((p, cy), []).append(m / pr)
    def med(x):
        x = sorted(x); k = len(x)
        return x[k // 2] if k % 2 else (x[k // 2 - 1] + x[k // 2]) / 2
    g = {k: med(v) for k, v in g.items()}
    dcom[n] = math.sqrt(sum((x - 1) ** 2 for x in g.values()) / len(g))
    for s in SERVICES:
        e = [m / (pr * g[(p, cy)]) - 1 for p, cy, pr, m in loo[(s, n)]]
        dind[(s, n)] = math.sqrt(sum(x * x for x in e) / len(e))

def mult(s, n, kc, ki):
    """サービス s の D にかける倍率 (n≥3 は n=2 の δ を使う)。"""
    k = min(n, 2)
    K = a.delta_k
    if a.delta_mode == 'independent':
        return 1 + ki * K * delta[(s, k)]
    return (1 + kc * K * dcom[k]) * (1 + ki * K * dind[(s, k)])


# 待ち受けポート (km2/normal/*.yaml の containerPort と PORT 環境変数。checkout は 9464 の metrics も listen)
PORTS = {'frontend': {8080}, 'checkoutservice': {5050, 9464}, 'cartservice': {7070},
         'productcatalogservice': {3550}, 'currencyservice': {7000}, 'paymentservice': {50051},
         'shippingservice': {50051}, 'emailservice': {8080}, 'recommendationservice': {8080},
         'adservice': {9555}}

# ---------- HPA シミュレーション ----------
def desired(n, util):
    ratio = util / a.target
    if abs(ratio - 1) <= a.tol + 1e-12:
        d = n
    else:
        d = math.ceil(n * ratio - 1e-9)
    return min(a.nmax, max(a.nmin, d))


def settle(members, n0, b, v, kc, ki):
    """members = [サービス,...] (1つなら分離、2つなら同居)。戻り (台数 or None, 外挿flag, 振動flag)。
    kc = 共通ずれの向き(-1/0/1)、ki = {サービス: 固有ずれの向き}。"""
    n, seen, extrap = n0, [], False
    while True:
        if n in seen:
            cyc = seen[seen.index(n):]
            return (n if len(cyc) == 1 else None), extrap, len(cyc) > 1
        seen.append(n)
        ds = []
        for s in members:
            d, ex = D(s, n, b, v)
            extrap |= ex
            ds.append(desired(n, d * mult(s, n, kc, ki[s]) / (n * req[s])))
        n = max(ds)


def judge(s, t, n0, b, v):
    losses, flags = [], set()
    kcs = (0,) if a.delta_mode == 'independent' else (-1, 0, 1)
    for kc, ks, kt in itertools.product(kcs, (-1, 0, 1), (-1, 0, 1)):
        sc = {s: ks, t: kt}
        ns, e1, o1 = settle([s], n0, b, v, kc, sc)
        nt, e2, o2 = settle([t], n0, b, v, kc, sc)
        nst, e3, o3 = settle([s, t], n0, b, v, kc, sc)
        if e1 or e2 or e3: flags.add('外挿')
        if o1 or o2 or o3: flags.add('振動')
        if None in (ns, nt, nst):
            continue
        losses.append((nst * (req[s] + req[t]) - (ns * req[s] + nt * req[t]), kc, ks, kt, ns, nt, nst))
    center = [x for x in losses if x[1] == 0 and x[2] == 0 and x[3] == 0]
    if not center:
        return None, flags, losses
    return center[0], flags, losses


def category(center, flags, losses):
    if flags or center is None or len(losses) < (9 if a.delta_mode == 'independent' else 27):
        return '不明'
    ls = [x[0] for x in losses]
    if all(l == 0 for l in ls): return '損なし'
    if all(l > 0 for l in ls): return '損あり'
    return '不明'


# ---------- 予測 ----------
pairs = list(itertools.combinations(SERVICES, 2))
preds = []
for s, t in pairs:
    for b in a.grid_buy:
        for v in a.grid_view:
            for n0 in (1, 2):
                c, fl, ls = judge(s, t, n0, b, v)
                cat = category(c, fl, ls)
                lmin = min((x[0] for x in ls), default=float('nan'))
                lmax = max((x[0] for x in ls), default=float('nan'))
                preds.append(dict(
                    pair=f'{ABBR[s]}+{ABBR[t]}', s=s, t=t, buy=b, view=v, start=n0,
                    n_s=c[4] if c else '', n_t=c[5] if c else '', n_st=c[6] if c else '',
                    r_s=req[s], r_t=req[t],
                    u1_s='%.3f' % (D(s, 1, b, v)[0] / req[s]), u1_t='%.3f' % (D(t, 1, b, v)[0] / req[t]),
                    loss_m=('%d' % c[0]) if c else '', loss_min=('%d' % lmin) if ls else '',
                    loss_max=('%d' % lmax) if ls else '', category=cat, flags='+'.join(sorted(fl)),
                    port_conflict='/'.join(map(str, sorted(PORTS[s] & PORTS[t]))) or 'なし'))

# 双安定: 同じ (ペア, 点) で開始台数 1 と 2 の中心値 (n_s, n_t, n_st) が違う = 履歴で結果が変わる (副次評価に回す)
_ctr = {}
for p in preds:
    _ctr.setdefault((p['pair'], p['buy'], p['view']), {})[p['start']] = (p['n_s'], p['n_t'], p['n_st'])
for p in preds:
    c = _ctr[(p['pair'], p['buy'], p['view'])]
    p['bistable'] = 'yes' if c.get(1) != c.get(2) else 'no'

fields = ['pair', 's', 't', 'buy', 'view', 'start', 'n_s', 'n_t', 'n_st', 'r_s', 'r_t', 'u1_s', 'u1_t',
          'loss_m', 'loss_min', 'loss_max', 'category', 'flags', 'port_conflict', 'bistable']
with open(a.out_pred, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(preds)

# 枠 CSV (読む側は deploy, container, request_m だけ使う。残りは参考列)
with open(a.out_req, 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['deploy', 'container', 'request_m', 'U_ref_m', 'theta', 'ref_buy', 'ref_view',
                'c1', 'beta1', 'nu1', 'c2', 'beta2', 'nu2', 'delta1', 'delta2', 'delta_mode', 'dcommon1', 'dcommon2', 'dindiv1', 'dindiv2'])
    for s in SERVICES:
        c1, c2 = coef[(s, 1)], coef[(s, 2)]
        w.writerow([s, container[s], req[s], '%.1f' % U_ref[s], a.theta, a.ref_buy, a.ref_view,
                    '%.2f' % c1[0], '%.4f' % c1[1], '%.4f' % c1[2], '%.2f' % c2[0], '%.4f' % c2[1],
                    '%.4f' % c2[2], '%.4f' % delta[(s, 1)], '%.4f' % delta[(s, 2)], a.delta_mode,
                    '%.4f' % dcom[1], '%.4f' % dcom[2], '%.4f' % dind[(s, 1)], '%.4f' % dind[(s, 2)]])
    w.writerow(['redis-cart', 'redis', a.redis_m] + [''] * 17)

# ---------- 標準出力 ----------
print('入力: %s  (行数 %d)' % (a.input, sum(len(x) for x in rows.values())))
print('θ=%.2f 基準ミックス buy=%g view=%g  格子 buy=%s view=%s' % (a.theta, a.ref_buy, a.ref_view, a.grid_buy, a.grid_view))
print('当てはめ: %s / δ: %s' % ('全10点 (旧)' if a.fit_all_points else 'buy>0 の8点', a.delta_mode))
print('共通倍率 g の median を取る主要サービス (U_ref>=%gm): %s' % (a.major_min_m, ', '.join(MAJOR)))
print('δ_common  n=1: %.1f%%  n=2: %.1f%%' % (dcom[1] * 100, dcom[2] * 100))
print('\n(a) サービス別 (D1 = c + β·buy + ν·view [m], ρ=ν/β, κ=(D2-D1)/D1 at b100v100 の実測平均)')
print('%-22s %7s %7s %7s %6s %7s %8s %8s %8s %8s %7s' % ('service', 'c1', 'β1', 'ν1', 'ρ', 'κ', 'δi1', 'δi2', '(独立δ1', '独立δ2)', 'r_s[m]'))
def mean_at(s, n, pt):
    xs = [u for p, _, _, _, u in rows[(s, n)] if p == pt]
    return sum(xs) / len(xs)
for s in SERVICES:
    c = coef[(s, 1)]
    kap = mean_at(s, 2, 'b100v100') / mean_at(s, 1, 'b100v100') - 1
    print('%-22s %7.1f %7.3f %7.3f %6.2f %6.1f%% %7.1f%% %7.1f%% %7.1f%% %7.1f%% %7d' % (
        s, c[0], c[1], c[2], c[2] / c[1], kap * 100, dind[(s, 1)] * 100, dind[(s, 2)] * 100,
        delta[(s, 1)] * 100, delta[(s, 2)] * 100, req[s]))
print('n=2 係数 (c2, β2, ν2):')
for s in SERVICES:
    c = coef[(s, 2)]
    print('  %-22s %7.1f %7.3f %7.3f   U_ref=%.1fm' % (s, c[0], c[1], c[2], U_ref[s]))
print('\n待ち受けポート:', '; '.join('%s=%s' % (ABBR[s], ','.join(map(str, sorted(PORTS[s])))) for s in SERVICES))

print('\n(b) ペアごとの判定 (なし=損なし あり=損あり ?=不明。[view %s の順] 中心値の n_s,n_t>n_st/損[m])' % ' '.join('%g' % v for v in a.grid_view))
byp = defaultdict(list)
for p in preds:
    byp[p['pair']].append(p)
short = {'損なし': 'なし', '損あり': 'あり', '不明': '?'}
for pr, ps in byp.items():
    print('%s: [ポート衝突: %s]' % (pr, ps[0]['port_conflict']))
    for n0 in (1, 2):
        sel = [x for x in ps if x['start'] == n0]
        print('   s%d=[%s]  中心 %s' % (n0, ','.join(short[x['category']] for x in sel),
              ' '.join('%s,%s>%s/%s' % (x['n_s'], x['n_t'], x['n_st'], x['loss_m']) for x in sel)
              + ('  flags=' + ','.join(sorted({x['flags'] for x in sel if x['flags']})) if any(x['flags'] for x in sel) else '')))

cnt = defaultdict(int)
for p in preds:
    cnt[(p['start'], p['category'])] += 1
print('\n(c) 判定ごとの件数 (組×格子点。全 %d 組 × 格子 %d 点)' % (len(pairs), len(a.grid_buy) * len(a.grid_view)))
for n0 in (1, 2):
    print('  start=%d: ' % n0 + ', '.join('%s %d' % (c, cnt[(n0, c)]) for c in ('損なし', '損あり', '不明')))

print('\n(d) ペアごとのまとめ (格子 × 開始台数 %d 通りの判定)' % (len(a.grid_buy) * len(a.grid_view) * 2))
groups = defaultdict(list)
for pr, ps in byp.items():
    cats = {p['category'] for p in ps}
    if cats == {'損なし'}: g = '全て損なし'
    elif cats == {'損あり'}: g = '全て損あり'
    elif cats == {'損なし', '損あり'}: g = '損なし/損あり が入れ替わる'
    elif len(cats) == 1: g = '全て不明'
    else: g = '不明を含む (' + '/'.join(sorted(cats)) + ')'
    groups[g].append(pr + ('[衝突]' if ps[0]['port_conflict'] != 'なし' else ''))
for g, l in groups.items():
    print('  [%s] %d組: %s' % (g, len(l), ', '.join(l)))
print('\n出力: %s, %s' % (a.out_pred, a.out_req))
