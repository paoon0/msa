#!/usr/bin/env python3
"""同じサービスの複数 Pod に、負荷が均等に分かれているかを調べる (gRPC 接続の偏りの確認)。

背景:
  frontend / checkout の gRPC クライアントは負荷分散の設定なし (src/frontend/main.go:228,
  src/checkoutservice/main.go:234) なので、既定の pick_first = 宛先ごとに接続を1本だけ張り、
  ClusterIP の Service 越しだと、その1本が振り分けられた Pod に全呼び出しが行く。
  呼び出し元の Pod 数が少ないと、呼ばれる側を増やしても新しい Pod に仕事が来ない可能性がある。

やること:
  bundle-vs-loss2.sh のログから各測定点の計測窓 (開始時刻 + WARM 〜 + MEAS) を読み取り、
  Prometheus (保持 10 日) に Pod ごとの CPU 使用量を問い合わせて、サービスごとに
    偏り = 最も忙しい Pod の CPU ÷ Pod 平均   (均等なら 1.0、1台に全部なら Pod 数)
  を出す。Prometheus には API サーバ経由 (kubectl get --raw) で問い合わせるので、クラスタに何も作らない。

使い方:
  python3 pod_balance.py --log ../summer2026/lbcheck.log
"""
import argparse, json, re, subprocess, datetime, urllib.parse
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument('--log', required=True)
ap.add_argument('--ns', default='exp')
ap.add_argument('--margin', type=int, default=10, help='窓の両端を何秒ずつ削るか(時刻の記録ずれ対策)')
a = ap.parse_args()

PROXY = '/api/v1/namespaces/monitoring/services/prometheus-grafana-kube-pr-prometheus:9090/proxy/api/v1/query'


def prom(q, t):
    url = PROXY + '?' + urllib.parse.urlencode({'query': q, 'time': t})
    out = subprocess.run(['kubectl', 'get', '--raw', url], capture_output=True, text=True).stdout
    return json.loads(out)['data']['result'] if out else []


text = open(a.log).read()
m = re.search(r'warm=(\d+)s meas=(\d+)s', text)
warm, meas = int(m.group(1)), int(m.group(2))
pts = re.findall(r'==== \[cyc(\d+)\]\[([^\]]+)\] (.*?) (\d{4}-\d\d-\d\dT[\d:]+[+-]\d\d:\d\d) ====', text)
print("計測窓: 各点の開始 + %ds から %ds (両端 %ds 削る)。偏り = 最大 Pod ÷ Pod 平均 (均等=1.0)" % (warm, meas, a.margin))

for cyc, arm, label, ts in pts:
    t0 = datetime.datetime.fromisoformat(ts).timestamp() + warm + a.margin
    win = meas - 2 * a.margin
    t_end = t0 + win
    q = ('sum by(pod,container)(rate(container_cpu_usage_seconds_total{namespace="%s",container!="",'
         'container!="POD",pod!~"k6load.*|promq.*"}[%ds]))' % (a.ns, win))
    by = defaultdict(list)
    for x in prom(q, t_end):
        pod = x['metric'].get('pod', '?')
        dep = re.sub(r'-[a-f0-9]{6,}-\w+$', '', pod)
        by[(dep, x['metric'].get('container', '?'))].append(float(x['value'][1]) * 1000)
    print("\n[cyc%s][%s] %s" % (cyc, arm, label))
    if not by:
        print("  (データなし: Prometheus の保持期間 10 日を過ぎたか、時刻の読み取り失敗)")
        continue
    for (dep, cont), v in sorted(by.items(), key=lambda kv: -sum(kv[1])):
        if len(v) < 2:
            continue
        mean = sum(v) / len(v)
        print("  %-24s %-12s Pod数=%d 合計=%6.0fm 偏り=%.2f  各Pod(m)=%s" % (
            dep, cont, len(v), sum(v), max(v) / mean if mean > 0 else float('nan'),
            ' '.join('%.0f' % x for x in sorted(v, reverse=True))))
