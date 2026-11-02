---
name: self-review-expmain
description: 2026-10-27〜 ユーザが AI の実験を自分の目で精査中。expmain/ に◎4実験、mix-cpu2 の measure-mix-cpu.sh を Claude の解説で一緒に読んだ (11/02 中断)。見つかった問題・入れた変更・未了の一覧
metadata:
  node_type: memory
  type: project
  originSessionId: f90c3056-09d6-4afc-920b-1015a0d1d988
  modified: 2026-11-02T12:47:45.063Z
---

ユーザは論文執筆に向けて、AI が回した実験が「指示どおりに・正しく」行われたかを自分で精査している (2026-10-27 開始、11/02 に一旦区切り)。

**場所**
- 総索引: リポジトリ直下 `EXPERIMENTS.md` (全実験を時系列、状態=FOSE/修論/置換/試し)。ユーザが ◎ を付けた 4 実験 (fixed4-lb, mix-cpu2, pdist-k3 分離/同居) を `expmain/` にコピーで集約 (scripts は実験時コミットの版、README.md が索引)。
- `expmain/02-mix-cpu2/CHECKLIST.md` = measure-mix-cpu.sh の解説 (§0 全体像〜§8 シェル構文、§9 実験設計のどこまでをスクリプトが決めているか)。名前は CHECKLIST だが中身は解説 (改名するか未決)。

**進め方の変遷**: コード読解チェックリスト (難しすぎた) → 1 点を手で再測定案 (アヌビスが「検証にならない」と判定、取り下げ) → 「AI が指示どおり実行したか」の監査 → 結局 Claude の解説で measure-mix-cpu.sh を 1 つずつ一緒に読む形に落ち着いた。

**mix-cpu2 を読んで分かったこと (事実、データで確認済み)**
- 欠測 1 点 (cyc2・1台・b100v75、k6 集計の回収失敗) を解析は「未回収 0 件」と出す (回収失敗の点は CSV に行が無い)。論文は「有効 203/204、欠測 1」と書くべき。
- 冷却待ちは 204 点中 11 回 (計 94 s) しか発動していない。CSV の temp_max_c は全センサの窓内最大で冷却待ちの coretemp とは別物。
- 慣らし負荷は実質「180 s 負荷 + 約 120 s 待機」(k6 Job の sleep 300 で wait が 300 s タイムアウトまで待つ)。
- 10 秒系列 (rate[30s]) に落ち込み (主データ比 <0.7 が 1台 6%・2台 21%)。主データ (rate[160s]) とは中央値 0.993〜0.997 で一致。系列は解析に未使用。
- Prometheus の区間は sh が t_run (Pod Running を見た時刻) から計算 → k6 の実際の窓とのずれは未測定 (両端 10 s 削りで吸収する設計)。
- 仮想ユーザ数はユーザ未指定でスクリプト既定値のまま、どこにも記録なし: bundle-vs-loss2 600/4000、OB measure-mix-cpu 300/3000、SS 50/400 (+購入は NUSERS 200 まで)。fixed4-lb の崩壊点で上限 4000 に届いた可能性は未確認。
- 配合の検証: k6 達成率のずれ最大 0.44%、購入側 4 サービスは閲覧のみの点で CPU≈0 → ラベルどおり。ただし checkout は b50 (136m) が b50v75/b50v150 (117m) より約 16% 高く、周波数では説明できない (未解明、ρ の加法モデルの前提に関わる)。
- requests/limits は測定でなく設定値 (kube-state-metrics)。pods 列は全行で台数と一致。

**入れた変更 (2026-11-02、ユーザが「C にしたい」と決定。未コミット・実機未検証)**
- 時刻の記録: `km2/experiments/k6/checkout.js` (setup() が `@@@K6_START@@@ <ms>` をログに出す + 集計に k6_start_ms/k6_warmup_s/k6_summary_ms)、`rightsizing/measure-mix-cpu.sh` (区間をログに出し、k6 ログから開始時刻を読む)、`rightsizing/_write_mixpoint.py` (`<CSV名>-times.csv` に prom 区間・k6 窓・k6_late_s・margin・取得経路を書く)。作り物の入力で 4 ケース確認済み。
- 次の本番前にスモークで k6_start_src が summary/log になるか要確認 (実行はユーザ)。OB の measure-mix-cpu.sh だけ。bundle-vs-loss2.sh と SS には未導入。

**未了**
- Prometheus の保持期間・保存先の確認 (既定 10 日、emptyDir なら Pod 再作成で全消失)。確認コマンドを渡済み、ユーザの結果待ち → 延長の具体コマンドを書く。
- 推奨したが未決: Prometheus の区間を k6 の時刻で問い合わせる作りに直す / frontend のアクセスログでリクエスト数を数える独立検証 / 既知の信号 (stress-ng) での校正。
- expmain/ とルート EXPERIMENTS.md のコミット、summer2026/EXPERIMENTS.md に fixed4/fixed4b/probe5 の行を足すか、CHECKLIST.md の改名、bundle-vs-loss2.sh の解説 (fixed4-lb・pdist-k3 用)。

**Why:** ユーザは「AI にやってもらっていたこと」を自分の言葉で説明できる状態にしたい (審査・査読で答えるため)。
**How to apply:** 計算や判断はユーザに任せ、Claude は説明と食い違いの切り分けに回る。説明は 1 つずつ (下の feedback)。所見は事実/推測を分けて書く。関連 [[explain-one-step-at-a-time]] [[verify-numbers-python]] [[fose2026-live-paper]] [[cpu-frequency-not-pinned]]
