#!/usr/bin/env python3
"""hpa-pair-ss.sh から 1 点ごとに呼ばれ、結果 CSV に 1 点 × 1 コンテナの行を足す (2026-11-10。直接は使わない)。

引数: <結果 CSV> <timeline CSV> cycle arm point buy view
環境変数: SUMMARY (k6 集計 JSON) / K6_START_MS / WARM / MEAS / T_Q / WIN (Prometheus に聞いた区間 = T_Q − WIN 〜 T_Q)
          USAGE / NODEJSON / FREQJSON / TEMPJSON (Prometheus の instant query) / REQ (枠の表 "container=m ...")
台数: timeline の t_rel (k6 の開始時刻 = @@@K6_START@@@ から) が [WARM, WARM+MEAS] の行の current_replicas。
      replicas_mode = 最頻値 (同数なら大きい方。OB の analyze_pdist_k3.py と同じ)、changed = 窓の中で値が変わったか。
      OB の bundle-vs-loss2.sh は t_rel の起点が k6 の Pod が Running になった時刻 (数秒早い) なので、そこだけ違う。
CPU: Prometheus の rate[WIN] を T_Q で (計測窓の両端 10 秒を削った内側)。Pod の合計 [m]。
予約枠: timeline の ns_running_cores (Running の Pod の requests 合計、k6/promq を除く) の窓内平均 [コア]。
"""
import sys, os, csv, json, re, collections

out, tl, cyc, arm, pt, buy, view = sys.argv[1:8]
warm, meas = float(os.environ['WARM']), float(os.environ['MEAS'])
t_q, win = float(os.environ['T_Q']), float(os.environ['WIN'])
k6s = float(os.environ.get('K6_START_MS') or 0) / 1000
try:
    d = json.loads(os.environ.get('SUMMARY') or '{}')
except Exception:
    d = {}


def res(env):
    try:
        return json.loads(os.environ.get(env, '')).get('data', {}).get('result', [])
    except Exception:
        return []


def scalar(env):
    try:
        return float(res(env)[0]['value'][1])
    except Exception:
        return None


def dep_of(pod):
    return re.sub(r'-[a-f0-9]{6,}-\w+$', '', pod)


cpu = collections.defaultdict(float)
for x in res('USAGE'):
    m = x['metric']
    cpu[(dep_of(m.get('pod', '?')), m.get('container', '?'))] += float(x['value'][1]) * 1000
req = dict(kv.split('=') for kv in os.environ.get('REQ', '').split())

# timeline からこの点の窓の行
reps = collections.defaultdict(list); resv = {}; pend = collections.defaultdict(int)
for r in csv.DictReader(open(tl)):
    if (r['cycle'], r['arm'], r.get('point')) != (cyc, arm, pt):
        continue
    t = float(r['t_rel'])
    if warm <= t <= warm + meas:
        if r['current_replicas'] not in ('', 'None'):
            reps[r['deploy']].append((t, int(float(r['current_replicas']))))
        resv[t] = float(r['ns_running_cores'])
        pend[t] = max(pend[t], int(r['pending_pods'] or 0))


def mode(xs):
    c = collections.Counter(xs)
    return max(c, key=lambda k: (c[k], k))


k_from = k6s + warm; k_to = k_from + meas
pt_cols = dict(
    buy_achieved=round(d.get('iter_rate', 0), 3), view_achieved=round(d.get('browse_rate', 0), 3),
    buy_dropped_win=d.get('dropped_win', 'NA'), view_dropped_win=d.get('browse_dropped_win', 'NA'),
    buy_failed_rate=round(d.get('failed_rate', 0), 4),
    view_failed_rate=round((d.get('browse_failed') or 0) / max(float(d.get('browse_reqs') or 1), 1), 4),
    order_failed=d.get('order_failed', 'NA'),
    buy_p50=d.get('p50'), buy_p99=d.get('p99'), view_p50=d.get('browse_p50'), view_p99=d.get('browse_p99'),
    reserved_avg_cores=round(sum(resv.values()) / len(resv), 3) if resv else 'NA',
    pending_max=max(pend.values()) if pend else 'NA', n_samples=len(resv),
    node_cores=round(scalar('NODEJSON'), 3) if scalar('NODEJSON') is not None else 'NA',
    freq_ghz=round(scalar('FREQJSON') / 1e9, 3) if scalar('FREQJSON') else 'NA',
    temp_max_c=scalar('TEMPJSON') if scalar('TEMPJSON') is not None else 'NA',
    k6_start=round(k6s, 3), prom_from=int(t_q - win), prom_to=int(t_q),
    margin_start_s=round(t_q - win - k_from, 3) if k6s else 'NA', margin_end_s=round(k_to - t_q, 3) if k6s else 'NA')
COLS = ['cycle', 'arm', 'point', 'buy_target', 'view_target', 'deploy', 'container', 'request_m',
        'replicas_mode', 'replicas_min', 'replicas_max', 'changed_in_window', 'cpu_mc'] + list(pt_cols)
rows = []
for (dp, c), v in sorted(cpu.items()):
    xs = [n for _, n in sorted(reps.get(dp, []))]
    rows.append([cyc, arm, pt, buy, view, dp, c, req.get(c, ''),
                 mode(xs) if xs else 'NA', min(xs) if xs else 'NA', max(xs) if xs else 'NA',
                 int(len(set(xs)) > 1) if xs else 'NA', round(v, 1)] + list(pt_cols.values()))
new = not os.path.exists(out) or os.path.getsize(out) == 0
with open(out, 'a', newline='') as f:
    w = csv.writer(f)
    if new:
        w.writerow(COLS)
    w.writerows(rows)

# ログ
apps = sorted({dp for (dp, c) in cpu if dp in reps})
print('     台数 (窓の最頻値[最小-最大]): ' + '  '.join(
    '%s=%d[%d-%d]%s' % (dp, mode([n for _, n in reps[dp]]), min(n for _, n in reps[dp]), max(n for _, n in reps[dp]),
                        '*' if len({n for _, n in reps[dp]}) > 1 else '') for dp in apps))
print('     予約枠 %s コア、Pending 最大 %s、達成 購入 %s / 閲覧 %s、取りこぼし %s / %s、失敗率 %s / %s、区間の余裕 %s / %s s、%s GHz %s℃'
      % (pt_cols['reserved_avg_cores'], pt_cols['pending_max'], pt_cols['buy_achieved'], pt_cols['view_achieved'],
         pt_cols['buy_dropped_win'], pt_cols['view_dropped_win'], pt_cols['buy_failed_rate'], pt_cols['view_failed_rate'],
         pt_cols['margin_start_s'], pt_cols['margin_end_s'], pt_cols['freq_ghz'], pt_cols['temp_max_c']))
if not resv:
    print('     !! timeline に窓の中の行が無い')
