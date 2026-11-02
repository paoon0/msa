#!/usr/bin/env python3
"""measure-mix-cpu.sh から呼ばれ、1点ぶんの行を CSV に追記する (直接は使わない)。

環境変数: SUMMARY (k6 集計 JSON) / USAGE, REQJSON, LIMJSON, THRJSON, THRTJSON, NODEJSON, FREQJSON, TEMPJSON (instant query)
          SERJSON (query_range, 10秒刻み)
引数: CSV SERIES cycle point replicas buy view t_beg
同じ Deployment の Pod は合計する (= そのサービス全体の CPU)。k6 の Pod は "k6load" として1行に記録する
(ノード負荷の一部なので捨てない)。
"""
import sys, json, csv, os, re
from collections import defaultdict

out, ser_out, cyc, pt, reps, buy, view, t_beg = sys.argv[1:9]
buy, view, t_beg = int(buy), int(view), float(t_beg)
d = json.loads(os.environ['SUMMARY'])
meas = float(d.get('measure_s') or 1)


def result(env):
    try:
        return json.loads(os.environ.get(env, '')).get('data', {}).get('result', [])
    except Exception:
        return []


def series(env):
    o = {}
    for x in result(env):
        try:
            v = float(x['value'][1])
        except Exception:
            continue
        if v == v:                       # NaN (分母0) は捨てる
            o[(x['metric'].get('pod', '?'), x['metric'].get('container', '?'))] = v
    return o


def scalar(env, nd=3):
    r = result(env)
    try:
        return round(float(r[0]['value'][1]), nd)
    except Exception:
        return 'NA'


def dep_of(pod):
    if pod.startswith('k6load'):
        return 'k6load'
    return re.sub(r'-[a-f0-9]{6,}-\w+$', '', pod)


# k6: buy と view を別々に
b_started = float(d.get('started') or 0)
v_started = float(d.get('browse_started') or 0)
k6 = dict(
    buy_target=buy, view_target=view,
    buy_achieved=round(b_started / meas, 2), view_achieved=round(v_started / meas, 2),
    buy_dropped_win=d.get('dropped_win') if buy > 0 else 0,
    view_dropped_win=d.get('browse_dropped_win') if view > 0 else 0,
    buy_p50=round(d.get('p50') or 0, 1), buy_p99=round(d.get('p99') or 0, 1),
    view_p50=round(d.get('browse_p50') or 0, 1), view_p99=round(d.get('browse_p99') or 0, 1),
    buy_failed_rate=round(d.get('failed_rate') or 0, 4),
    view_failed_rate=round((d.get('browse_failed') or 0) / max(v_started, 1), 4),
)
node = dict(node_cores=scalar('NODEJSON', 2), freq_ghz=(lambda f: round(f / 1e9, 3) if f != 'NA' else 'NA')(scalar('FREQJSON', 0)),
            temp_max_c=scalar('TEMPJSON', 1))

usage, req, lim, thr, thrt = (series(e) for e in ('USAGE', 'REQJSON', 'LIMJSON', 'THRJSON', 'THRTJSON'))
agg = defaultdict(lambda: dict(usage_mc=0.0, req_mc=0.0, lim_mc=0.0, pods=0, thr=[], thrt_mc=0.0))
for k, v in usage.items():
    a = agg[(dep_of(k[0]), k[1])]
    a['usage_mc'] += v * 1000
    a['req_mc'] += req.get(k, 0) * 1000
    a['lim_mc'] += lim.get(k, 0) * 1000
    a['pods'] += 1
    a['thr'].append(thr.get(k, 0) * 100)
    a['thrt_mc'] += thrt.get(k, 0) * 1000

cols = ['cycle', 'point', 'replicas'] + list(k6) + ['deploy', 'container', 'pods', 'usage_mc', 'req_mc', 'lim_mc',
        'throttle_pct', 'throttled_mc'] + list(node)
new = not os.path.exists(out) or os.path.getsize(out) == 0
rows = []
for (dep, cont), a in sorted(agg.items(), key=lambda kv: -kv[1]['usage_mc']):
    rows.append([cyc, pt, reps] + list(k6.values()) + [dep, cont, a['pods'], round(a['usage_mc'], 1), round(a['req_mc'], 1),
                round(a['lim_mc'], 1), round(max(a['thr']) if a['thr'] else 0, 1), round(a['thrt_mc'], 1)] + list(node.values()))
with open(out, 'a', newline='') as f:
    w = csv.writer(f)
    if new:
        w.writerow(cols)
    w.writerows(rows)

# 10秒刻みの系列 (Deployment ごとに Pod を合計)
ser = defaultdict(float)
for x in result('SERJSON'):
    key = (dep_of(x['metric'].get('pod', '?')), x['metric'].get('container', '?'))
    for t, v in x.get('values', []):
        try:
            ser[(key, float(t))] += float(v) * 1000
        except ValueError:
            pass
new = not os.path.exists(ser_out) or os.path.getsize(ser_out) == 0
with open(ser_out, 'a', newline='') as f:
    w = csv.writer(f)
    if new:
        w.writerow(['cycle', 'point', 'replicas', 't_off', 'deploy', 'container', 'usage_mc'])
    for ((dep, cont), t), v in sorted(ser.items()):
        w.writerow([cyc, pt, reps, int(t - t_beg), dep, cont, round(v, 1)])

print("  -> buy %.1f/%d view %.1f/%d 周/秒  取りこぼし(窓) buy=%s view=%s  p50 buy=%.0f view=%.0f ms  "
      "ノード=%s コア  周波数=%s GHz  最高温度=%s℃"
      % (k6['buy_achieved'], buy, k6['view_achieved'], view, k6['buy_dropped_win'], k6['view_dropped_win'],
         k6['buy_p50'], k6['view_p50'], node['node_cores'], node['freq_ghz'], node['temp_max_c']))
print("     %-24s %-14s %4s %8s %7s %7s" % ("deploy", "container", "Pod", "使用m", "上限m", "絞り%"))
for r in rows[:12]:
    print("     %-24s %-14s %4s %8.1f %7.0f %7.1f" % (r[cols.index('deploy')], r[cols.index('container')], r[cols.index('pods')],
          r[cols.index('usage_mc')], r[cols.index('lim_mc')], r[cols.index('throttle_pct')]))
hot = [r for r in rows if r[cols.index('throttle_pct')] > 5.0]
if hot:
    print("     !! 絞り 5% 超 (解析で捨てる): " + ", ".join("%s/%s=%.0f%%" % (r[cols.index('deploy')], r[cols.index('container')],
          r[cols.index('throttle_pct')]) for r in hot))
