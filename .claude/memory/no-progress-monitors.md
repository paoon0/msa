---
name: no-progress-monitors
description: Monitorツールを進捗通知に使わない。「● Monitor event: ...」の行が数分おきにターミナルに出るのを嫌う
metadata:
  type: feedback
---

**Monitor ツールを長時間処理の進捗通知に使わない。** 2026-09-07、実験のスモーク中に「`● Monitor event: "スモーク実験の進捗と失敗"` という項目が2分おきくらいに表示されていたのでやめてほしかった」と指摘された。

**Why:** 嫌われたのは進捗の中身ではなく、**Monitor が出す通知行そのものがターミナルに繰り返し表示されること**。実験1点ごとにこの行が積み上がって画面が埋まる。

**How to apply:** 長時間の実験・ビルドの待機は `Bash` の `run_in_background` に完了条件の `until` ループを置き、**通知は完了時の1回だけ**にする。進捗を伝えたいときは Monitor ではなく、自分の応答の中で必要なときにまとめて書く。関連: [[verify-numbers-python]]
