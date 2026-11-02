#!/usr/bin/env python3
"""measure-mix-cpu.sh から呼ばれ、1点ぶんの行を CSV に追記する (直接は使わない)。

環境変数: SUMMARY (k6 集計 JSON) / USAGE, REQJSON, LIMJSON, THRJSON, THRTJSON, NODEJSON, FREQJSON, TEMPJSON (instant query)
          SERJSON (query_range, 10秒刻み)
          T_RUN, T_END, T_Q, WIN (問い合わせた区間。無ければ時刻の表は書かない)
引数: CSV SERIES cycle point replicas buy view t_beg
時刻の表 (2026-11-02 追加): <CSV 名>-times.csv に 1 点 1 行。スクリプトが Prometheus に問い合わせた区間と、
k6 自身が数えた計測窓 (k6 が集計に k6_start_ms を出すときだけ) を unix 秒で並べ、ずれ (秒) を出す。
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

# 時刻の表 (unix 秒)。prom_* = スクリプトが問い合わせた区間、k6_meas_* = k6 が実際に数えた計測窓。
# 余裕 (margin) が両方とも正なら、Prometheus の区間は k6 の計測窓の内側に収まっている
if os.environ.get('T_Q'):
    t_run, t_end, t_q, win = (float(os.environ[k]) for k in ('T_RUN', 'T_END', 'T_Q', 'WIN'))
    # k6 の開始時刻は 2 経路で取る: 集計 JSON の k6_start_ms (handleSummary に setup_data が渡るとき) と、
    # setup() がログに出した @@@K6_START@@@ 行 (シェル側が読んで K6_START_MS で渡す)。どちらで取れたかを残す
    k6s, src = d.get('k6_start_ms'), 'summary'
    if not k6s and os.environ.get('K6_START_MS'):
        k6s, src = float(os.environ['K6_START_MS']), 'log'
    if not k6s:
        src = 'NA'
    if k6s:
        k_from = k6s / 1000 + float(d.get('k6_warmup_s') or 0)
        k_to = k_from + meas
        times = [round(k6s / 1000, 3), round(k_from, 3), round(k_to, 3), round(d['k6_summary_ms'] / 1000, 3) if d.get('k6_summary_ms') else 'NA',
                 round(k_from - t_beg, 3), round((t_q - win) - k_from, 3), round(k_to - t_q, 3)]
    else:
        times = ['NA'] * 7
    t_out = re.sub(r'\.csv$', '', out) + '-times.csv'
    new = not os.path.exists(t_out) or os.path.getsize(t_out) == 0
    with open(t_out, 'a', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['cycle', 'point', 'replicas', 't_run', 't_beg', 't_end', 'prom_from', 'prom_to',
                        'k6_start', 'k6_meas_from', 'k6_meas_to', 'k6_summary_at',
                        'k6_late_s', 'margin_start_s', 'margin_end_s', 'k6_start_src'])
        w.writerow([cyc, pt, reps, int(t_run), int(t_beg), int(t_end), int(t_q - win), int(t_q)] + times + [src])
    if k6s:
        print("     時刻 (k6 の開始=%s から): k6 の窓は t_beg より %+.1f s、Prometheus の区間の余裕 始め %.1f s / 終わり %.1f s%s"
              % (src, times[4], times[5], times[6], "  !! 区間が k6 の窓からはみ出した" if min(times[5], times[6]) < 0 else ""))
    else:
        print("     !! 時刻: k6 の開始時刻が集計にもログにも無い (checkout.js が古い可能性)。区間のずれは確かめられない")
