# 全実験の索引 (リポジトリ全体、2026-10-27 作成)

修士研究で回した実験を、アプリ・フォルダをまたいで**時系列で 1 枚に並べた総索引**。
条件・再現コマンド・除外の詳細は「詳細」列の索引にある (ここには重複して書かない。食い違いを防ぐため)。

- **パスはすべてリポジトリ直下 (このファイルの場所) から見た相対パス**。
- **日付の出所**: 「ログ」= ログ先頭の START 時刻 (正確)。「git」= そのファイルが最初にコミットされた日 (実験はその日かそれ以前。7 月以前の softirq/hpa はログが残っていないのでこれしかない)。「CSV」= CSV の ts 列。
- **状態**: **FOSE** = FOSE2026 論文の数値に使用 (出所は `FOSE2026-TeX-UTF8/fose2026-data-provenance.md`) / **修論** = 修論の主結果・候補 (`km2/experiments/restart-audit.md` §2 の位置づけ) / **本番** / **置換** = 後の測定で置き換え / **撤回** = 結論を撤回 / **試し** / **中断** / **—** = 位置づけ未記録 (初期の探索)。
- ★ = 2026-10-27 時点で下位の索引に行が無かったもの (ここで初めて索引化)。

## 下位の索引 (詳細はこちら)

| 索引 | 範囲 |
|---|---|
| `km2/experiments/README.md` | OB の 2026-06〜09、フォルダ別 (softirq / hpa / perservice-cpu / rightsizing / edge-traffic) |
| `km2/experiments/summer2026/EXPERIMENTS.md` | OB の 2026-08-18〜10-16 の主力実験。条件と再現コマンド付き |
| `km2/experiments/k6/README.md` | k6 による開ループ化 (2026-07-15〜) |
| `km2/experiments/latency-breakdown/investigation-writeup.md` | レイテンシ分解と固定台数スイープ (2026-07) |
| `sockshop/experiments/EXPERIMENTS.md` | Sock Shop の全実験 (2026-10-17〜) |
| `km2/approach/comm-experiment/README.md`, `km2/approach/echo/README.md` | 初期の通信時間実験 (2026-06) |
| `km2/experiments/restart-audit.md` | 9/16 以降の全実験ログの実行区間と、MicroK8s 自動再起動との重なり |
| `FOSE2026-TeX-UTF8/fose2026-data-provenance.md` | FOSE2026 本文の数値 → CSV の列 → スクリプト |

## 一覧 (時系列)

### Online Boutique (OB)

