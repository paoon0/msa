#!/usr/bin/env python3
"""bundle-vs-loss2.sh から 1 点ごとに呼ばれ、時刻の表と CPU カウンタの生の記録を書く (2026-11-04 追加。直接は使わない)。
rightsizing/_write_mixpoint.py の時刻の表・生の記録と同じ考え方。results の CSV には触らない。

引数: CSV cycle arm target_rate browse_rate point start_replicas  (point / start_replicas は RESET_EACH_POINT=1 のときだけ値が入る)
環境変数: SUMMARY (k6 集計 JSON。回収失敗なら空) / K6_START_MS (k6 のログの @@@K6_START@@@ 行)
          FREQJSON, TEMPJSON (instant query) / SERJSON (区間の CPU カウンタの生の記録 = range vector)
          T_RUN (k6 の Pod が Running になったのをスクリプトが見た時刻) / T_Q (Prometheus に聞いた区間の終わり) / WIN (区間の長さ) / WARM / MEAS

<CSV 名>-times.csv : 1 点 1 行。
  列の名前と意味は rightsizing/_write_mixpoint.py の -times.csv と同じ (先頭の点の識別列と、末尾の周波数・温度だけ違う)。
  t_beg / t_end         = スクリプトが考える計測窓 (t_run + WARM から MEAS 秒)。台数の時系列 (timeline) の t_rel もこの t_run が起点
  prom_from / prom_to   = Prometheus に聞いた区間 (窓の両端を 10 秒ずつ削った内側、2026-11-04 から)。
                          node_cpu_sec / softirq_cpu_sec / k6_cpu_sec はこの区間で使った CPU 秒
  k6_meas_from / to     = k6 が実際に数えた計測窓 (k6_start + WARM から MEAS 秒)
  margin_start_s / margin_end_s = Prometheus の区間が k6 の窓の内側に収まっている余裕 (負なら外にはみ出している)
  freq_ghz / temp_max_c = 問い合わせた区間のノードの平均周波数・最高温度
<CSV 名>-raw.csv   : 1 行 = 1 点 × 1 Pod × 1 記録 (CPU 時間の累計、そのまま)。t_off は t_beg からの秒
"""
import sys, json, csv, os, re

out, cyc, arm, rate, brw, pt, n0 = (sys.argv[1:8] + [''] * 7)[:7]
try:
    d = json.loads(os.environ.get('SUMMARY') or '{}')
except Exception:
    d = {}
t_run, t_q, win, warm, meas = (float(os.environ[k]) for k in ('T_RUN', 'T_Q', 'WIN', 'WARM', 'MEAS'))
t_beg, t_end = t_run + warm, t_run + warm + meas
prom_from, prom_to = t_q - win, t_q
key = [cyc, arm, pt, n0, rate, brw]
KEY_COLS = ['cycle', 'arm', 'point', 'start_replicas', 'target_rate', 'browse_rate']


def result(env):
    try:
        return json.loads(os.environ.get(env, '')).get('data', {}).get('result', [])
    except Exception:
        return []


def scalar(env, nd):
    try:
        return round(float(result(env)[0]['value'][1]), nd)
    except Exception:
        return 'NA'


def dep_of(pod):
    if pod.startswith('k6load'):
        return 'k6load'
    return re.sub(r'-[a-f0-9]{6,}-\w+$', '', pod)


def open_checked(path, hdr):
    """形式の違う既存ファイルには追記しない。戻り値 (ファイル, ヘッダを書くか)"""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path) as f:
            head = f.readline().strip().split(',')
        if head != hdr:
            print("     !! %s は形式が違うので書かない (CSV の名前を変えて回すこと)" % os.path.basename(path))
            return None, False
        return open(path, 'a', newline=''), False
    return open(path, 'a', newline=''), True


def write(path, hdr, rows):
    f, new = open_checked(path, hdr)
    if f is None:
        return
    with f:
        w = csv.writer(f)
        if new:
            w.writerow(hdr)
        w.writerows(rows)


base = re.sub(r'\.csv$', '', out)

# --- 時刻の表 ---
k6s, src = d.get('k6_start_ms'), 'summary'
if not k6s and os.environ.get('K6_START_MS'):
    k6s, src = float(os.environ['K6_START_MS']), 'log'
if not k6s:
    src = 'NA'
freq = scalar('FREQJSON', 0)
freq = round(freq / 1e9, 3) if freq != 'NA' else 'NA'
temp = scalar('TEMPJSON', 1)
if k6s:
    k_from = k6s / 1000 + float(d.get('k6_warmup_s') or warm)
    k_to = k_from + float(d.get('measure_s') or meas)
    k6 = [round(k6s / 1000, 3), round(k_from, 3), round(k_to, 3),
          round(d['k6_summary_ms'] / 1000, 3) if d.get('k6_summary_ms') else 'NA',
          round(k_from - t_beg, 3), round(prom_from - k_from, 3), round(k_to - prom_to, 3)]
else:
    k6 = ['NA'] * 7
T_COLS = KEY_COLS + ['t_run', 't_beg', 't_end', 'prom_from', 'prom_to',
                     'k6_start', 'k6_meas_from', 'k6_meas_to', 'k6_summary_at', 'k6_late_s', 'margin_start_s', 'margin_end_s',
                     'k6_start_src', 'freq_ghz', 'temp_max_c']
write(base + '-times.csv', T_COLS,
      [key + [int(t_run), int(t_beg), int(t_end), int(prom_from), int(prom_to)] + k6 + [src, freq, temp]])

# --- CPU カウンタの生の記録 ---
R_COLS = KEY_COLS + ['deploy', 'container', 'pod', 't_unix', 't_off', 'cpu_seconds_total']
rows, n_ser, n_short = [], 0, 0
for x in result('SERJSON'):
    pod, cont = x['metric'].get('pod', '?'), x['metric'].get('container', '?')
    pts = []
    for t, v in x.get('values', []):
        try:
            pts.append((float(t), float(v)))
        except ValueError:
            pass
    pts.sort()
    n_ser += 1
    if len(pts) < 2:
        n_short += 1
    for t, v in pts:
        rows.append(key + [dep_of(pod), cont, pod, round(t, 3), round(t - t_beg, 3), v])
write(base + '-raw.csv', R_COLS, rows)

# --- ログ ---
if k6s:
    print("     時刻 (k6 の開始=%s から): k6 の窓は t_beg より %+.1f s、Prometheus の区間の余裕 始め %.1f s / 終わり %.1f s%s"
          % (src, k6[4], k6[5], k6[6], "  !! 区間が k6 の窓からはみ出した" if min(k6[5], k6[6]) < 0 else ""))
else:
    print("     !! 時刻: k6 の開始時刻が集計にもログにも無い。区間のずれは確かめられない")
print("     ノード: 周波数=%s GHz  最高温度=%s℃" % (freq, temp))
if n_ser == 0:
    print("     !! 生の記録が 1 つも取れなかった")
elif n_short:
    print("     !! 生の記録: 記録が 2 つ未満の Pod %d 個 (全 %d 系列)" % (n_short, n_ser))
