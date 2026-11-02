#!/usr/bin/env python3
"""開始台数の検査 (start_ok) を時系列 CSV から出す。

目的: RESET_EACH_POINT=1 の測定で「負荷を掛け始めた直後 (t_rel ≤ 15 秒) の全 Deployment の台数が、
  狙った開始台数 n0 と一致していたか」を確かめる。1 = 一致 / 0 = 不一致またはデータ不足。
  (HPA の安定化窓 = 増30秒/減60秒 より前なので、n0 と違えば Pod が落ちた・scale が戻った等の異常。)

入力: timeline CSV (sample_hpa.py の出力。RESET_EACH_POINT=1 のときは末尾に point,start_replicas 列がある)。
  対象 = 引数で指定した (cycle, arm, target_rate, limit_x, browse_rate, point, start_replicas) の**最後の測定**
  (t_rel が戻る位置で測定が分かれるので、最後のブロックだけを使う)。
判定:
  * redis-cart は常に 1 台固定なので対象外。
  * t_rel ≤ 15 の行のうち current_replicas (空なら ready_replicas) が空でないものが、すべて n0 と等しい。
  * 対象の全 Deployment (redis-cart 以外) について、t_rel ≤ 15 で current_replicas が空でない行が1つ以上ある。
    (HPA を作った直後は status.currentReplicas が空のことがあるので、空は「判断材料なし」として飛ばす。
     全部空のままの Deployment が1つでもあれば 0 = 検査できなかったとして扱う。)
使い方 (bundle-vs-loss2.sh から呼ぶ): python3 start_ok.py TL CYC ARM RATE LX BRW POINT N0
"""
import csv, sys

tl, cyc, arm, rate, lx, brw, pt, n0 = sys.argv[1:9]
try:
    rows = list(csv.DictReader(open(tl)))
except Exception:
    print(0); raise SystemExit
sel = [r for r in rows
       if r.get('cycle') == cyc and r.get('arm') == arm and r.get('target_rate') == rate
       and r.get('limit_x', '0') == lx and r.get('browse_rate', '0') == brw
       and r.get('point') == pt and r.get('start_replicas') == n0]
blocks, cur, prev = [], [], None
for r in sel:
    t = float(r['t_rel'])
    if prev is not None and t < prev:
        blocks.append(cur); cur = []
    cur.append(r); prev = t
if cur: blocks.append(cur)
if not blocks:
    print(0); raise SystemExit
seen, ok = {}, True
for r in blocks[-1]:
    if r['deploy'] == 'redis-cart' or float(r['t_rel']) > 15:
        continue
    seen.setdefault(r['deploy'], 0)
    # 2026-10-08 スモークで、HPA 作成直後 (t_rel=1) は current_replicas が空で ready_replicas だけ入っていた。
    # 空のときは ready_replicas (Ready な Pod 数) で代用する (どちらも空なら判断材料なし)。
    v = r['current_replicas'] or r.get('ready_replicas', '')
    if v == '':
        continue
    seen[r['deploy']] += 1
    if v != n0:
        ok = False
print(1 if (ok and seen and all(v > 0 for v in seen.values())) else 0)