| 日付 | 出所 | 呼び名 | 状態 | 何を見たか (1 行) | 結果 CSV | 詳細 |
|---|---|---|---|---|---|---|
| 06-15 | CSV | 初期 megapod | — | 分離 vs 全部入りの CPU/req (v1 はネットワーク計測が壊れていた版) | `km2/experiments/archive-202606/results.csv`, `km2/experiments/archive-202606/results_v1_brokennet.csv` | `km2/experiments/README.md` §8 |
| 06-24 | git | エコー法 | — | localhost vs ClusterIP の通信時間 (処理ゼロのサーバ) | `km2/approach/echo/results.csv` | `km2/approach/echo/README.md` |
| 06-28 | git | ★ outmail 通信時間 | — | 本物の checkout→email で比較。差は検出限界以下 (対照 payment もノイズで動く) | `km2/approach/comm-experiment/results-20260628.csv` | `km2/approach/comm-experiment/README.md` |
| 06-29〜30 | git | 基線診断・分離 vs 全部入り | — | 基線ドリフト、softirq の比較とスイープ | `km2/experiments/softirq/baseline-probe.csv`, `km2/experiments/softirq/baseline-repeat.csv`, `km2/experiments/softirq/results-compare.csv`, `km2/experiments/softirq/results-cpu.csv`, `km2/experiments/softirq/results-cpu-smoke.csv`, `km2/experiments/softirq/results-softirq-smoke.csv`, `km2/experiments/softirq/results-sweep.csv` | `km2/experiments/README.md` §1–2 |
| 06-30〜07-06 | git | 部分集約の用量反応 | — | 1 つずつ同居させたときの softirq/req | `km2/experiments/softirq/results-outmail.csv`, `km2/experiments/softirq/results-outpy.csv`, `km2/experiments/softirq/results-paymail.csv`, `km2/experiments/softirq/results-frontcart.csv`, `km2/experiments/softirq/results-frontcatalog.csv`, `km2/experiments/softirq/results-frontreco.csv`, `km2/experiments/softirq/results-front4.csv`, `km2/experiments/softirq/results-replicasweep.csv` | `km2/experiments/README.md` §3 |
| 07-07 | git | HPA スイープ・HPA 比較 | — | スケールしても softirq/req はフラット。front3 vs 分離 | `km2/experiments/hpa/results-hpasweep.csv`, `km2/experiments/hpa/results-hpacompare.csv` | `km2/experiments/README.md` §4 |
| 07-13〜14 | git | コンテナ別 HPA (SCALE_ALL) | — | Pod 平均 vs コンテナ別しきい値。u480 の双安定 | `km2/experiments/hpa/results-hpapercont.csv`, `km2/experiments/hpa/results-hpapercont-allscale.csv`, `km2/experiments/hpa/results-hpapercont-allscale-max8.csv` | `km2/experiments/README.md` §4 |
| 07 | — | ボトルネック・失敗診断 | — | email のスロットリング、fails = HTTP 500 (CSV でなく txt)。**ボトルネック診断の出力 txt は下位索引に書かれているが実在しない** (結論はメモリ `hpa-throttling-blindspot` 等にのみ残る) | `km2/experiments/hpa/fail-capture-multi.txt` (スクリプト `km2/experiments/hpa/bottleneck-diag.sh`) | `km2/experiments/README.md` §5 |
| 07-13〜14 | ログ | レイテンシ分解・台数スイープ | — | 分離が頭打ちする理由。★ latency-sweep は writeup にのみ記載 | `km2/experiments/latency-breakdown/smoke.csv`, `km2/experiments/latency-breakdown/latency-sweep.csv`, `km2/experiments/latency-breakdown/replica-count-sweep.csv` | `km2/experiments/latency-breakdown/investigation-writeup.md` |
| 07-15 | ログ | ★ k6 動作確認 t3 / t4 | 試し | bundle 200 周/s の試走 | `km2/experiments/k6/t3.csv`, `km2/experiments/k6/t4.csv` | `km2/experiments/k6/README.md` |
| 07-15〜17 | ログ | k6 スイープ | — | 開ループで容量の崖を測る | `km2/experiments/k6/k6-sweep.csv`, `km2/experiments/k6/k6-sweep-run1.csv`, `km2/experiments/k6/k6-sweep-3arm-3cyc.csv` | `km2/experiments/k6/README.md` |
| 08-18 | ログ | B 測定 (利用率カーブ) | **FOSE** (§4 予約枠の適正化) | 分離 1 台固定でサービス別の CPU カーブ | `km2/experiments/perservice-cpu/results-perservice-cpu.csv`, `km2/experiments/summer2026/rightsize-requests.csv` | `km2/experiments/summer2026/EXPERIMENTS.md` |
| 08-19 | ログ | 決着実験 第 1 版 | **撤回** | 束ね vs 粒度損 | `km2/experiments/summer2026/results-bundle-vs-loss.csv` | 同上 |
| 08-19 | ログ | 決着実験 第 2 版 | — | HPA 判断時の利用率を時系列で記録 | `km2/experiments/summer2026/results-bundle-vs-loss2.csv` | 同上 |
| 08-19 | ログ | 適正化検証 | — | 枠の適正化 @200 周/s | `km2/experiments/summer2026/results-rightsized.csv` | 同上 |
| 08-20 | ログ | 負荷スイープ | — | 4 構成 × 150〜300 | `km2/experiments/summer2026/results-loadsweep.csv` | 同上 |
| 08-29 | ログ | 実験 B (limits の因果) | — | 上限 ×10 で悪化 = 上限は保護装置 | `km2/experiments/summer2026/results-expB-limits.csv` | 同上 |
| 08-29〜09-01 | ログ | 開始台数の検証 | — | 250 周/s の崩壊 = 増やし遅れ | `km2/experiments/summer2026/results-prescale.csv`, `km2/experiments/summer2026/results-prescale250.csv`, `km2/experiments/summer2026/results-prescale1.csv` | 同上 |
| 09-01 | ログ | ★ p1-4arms | 試し (約 1 分で終了) | 実験 9/1 の直前の試走 | `km2/experiments/summer2026/results-p1-4arms.csv` | ログ `km2/experiments/summer2026/p1-4arms.log` |
| 09-01 | ログ | 実験 9/1 (rs4) | — | 束ねの得 = 台数の節約 | `km2/experiments/summer2026/results-rs4.csv` | `km2/experiments/summer2026/EXPERIMENTS.md` |
| 09-02 | ログ | ★ mixtest | 試し | 混合負荷の前の試走 (normal / frontrecocatalog × 100 × 1 回) | `km2/experiments/summer2026/results-mixtest.csv` | ログ `km2/experiments/summer2026/mixtest.log` |
| 09-02〜03 (ログは 09-13 まで追記) | ログ | 実験 9/2・9/3 (混合) | **FOSE** (表 1・§5) | 閲覧型を積んで需要のズレを作る | `km2/experiments/summer2026/results-mix.csv` | `km2/experiments/summer2026/EXPERIMENTS.md` |
| 09-03〜04 | ログ | 実験 9/4 (枠 1/3) | — | requests だけ 1/3 にして分解能を上げる | `km2/experiments/summer2026/results-scale3.csv` | 同上、`km2/experiments/summer2026/analysis-scale3.md` |
| 09-07 (ログは 09-14 まで追記) | ログ | 実験 9/7 (需要ズレ最大) | **FOSE** (表 1・§5) | checkout / email と束ね、損の向きの反転 | `km2/experiments/summer2026/results-mix2.csv` | 同上、`km2/experiments/summer2026/analysis-mix2.md` |
| 09-07 | ログ | 実験 9/7 (購入スイープ) | — | 購入 150 で 4 ペアとも損ゼロ、250 は全崩壊 | `km2/experiments/summer2026/results-ratesweep2.csv` | `km2/experiments/summer2026/EXPERIMENTS.md` |
| 09-08 | ログ | 通信量実測 (Pod 単位・エッジ単位) | **FOSE** (§5 affinity の割合) | cAdvisor と `ss -tin` でエッジの太さ | `km2/experiments/edge-traffic/results-edge-traffic.csv`, `km2/experiments/edge-traffic/results-edge-pairs.csv` | 同上、`km2/experiments/README.md` §7 |
| 09-09〜10 | ログ | ★ 固定 4 台 (fixed4 / fixed4b) | **FOSE** (§3.1 予備実験) | HPA 無し 4 台固定、softirq と崖。下位索引には行が無く provenance にのみ記載 | `km2/experiments/summer2026/results-fixed4.csv`, `km2/experiments/summer2026/results-fixed4b.csv`, `km2/experiments/summer2026/fixed4-all-points.csv` | `FOSE2026-TeX-UTF8/fose2026-data-provenance.md` §3.2 |
| 09-10 | ログ | ICTer affinity の再現 | **FOSE** (§3 バイト量 +2〜4%) | 先行研究の指標ではバイト量が減らない | `km2/experiments/edge-traffic/results-icter-affinity.csv` | `km2/experiments/README.md` §7 |
| 09-11 | ログ | ★ プローブ対照 (probe5) | 査読対策 (FOSE の草稿に記載) | readiness timeout 1→5 s でも分離は回復しない | `km2/experiments/summer2026/results-probe5.csv` | ログ `km2/experiments/summer2026/probe5.log`、`FOSE2026-TeX-UTF8/fose2026-draft.md` |

