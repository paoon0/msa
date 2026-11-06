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

**入れた変更 (2026-11-02、ユーザが「C にしたい」と決定。2ee602a でコミット済み・実機未検証)**
- 時刻の記録: `km2/experiments/k6/checkout.js` (setup() が `@@@K6_START@@@ <ms>` をログに出す + 集計に k6_start_ms/k6_warmup_s/k6_summary_ms)、`rightsizing/measure-mix-cpu.sh` (区間をログに出し、k6 ログから開始時刻を読む)、`rightsizing/_write_mixpoint.py` (`<CSV名>-times.csv` に prom 区間・k6 窓・k6_late_s・margin・取得経路を書く)。作り物の入力で 4 ケース確認済み。
- ★2026-11-02 スモーク済み (smoke-times-20261102、ユーザ了承で Claude が起動): 4 点とも k6_start_src=summary、区間は k6 窓の内側 (余裕 始め約11 s/終わり約8.5 s)、usage_mc 48 行を Prometheus 再問い合わせで全一致。exp の Sock Shop はこのとき削除。OB の measure-mix-cpu.sh だけ。bundle-vs-loss2.sh と SS には未導入。

**設計確認ダッシュボード (2026-11-02)**: Grafana に「設計の確認 (exp)」(uid design-check) を API で登録。定義と説明は km2/experiments/grafana/ (make_design_check.py, design-check.json, README.md)。スクリプトとは別経路 (Prometheus) で台数・HPA・枠・k6 時刻・区間平均 CPU を人が確かめる用。負荷量は確かめられない。Grafana は emptyDir なので Pod 再作成で消える→README の手順で登録し直す。

**アヌビス点検 (2026-11-03、smoke-times)**: 主張1・2・4 は要修正、3・5 は掲載可。核心=区間・k6 時刻は AI のコードの自己申告で循環、CSV と再問い合わせの一致は再現性であって妥当性ではない。独立経路 (kubelet のコンテナ開始 ≤ k6_start ≤ t_run 4/4、cAdvisor の CPU の立ち上がり・終わりが ±1 s) で補強可。Claude の誤報告 2 件 (「絞り 0」→実際は最大 1.2%、「cAdvisor 10 秒ごと」→実効約 15 秒) を訂正済み。series は Pod 抜けの合計が混入 (mix-cpu2 の 2 台で 20%) → 使用禁止。mix-cpu2 本体は検証不能 (Prometheus のデータ消失)。追加の優先順: ①設計↔証拠の対応表 ②点ごとに k6 の全ログと Job の yaml を保存 ③k6 を通らない負荷量の確認 (frontend のアクセスログ) ④負荷区間の自動照合 ⑤本番設定でのスモーク ⑥series と慣らし待ちの修正。related_work §9.13 に記録。

**series を案 2 に変更 (2026-11-03、ユーザ決定・未コミット・実機未検証)**: measure-mix-cpu.sh の SER を rate[30s] の query_range → 主データと同じ区間の生の記録 (range vector) に。_write_mixpoint.py が <CSV>-raw.csv (記録そのまま) と -series.csv (Pod ごとに隣り合う記録の差、列が変わった。古い形式のファイルには書かない) を出す。スモーク 4 点の実データで確認: 推移は滑らか (frontend 766/782/763/764)。★副産物の発見: 主データ usage_mc (rate) は端の空きが平均間隔×1.1 以上だと過小 (スモーク 48 行中 4 行で 8〜15% 低い、payment 60.9↔69.8 を手計算で機構確認)。mix-cpu2 本番への影響は未測定。対処はしない＝研究の限界として明記する (ユーザ決定 2026-11-03、§9.13)。生の記録は -raw.csv に残るので後から再計算は可能。k6 を通らない負荷量の確認 (frontend のログ行数) はユーザが「いらない」と判断 (2026-11-03)。

**本番設定スモーク smoke-prod-20261103 (2026-11-03 00:46〜01:31、Claude 起動)**: 6 点回収、時刻の余裕 全点プラス (始め約11 s/終わり約8.5 s)、新 -raw/-series 正常。重い点の取りこぼし buy 11〜31 は mix-cpu2 本番の同じ点と同程度。rate の過小評価を実測: 160 s 区間で 72 行中 11 行が 1% 超低く最大 7.5% (限界として §9.13 に記載)。

**未了**
- Prometheus の保持期間: 2026-11-02 に Claude が確認済み = retention 10d・容量上限なし・保存先 emptyDir (PVC なし)・最古 10/23 21:00・約 2 GB。◎4 実験の Prometheus 生データは既に消失 (CSV とログのみ残る)。related_work §9.12 に記録。★2026-11-02 22:28 ユーザ指示で変更済み: retention 180d + PVC (microk8s-hostpath 100Gi) に切替 (kubectl patch prometheus、旧データは消去、ユーザは全実験やり直す方針)。helm upgrade で戻る恐れあり。
- 推奨したが未決: Prometheus の区間を k6 の時刻で問い合わせる作りに直す / frontend のアクセスログでリクエスト数を数える独立検証 / 既知の信号 (stress-ng) での校正。
- expmain/ とルート EXPERIMENTS.md のコミット、summer2026/EXPERIMENTS.md に fixed4/fixed4b/probe5 の行を足すか、CHECKLIST.md の改名、bundle-vs-loss2.sh の解説 (fixed4-lb・pdist-k3 用)。

**Why:** ユーザは「AI にやってもらっていたこと」を自分の言葉で説明できる状態にしたい (審査・査読で答えるため)。
**How to apply:** 計算や判断はユーザに任せ、Claude は説明と食い違いの切り分けに回る。説明は 1 つずつ (下の feedback)。所見は事実/推測を分けて書く。関連 [[explain-one-step-at-a-time]] [[verify-numbers-python]] [[fose2026-live-paper]] [[cpu-frequency-not-pinned]]

- 2026-11-03 mix-cpu3 本走 (mix-cpu2 と同設定の取り直し、コミット e785dc3 のスクリプト) 完了 03:59〜23:34。204/204 点、取りこぼし超過 0、絞り>5% は cyc3 2台 v75 payment 5.9% の 1 件、余裕最小 6.9 s。解析は未実施 (索引 summer2026/EXPERIMENTS.md)
