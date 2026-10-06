#!/usr/bin/env python3
"""枠(requests)適正化の第2版 — 手順 STEP 3: クラス別の係数を推定し、枠を計算する。

モデル(1台あたり):
    CPU_s = c0_s + Σ_j a_sj × x_j
      c0_s  = アイドル分(負荷ゼロでも Pod 1台ごとにかかる CPU)[m]
      a_sj  = クラス j のリクエスト 1周/秒 あたりの CPU [m/(周/秒)]
      x_j   = その Pod 1台が担当するクラス j の負荷 [周/秒]
枠:
    r_s = U_ref,s / θ     U_ref = 基準ミックス (k_j) を1台で担当したときの CPU、θ = HPA 目標(0.70)

第1版(summer2026/rightsize.py)からの変更点 — 手順書 km2/approach/rightsizing-procedure.md:
  1. クラス別の傾き a_sj を出す(第1版は buy だけ)。
  2. U_ref は「設計点の周辺だけ」で当てはめた直線の、設計点での値を使う
     (第1版は 10〜150 周/s 全体の直線 → カーブが曲がっている分だけ設計点で外れた)。
  3. c0 は台数を変えた差 U(2台) − U(1台) から出す(データがあれば)。無ければ切片で代用し「未分離」と表示。
  4. 設計点での推定の不確かさ(標準誤差 %)を出す。HPA の許容幅 ±10% に対して十分小さいかを見る。

入力: measure-class-cpu.sh の CSV(--src、複数可)。第1版の CSV は --old-format で読める(class=buy, 1台扱い)。
出力: --out の CSV。先頭3列 (deploy,container,request_m) は summer2026/apply_rightsize.py がそのまま読める。
      → bundle-vs-loss2.sh に RSTABLE=<このCSV> RIGHTSIZE=1 で渡せば、STEP 4 (検証) がそのまま回る。

使い方:
  python3 rightsize2.py --src results-class-cpu.csv --ref buy=100
  python3 rightsize2.py --src ../perservice-cpu/results-perservice-cpu.csv --old-format   # 第1版データで比較
"""
import csv, argparse, math
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('--src', nargs='+', default=['km2/experiments/rightsizing/results-class-cpu.csv'])
ap.add_argument('--old-format', action='store_true', help='第1版 perservice-cpu の CSV を読む')
ap.add_argument('--out', default='km2/experiments/rightsizing/rightsize2-requests.csv')
ap.add_argument('--ref', default='buy=100', help='基準ミックス: 1台が担当する負荷。例 "buy=100" "buy=100,view=50"')
ap.add_argument('--target', type=float, default=0.70, help='HPA 目標利用率 θ')
ap.add_argument('--window', type=float, default=0.4, help='設計点の周辺とみなす幅(±割合)。0.4 なら k の 0.6〜1.4 倍')
ap.add_argument('--throttle-max', type=float, default=5.0, help='この%%を超えて絞られた点は捨てる')
ap.add_argument('--achieve-min', type=float, default=0.97, help='達成率がこれ未満の点(取りこぼし)は捨てる')
ap.add_argument('--min-req', type=float, default=50.0, help='枠の下限 [m]')
a = ap.parse_args()

ref = {}
for kv in a.ref.split(','):
    k, v = kv.split('=')
    ref[k.strip()] = float(v)
main = max(ref, key=ref.get)               # 基準ミックスで一番負荷の大きいクラス

# ---- 読み込み: pts[(deploy,container)][(class, replicas)] = [(cycle, x, cpu_mc)] ----
pts = defaultdict(lambda: defaultdict(list))
cur_req = {}
dropped_pts = 0
for src in a.src:
    for r in csv.DictReader(open(src)):
        try:
            if a.old_format:
                key = (r['pod'], r['container']); cls, reps = 'buy', 1
                x = float(r['iter_rate']); tgt = float(r['target_rate'])
            else:
                key = (r['deploy'], r['container']); cls, reps = r['class'], int(r['replicas'])
                x = float(r['achieved_rate']); tgt = float(r['target_rate'])
            use = float(r['usage_mc']); thr = float(r['throttle_pct'])
            cur_req[key] = float(r['req_mc']) / reps
        except (ValueError, KeyError):
            continue
        if thr > a.throttle_max or (tgt > 0 and x < a.achieve_min * tgt):
            dropped_pts += 1
            continue
        pts[key][(cls, reps)].append((r['cycle'], x, use))


