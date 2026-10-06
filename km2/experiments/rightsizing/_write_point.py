#!/usr/bin/env python3
"""measure-class-cpu.sh から呼ばれ、1測定点ぶんの行を CSV に追記する(直接は使わない)。

環境変数: SUMMARY(k6 集計 JSON) / USAGE, REQJSON, THRJSON(Prometheus 応答) / SKEY(開始周数のキー)
引数: CSV cycle class replicas target_rate node_cores
複数台のときは同じ deploy の Pod を合計する(HPA が見る「需要 = 利用率 × 台数」と同じ単位にするため)。
"""
import sys, json, csv, os, re
from collections import defaultdict

out, cyc, cls, reps, target, node = sys.argv[1:7]
d = json.loads(os.environ['SUMMARY'])
meas = float(d.get('measure_s') or 1)
started = float(d.get(os.environ.get('SKEY', 'started')) or 0)
achieved = started / meas
dropped = d.get('browse_dropped_win') if cls == 'view' else d.get('dropped_win')
fail = d.get('browse_failed', 0) / max(started, 1) if cls == 'view' else (d.get('failed_rate') or 0)
p99 = d.get('browse_p99') if cls == 'view' else d.get('p99')


def series(env):
    try:
        r = json.loads(os.environ[env]).get('data', {}).get('result', [])
    except Exception:
        r = []
    o = {}
    for x in r:
        try:
            v = float(x['value'][1])
        except Exception:
            continue
        if v != v:                       # NaN(分母0)は捨てる
            continue
        o[(x['metric'].get('pod', '?'), x['metric'].get('container', '?'))] = v
    return o


usage, req, thr = series('USAGE'), series('REQJSON'), series('THRJSON')
# Pod 名の末尾(ReplicaSet ハッシュ-Pod ID)を落として deploy 名で合計
agg = defaultdict(lambda: [0.0, 0.0, [], 0])   # usage_mc, req_mc, throttle%, pods
for k, v in usage.items():
    dep = re.sub(r'-[a-f0-9]{6,}-\w+$', '', k[0])
    a = agg[(dep, k[1])]
    a[0] += v * 1000.0
    a[1] += req.get(k, 0.0) * 1000.0
    a[2].append(thr.get(k, 0.0) * 100.0)
    a[3] += 1

rows = []
for (dep, cont), (mc, rq, tps, npod) in sorted(agg.items(), key=lambda kv: -kv[1][0]):
    util = mc / rq * 100.0 if rq > 0 else 0.0     # 合計使用 ÷ 合計枠 = Pod 平均の利用率
    rows.append([cyc, cls, reps, target, round(achieved, 2), dropped, round(fail, 4),
                 round(p99 or 0, 1), dep, cont, round(mc, 1), round(rq, 1), round(util, 1),
                 round(max(tps), 1), node])
with open(out, 'a', newline='') as f:
    csv.writer(f).writerows(rows)

print("  -> 達成 %.1f/%s周/秒 取りこぼし(窓)=%s p99=%.0f 失敗=%.3f ノード=%s コア"
      % (achieved, target, dropped, p99 or 0, fail, node))
print("     %-24s %-12s %8s %7s %8s %7s" % ("deploy", "container", "使用m", "枠m", "利用率%", "絞り%"))
for r in rows[:12]:
    print("     %-24s %-12s %8.1f %7.0f %8.1f %7.1f" % (r[8], r[9], r[10], r[11], r[12], r[13]))
hot = [r for r in rows if r[13] > 1.0]
if hot:
    print("     !! スロットリング検出(この点はカーブが寝ている可能性): "
          + ", ".join("%s/%s=%.0f%%" % (r[8], r[9], r[13]) for r in hot))
