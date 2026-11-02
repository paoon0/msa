---
name: self-review-expmain
description: 2026-10-27〜 ユーザが AI の実験を自分の目で精査中。方法はスクリプトを読む (10/29 決定)、作業場は expmain/、総索引は ルート EXPERIMENTS.md
metadata:
  node_type: memory
  type: project
  originSessionId: f90c3056-09d6-4afc-920b-1015a0d1d988
  modified: 2026-10-29T06:09:10.197Z
---

ユーザは論文執筆に向けて、AI が回した実験を自分で精査している (2026-10-27 開始)。
- 総索引: リポジトリ直下 `EXPERIMENTS.md` (全実験を時系列、状態=FOSE/修論/置換/試し)。ユーザが ◎ を付けた 4 実験 (fixed4-lb, mix-cpu2, pdist-k3 分離/同居) を `expmain/` にコピーで集約 (scripts は実験時コミットの版)。
- 方法: 2026-10-29 にユーザが「スクリプトを読む方向」に決定 (Grafana 案は Prometheus 保持期間が不明で見送り)。全行ではなく数値が生まれる行に絞った行番号つきチェックリストを Claude が作り、ユーザが読んでチェック → 最後に生データから自分で再計算。
- 進捗: mix-cpu2 のチェックリスト `expmain/02-mix-cpu2/CHECKLIST.md` 作成済み。次は pdist-k3、fixed4-lb (解析スクリプトが無い=TODO)。

**Why:** ユーザは「AI にやってもらっていたこと」を自分の言葉で説明できる状態にしたい (審査・査読で答えるため)。
**How to apply:** 計算や判断はユーザに任せ、Claude は読む箇所の案内と食い違いの切り分けに回る。所見は「判断はあなたが」と分けて書く。関連 [[verify-numbers-python]] [[fose2026-live-paper]]
