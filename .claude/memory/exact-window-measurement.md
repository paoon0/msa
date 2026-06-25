---
name: exact-window-measurement
description: "How to measure exactly the last 10min of a 13min load run from Prometheus, after the fact"
metadata: 
  node_type: memory
  type: project
  originSessionId: d2cea3bd-2c2c-4109-8e64-b9f6f7d126fa
---

実験プロトコル: loadgenerator Job が 13分(RUN_TIME=13m)負荷をかけ、**最後の10分を本計測区間**とする(先頭3分はウォームアップ除外)。

「その区間だけをピタリと計測できない」問題の解 = ライブで捕まえようとせず、**事後に Prometheus の蓄積カウンタから厳密窓を再構成する**。
- 窓の絶対時刻を Job から確定: `kubectl get job loadgenerator -o jsonpath='{.status.startTime}'`(RFC3339)。t0 = startTime+180s, t1 = startTime+780s。
- カウンタは累積なので、**窓内平均 rate = (counter@t1 − counter@t0)/(t1−t0)**。Prometheus `/api/v1/query?query=<counter>&time=<t0>` と `&time=<t1>` の2点を引いて差分。rate()/increase() のような端の外挿が無く厳密。
- 注意: 2点差分は窓内のカウンタリセット(pod 再起動)を検知できない → 安定 run 前提。心配なら `resets(counter[600s] @ t1)` で確認。

このロジックは計測ヘルパースクリプトに実装予定(km2/approach あたり)。関連: [[coloc-resource-efficiency-study]] [[monitoring-stack]]