| 10-06〜07 | ログ | gRPC 振り分けの確認 | 試し (結論は既定 GRPC_LB=1 の根拠) | lbcheck / lbfix / lbctl。★ lbarm0 / lbarm1 (front3・mega) は下位索引に無い | `km2/experiments/summer2026/smoke/results-lbcheck.csv`, `km2/experiments/summer2026/smoke/results-lbfix.csv`, `km2/experiments/summer2026/smoke/results-lbctl.csv`, `km2/experiments/summer2026/smoke/results-lbarm0.csv`, `km2/experiments/summer2026/smoke/results-lbarm1.csv` | `km2/experiments/summer2026/EXPERIMENTS.md` |

|×10-07 | ログ | 混合負荷 CPU (mix-cpu) | 修論 (ρ の初回、mix-cpu2 の前段) | 分離 1 台・2 台固定 × 10 配合 | `km2/experiments/rightsizing/results-mix-cpu.csv` | 同上 |→冷却時間や測定点の問題からmix-cpu2にて計測しなおす

|◎10-07〜08 | ログ | 固定 4 台・振り分けあり (fixed4-lb / fixed4b-lb) | FOSE には無し | fixed4 を GRPC_LB=1 だけ変えて再実行 | `km2/experiments/summer2026/results-fixed4-lb.csv`, `km2/experiments/summer2026/results-fixed4b-lb.csv` | 同上 |( 固定1台・2台も振り分けありで計測するべき)

