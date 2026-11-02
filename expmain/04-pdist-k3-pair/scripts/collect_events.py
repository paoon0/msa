#!/usr/bin/env python3
"""`kubectl get events --field-selector reason=SuccessfulRescale -o json` を受け、
台数変更イベントを CSV で出す(cycle,arm,target_rate,time,object,message)。

message には HPA の判断理由がそのまま入る
(例: "New size: 3; reason: cpu resource utilization (percentage of request) above target")。
環境変数 CYC/ARM/RATE/SINCE。SINCE(RFC3339)以降のイベントだけを出す。
環境変数 TL_POINT / TL_N0 が設定されているときだけ、行の末尾に point,start_replicas の2列を足す
(2026-10-08 追加。RESET_EACH_POINT=1 用。既定では出力は従来と同じ)。
"""
import sys, json, os, csv

try:
    d = json.load(sys.stdin)
except Exception as e:
    print("collect_events: JSON読み取り失敗: %s" % e, file=sys.stderr)
    sys.exit(0)

cyc, arm, rate = os.environ.get('CYC', '1'), os.environ.get('ARM', '?'), os.environ.get('RATE', '?')
since = os.environ.get('SINCE', '')
extra = [os.environ['TL_POINT'], os.environ.get('TL_N0', '')] if 'TL_POINT' in os.environ else []

rows = []
for e in d.get('items', []):
    t = e.get('lastTimestamp') or e.get('eventTime') or ''
    if since and t and t < since:
        continue
    rows.append([cyc, arm, rate, t,
                 e.get('involvedObject', {}).get('name', ''),
                 (e.get('message') or '').replace(',', ';')] + extra)
rows.sort(key=lambda r: r[3])
w = csv.writer(sys.stdout)
for r in rows:
    w.writerow(r)
