#!/usr/bin/env python3
"""計測窓のあいだに「確保していた」CPU量を、時間積分で出す。

なぜ必要か:
  予約枠を計測窓の終わりの1点だけで取ると、窓の途中でPodが増減した分が落ちる。
  実際 2026-09-02 の実験で、瞬間値 8.60コアに対し窓の平均が 9.41コアだった測定があった
  (途中まで3台動いていて、最後に2台へ減った)。約0.8コアの過小評価。

出すもの (空白区切り1行):
  reserved_core_sec  … Running の Pod が確保していた量の時間積分 [コア秒]
  pending_core_sec   … Pending の Pod の同上 [コア秒]
  reserved_avg       … 上を窓長で割った平均 [コア]
  n_samples          … 使ったサンプル数

使うと何が言えるか:
  「使ったCPU秒」(node_cpu_sec) と同じ単位になるので、そのまま割れば
  「確保したうちどれだけ実際に使ったか」が出る。

引数: TL WARM MEAS CYC ARM RATE LX BRW
"""
import csv, sys, collections

tl, warm, meas, cyc, arm, rate, lx, brw = sys.argv[1:9]
warm, meas = float(warm), float(meas)
lo, hi = warm, warm + meas

try:
    rows = list(csv.DictReader(open(tl)))
except Exception:
    print("0 0 0 0"); raise SystemExit

# 同じ条件の行だけを拾う。t_rel が戻る箇所で測定が変わるので、最後の測定ぶんだけを使う。
sel = [r for r in rows
       if r.get('cycle') == cyc and r.get('arm') == arm and r.get('target_rate') == rate
       and r.get('limit_x', '0') == lx and r.get('browse_rate', '0') == brw]
blocks, cur, prev = [], [], None
for r in sel:
    t = float(r['t_rel'])
    if prev is not None and t < prev:
        blocks.append(cur); cur = []
    cur.append(r); prev = t
if cur: blocks.append(cur)
if not blocks:
    print("0 0 0 0"); raise SystemExit
b = blocks[-1]

# 同じ時刻の行は deploy/container ぶん重複するので、時刻ごとに1つだけ取る
per_t = {}
for r in b:
    t = float(r['t_rel'])
    if not (lo <= t <= hi): continue
    if t in per_t: continue
    try:
        per_t[t] = (float(r['ns_running_cores']), float(r['ns_pending_cores']))
    except (ValueError, TypeError, KeyError):
        pass
if not per_t:
    print("0 0 0 0"); raise SystemExit

run = [v[0] for v in per_t.values()]
pend = [v[1] for v in per_t.values()]
avg_r = sum(run) / len(run)
avg_p = sum(pend) / len(pend)
print("%.1f %.1f %.3f %d" % (avg_r * meas, avg_p * meas, avg_r, len(per_t)))