|×10-08 | ログ | 同居ペアの台数予測 (pairval) | 修論候補 | 事前登録の前向き検証 → 合格 | `km2/experiments/summer2026/results-pairval.csv` | 同上 |

|◎10-09〜10 | ログ | ρ 精度向上 (mix-cpu2) | **修論の主結果** | 分離 1 台・2 台 × 17 配合 × 6 サイクル | `km2/experiments/rightsizing/results-mix-cpu2.csv` | 同上 |
→HPAなし・台数固定の測定　枠は使用量Dに着目するため、従来の枠を用いて実験。limitのみの変更は行う。

|×10-14 | ログ | P の近さと引きずり (pdist) | 修論候補 | 3 アーム × 3 配合 × 開始 1/2 台 | `km2/experiments/summer2026/results-pdist.csv` | 同上 |(Pの話だったけど、複雑だったので、ρを基準にするため、pdist-k3を開始)

|×10-15 | ログ | ★ pdist-k3 分離 開始 3/4 台 (pdistk3n) | **中断** (使わない) | ユーザ指示で 14:30 ごろ停止、2 点のみ | `km2/experiments/summer2026/results-pdistk3n.csv` | `km2/experiments/rightsizing/plan-pdist-k3.md` |

|◎10-15 | ログ | pdist-k3 分離 | **修論の主結果** | 分離 12 サイクル | `km2/experiments/summer2026/results-pdistk3sep.csv` | `km2/experiments/summer2026/EXPERIMENTS.md` |→分離を事前に図り、「基準」として計測し、同居した場合の損を計算する(基準の配合 b50v150 のときに 3 台になる枠にしました。)

|◎10-16 | ログ | pdist-k3 同居 | **修論の主結果** | 6 ペア構成 × 4 配合 × 3 サイクル | `km2/experiments/summer2026/results-pdistk3pair.csv` | 同上 |→pdist-k3分離の台数と比較を行い、損かどうかを判定

|×10-19〜20 | ログ | ★ OB 限界の粗い測定 (limit-coarse) | 補足 (FOSE には無し) | 購入 200 まで通過・250 で email 絞り 14%、閲覧 800 まで通過 | `km2/experiments/rightsizing/results-limit-coarse.csv` | `km2/approach/related_work.md` §10、スクリプト `km2/experiments/rightsizing/measure-limit.sh` / `km2/experiments/rightsizing/analyze_limit.py` |

### Sock Shop (SS)

すべて `sockshop/experiments/EXPERIMENTS.md` に詳細あり。

