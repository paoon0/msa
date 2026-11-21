#!/usr/bin/env python3
"""`kubectl get events --field-selector reason=SuccessfulRescale -o json` を受け、
台数変更イベントを CSV で出す(cycle,arm,target_rate,time,object,message)。

message には HPA の判断理由がそのまま入る
(例: "New size: 3; reason: cpu resource utilization (percentage of request) above target")。
環境変数 CYC/ARM/RATE/SINCE。SINCE(RFC3339)以降のイベントだけを出す。
環境変数 TL_POINT / TL_N0 が設定されているときだけ、行の末尾に point,start_replicas の2列を足す
(2026-10-08 追加。RESET_EACH_POINT=1 用。既定では出力は従来と同じ)。
2026-11-21 修正: 行に limit_x, browse_rate (環境変数 LX / BRW) を入れ、ドライバのヘッダ
cycle,arm,target_rate,limit_x,browse_rate,time,object,message と列を揃えた (それ以前の events-*.csv は 2 列ずれている)。
環境変数 REASON があれば message の頭に「REASON: 」を付ける (FailedScheduling の回収用)。
2026-11-21 追加: 環境変数 EARLY に、前に取っておいた `kubectl get events -o json` のファイルを渡すと、
その中のイベントも合わせて出す。同じイベント (metadata.uid が同じ) は stdin (= 後で取った方) を使う。
API サーバの --event-ttl=5m でイベントが 5 分後に消えるため、ドライバは計測窓の始まりにも取っておく。
"""
import sys, json, os, csv

try:
    d = json.load(sys.stdin)
except Exception as e:
    print("collect_events: JSON読み取り失敗: %s" % e, file=sys.stderr)
    sys.exit(0)

cyc, arm, rate = os.environ.get('CYC', '1'), os.environ.get('ARM', '?'), os.environ.get('RATE', '?')
since = os.environ.get('SINCE', '')
lx, brw, reason = os.environ.get('LX', ''), os.environ.get('BRW', ''), os.environ.get('REASON', '')
extra = [os.environ['TL_POINT'], os.environ.get('TL_N0', '')] if 'TL_POINT' in os.environ else []

items = {}
early = os.environ.get('EARLY', '')
if early and os.path.exists(early):
    try:
        for e in json.load(open(early)).get('items', []):
            items[e.get('metadata', {}).get('uid') or id(e)] = e
    except Exception as ex:
        print("collect_events: EARLY の読み取り失敗: %s" % ex, file=sys.stderr)
for e in d.get('items', []):
    items[e.get('metadata', {}).get('uid') or id(e)] = e

rows = []
for e in items.values():
    t = e.get('lastTimestamp') or e.get('eventTime') or ''
    if since and t and t < since:
        continue
    msg = (e.get('message') or '').replace(',', ';').replace('\n', ' ')
    rows.append([cyc, arm, rate, lx, brw, t,
                 e.get('involvedObject', {}).get('name', ''),
                 (reason + ': ' + msg) if reason else msg] + extra)
rows.sort(key=lambda r: r[5])
w = csv.writer(sys.stdout)
for r in rows:
    w.writerow(r)