def ols(P):
    """y = s·x + b の最小二乗。戻り値 (s, b, 設計点 k での標準誤差を返す関数)。"""
    n = len(P)
    xs = [p[1] for p in P]; ys = [p[2] for p in P]
    mx = sum(xs) / n; my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if n < 2 or sxx == 0:
        return None
    s = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - s * mx
    res = [y - (s * x + b) for x, y in zip(xs, ys)]
    sig = math.sqrt(sum(e * e for e in res) / (n - 2)) if n > 2 else float('nan')
    se_at = lambda k: sig * math.sqrt(1.0 / n + (k - mx) ** 2 / sxx)
    return s, b, se_at


rows = []
for key in sorted(pts, key=lambda k: -cur_req.get(k, 0)):
    by = pts[key]
    one = {c: v for (c, n), v in by.items() if n == 1}
    if main not in one or len({p[1] for p in one[main]}) < 2:
        continue
    slope_all, slope_loc, note = {}, {}, []
    for c, P in one.items():
        f = ols(P)
        if f: slope_all[c] = f
    # 設計点の周辺だけで当てはめ(点が足りなければ全範囲)
    k = ref[main]
    near = [p for p in one[main] if abs(p[1] - k) <= a.window * k]
    f_loc = ols(near) if len({p[1] for p in near}) >= 3 else None
    if f_loc is None:
        f_loc = slope_all[main]; note.append('周辺の点不足→全範囲')
    s_m, b_m, se_m = f_loc
    U_ref = s_m * k + b_m
    se = se_m(k) if not math.isnan(se_m(k)) else float('nan')
    # 他のクラスの寄与(傾き × 基準負荷)。切片は main 側に含まれているので足さない
    for c, kc in ref.items():
        if c == main or kc == 0:
            continue
        if c not in slope_all:
            note.append('%s の測定なし' % c); continue
        U_ref += slope_all[c][0] * kc
    # アイドル分 c0: 台数を変えた差 (同じサイクル・同じ負荷の対)
    c0, c0m = None, ''
    for (c, n), P in by.items():
        if n < 2 or (c, 1) not in by:
            continue
        diffs = []
        for cyc, x, u in P:
            pair = [u1 for cy1, x1, u1 in by[(c, 1)] if cy1 == cyc and abs(x1 - x) <= 0.05 * x]
            if pair:
                diffs.append((u - pair[-1]) / (n - 1))
        if diffs:
            c0 = sum(diffs) / len(diffs); c0m = '台数差(n=%d)' % len(diffs)
    if c0 is None:
        c0 = slope_all[main][1]; c0m = '切片(未分離)'
    req = max(U_ref / a.target, a.min_req)
    row = dict(deploy=key[0], container=key[1], request_m=round(req), U_ref_m=round(U_ref, 1),
               se_pct=round(se / U_ref * 100, 1) if U_ref > 0 and se == se else '',
               c0_m=round(c0, 1), c0_method=c0m, old_request_m=round(cur_req.get(key, 0)),
               n_points=sum(len(v) for v in one.values()), note=';'.join(note))
    for c in sorted(slope_all):
        row['a_%s' % c] = round(slope_all[c][0], 3)
    row['a_%s_local' % main] = round(s_m, 3)
    rows.append(row)

classes = sorted({k[2:] for r in rows for k in r if k.startswith('a_') and not k.endswith('_local')})
cols = ['deploy', 'container', 'request_m', 'U_ref_m', 'se_pct', 'c0_m', 'c0_method'] + \
       ['a_%s' % c for c in classes] + ['a_%s_local' % main, 'old_request_m', 'n_points', 'note']
with open(a.out, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in rows:
        w.writerow(r)

print("基準ミックス(1台あたり): %s   θ=%.2f   周辺幅 ±%.0f%%   除外した点 %d"
      % (a.ref, a.target, a.window * 100, dropped_pts))
print("%-22s %8s %8s %6s %7s %-14s %s" % ("deploy", "枠m", "U_ref", "誤差%", "c0", "c0の出し方",
                                          "  ".join("a_%s" % c for c in classes)))
for r in rows:
    print("%-22s %8d %8.0f %6s %7.1f %-14s %s %s" % (
        r['deploy'], r['request_m'], r['U_ref_m'], r['se_pct'], r['c0_m'], r['c0_method'],
        "  ".join("%6.3f" % r.get('a_%s' % c, float('nan')) for c in classes), r['note']))
print("\n誤差% = 設計点での推定値の標準誤差 ÷ U_ref。HPA の許容幅は ±10% なので、2倍しても 5% 未満が目安。")
print("書き出し: %s  → 次は STEP 4(検証): bundle-vs-loss2.sh に RIGHTSIZE=1 RSTABLE=<このCSV> RS_SERVICES=\"<全サービス名>\"(空にすると既定の4サービスに戻るので列挙する)" % a.out)