| 日付 | 出所 | 呼び名 | 状態 | 結果 CSV |
|---|---|---|---|---|
| 10-17 | ログ | 枠決めの予備測定 (probe-cpu) | 試し | `sockshop/experiments/probe-cpu.csv` |
| 10-19 | ログ | ρ 初回 (mix-cpu) | **置換** (mix-cpu2b へ) | `sockshop/experiments/results-mix-cpu.csv` |
| 10-19 | ログ | readinessProbe 10 s (probe10 / probe10b) | 試し (方法節の根拠) | `sockshop/experiments/probe10-cpu.csv`, `sockshop/experiments/probe10-ready.csv`, `sockshop/experiments/probe10b-cpu.csv`, `sockshop/experiments/probe10b-ready.csv` |
| 10-20 | ログ | 耐久試験 (stress) | 試し (格子の上限決め) | `sockshop/experiments/results-stress.csv` |
| 10-20 | ログ | 格子の角 (smoke-mix2b / -corner) | 試し | `sockshop/experiments/smoke-mix2b.csv`, `sockshop/experiments/smoke-mix2b-corner.csv` |
| 10-20〜21 | ログ | ρ 本測定 (mix-cpu2b) | **修論の主結果** (cyc2 × 2 台を除く) | `sockshop/experiments/results-mix-cpu2b.csv` |
| 10-26 | ログ | 同 cyc2 × 2 台の取り直し (redo2) | **本番** (上と差し替え) | `sockshop/experiments/results-mix-cpu2b-redo2.csv` |

### スモーク (動作確認。結論には使っていない)

内容を記録した索引は無い。日付は `km2/experiments/restart-audit.md` §2 のログ区間から (9/25 以前の分は git の日付で、再編時にまとめてコミットされたため実際の実行日は不明)。

| 日付 | 出所 | ファイル (先頭部分。`-tl` / `-ev` / `-timeline` / `-events` / `-series` が付いたものは同じ回の付属) |
|---|---|---|
| 〜09-25 | git | `km2/experiments/summer2026/smoke/` の `smoke4`, `smoke4w`, `smokeB`, `smoke13`, `smoke13b`, `smoke13c`, `smoke-browse`, `smoke-dw`, `smoke-inc`, `smoke-newarms`, `smoke-res` |
| 10-07 | ログ | `km2/experiments/rightsizing/smoke/smoke-mix.csv` |
| 10-08 | ログ | `km2/experiments/summer2026/smoke/results-smoke-pairval.csv` |
| 10-09 | ログ | `km2/experiments/summer2026/smoke/smoke-mix2.csv` |
| 10-14 | ログ | `km2/experiments/summer2026/smoke/results-smoke-pdist.csv` |
| 10-15 | ログ | `km2/experiments/summer2026/smoke/results-smoke-pdist2.csv` (中断), `km2/experiments/summer2026/smoke/results-smoke-pdistk3.csv`, `km2/experiments/summer2026/smoke/results-smoke-k3b.csv` |

## 実験ではない CSV (入力・予測・採点)

| ファイル | 役割 |
|---|---|
| `km2/experiments/rightsizing/rightsize-pairval.csv`, `km2/experiments/rightsizing/rightsize-pdist.csv`, `km2/experiments/rightsizing/rightsize-pdist-k3.csv`, `km2/experiments/rightsizing/rightsize3-requests.csv` | 各実験で使った枠 (requests) の表 |
| `km2/experiments/rightsizing/predictions-pairs.csv`, `km2/experiments/rightsizing/predictions-pairval-K1.csv`, `km2/experiments/rightsizing/predictions-pairval-K2.csv`, `km2/experiments/rightsizing/predictions-pdist.csv` | 実験前に固定した予測 |
| `km2/experiments/rightsizing/score-pairval-cells.csv`, `km2/experiments/rightsizing/score-pairval-cells-K2.csv` | pairval の採点結果 |

## 実験を足したら

アプリごとの索引 (OB = `km2/experiments/summer2026/EXPERIMENTS.md`、SS = `sockshop/experiments/EXPERIMENTS.md`) に行を足し、ここにも 1 行足す (`CLAUDE.md`「実験の記録」)。
