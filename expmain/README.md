# expmain — 主要実験の参照用まとめ (2026-10-27 作成)

ルートの `../EXPERIMENTS.md` で ◎ を付けた 4 つの実験について、データ・スクリプト・マニフェスト・計画・解析を実験ごとのフォルダに**コピー**したもの。自分で確認するときの作業場として使う。

## 使う前に知っておくこと

- **原本は元の場所** (`km2/experiments/...`)。ここはコピーなので、数値を直すときや論文の出所 (`FOSE2026-TeX-UTF8/fose2026-data-provenance.md`) に書くときは元の場所を指す。移動にしなかった理由は 2 つ。ドライバが元の場所を絶対パスで参照していること、出所の記録や索引が元のパスを指していること。
- **`scripts/` は実験したときの版**を git から取り出したもの。いまの版とは違うことがある (例: `measure-mix-cpu.sh` は 10/27 に更新されている)。取り出したコミットは各節に書いた。手元に未コミットの変更があった可能性までは消せない。
- **ここからは実行できない**。スクリプトの中は `REPO=/home/mizuki/ダウンロード/msa` (実験マシン) を前提にしている。
- **`manifests/`、`k6/` はいまのファイルのコピー**。どれも実験の後に変更されていないことを git で確認済み。`km2/normal/CMD` (平文の認証情報) は入れていない。
- **`analysis/` の解析スクリプトはいまの版** (`analysis-*.txt` を出した版)。
- 用語: **枠** = CPU requests。**ρ** = 閲覧 1 周が購入 1 周の何倍の CPU を使うか (ν/β)。**引きずり** = 同居 Pod の片方が、相方の需要のせいで分離のときより多い台数になること。**配合** `b50v150` = 購入 50 周/s + 閲覧 150 周/s。

## 一覧

| # | フォルダ | 日付 | 実験 | 状態 | メモ (◎ を付けたときの書き込み) |
|---|---|---|---|---|---|
| 1 | `01-fixed4-lb/` | 10-07〜08 | 固定 4 台・振り分けあり (fixed4-lb / fixed4b-lb) | FOSE には無し | 固定 1 台・2 台も振り分けありで計測するべき |
| 2 | `02-mix-cpu2/` | 10-09〜10 | ρ 精度向上の分離測定 (mix-cpu2) | 修論の主結果 | — |
| 3 | `03-pdist-k3-sep/` | 10-15 | pdist-k3 分離 | 修論の主結果 | 分離を事前に測り「基準」とし、同居した場合の損を計算する (基準の配合 b50v150 で 3 台になる枠) |
| 4 | `04-pdist-k3-pair/` | 10-16 | pdist-k3 同居 | 修論の主結果 | pdist-k3 分離の台数と比較し、損かどうかを判定 |

各フォルダの中身は同じ形にしてある: `data/` (結果 CSV・時系列・イベント・ログ)、`scripts/` (実験時の版)、`manifests/`、`k6/`、`plan/` (事前の計画・枠の表)、`analysis/` (解析スクリプトと出力)。

---

## 1. `01-fixed4-lb/` 固定 4 台・振り分けあり

**問い**: FOSE §3.1 の予備実験 (fixed4 / fixed4b、9/9〜10、振り分けなし) を、gRPC の振り分け (GRPC_LB=1) だけ変えて測り直すと、崖の位置や CPU の得は変わるか。振り分けなしでは、呼ばれる側の 4 台のうち 1 台がほぼ遊ぶほど負荷が偏っていた。

**構成**: normal (分離) / frontrecocatalog (front3) / mega × **4 台固定・HPA 無し** × requests 150m 一律・limits 据置 × 購入のみ。
- 基本帯: 150 / 200 / 250 / 300 周/s × 4 サイクル = 48 点 (`fixed4-lb`、10/07 17:50〜21:21)
- 飽和帯: 350 / 400 / 450 周/s × 4 サイクル = 34 点 (`fixed4b-lb`、10/07 21:21〜10/08 00:39)。自動再起動 2 回で front3@350・mega@400 の 1 点ずつ欠け
- WARM 90 s / MEAS 120 s。飽和帯はアームの間に 60 s、サイクルの間に 300 s 休む

**枠**: 適正化はしていない (RIGHTSIZE=0)。全コンテナ requests 150m 一律 (UNIFORM_REQ_M=150)。HPA 無しなので requests は使用量に効かない。

| フォルダ | ファイル |
|---|---|
| `data/` | `results-fixed4-lb.csv`, `results-fixed4b-lb.csv` (1 行 = 1 点)、`timeline-*.csv` (15 秒ごと)、`events-*.csv` (列ずれあり、根拠に使わない)、`fixed4-lb.log`, `fixed4b-lb.log` |
| `scripts/` | `bundle-vs-loss2.sh` と、それが呼ぶ補助 7 本。**コミット `d2f5fb1` (10/07 12:02) の版**。`start_ok.py` はこの版では使っていないので無い |
| `manifests/` | `normal/` (分離)、`front3/frontrecocatalogcart.yaml` (名前に cart が付くが中身は 3 コンテナ)、`mega/all.yaml` + `redis-cart.yaml` (MEGA_REDIS=shared で redis を外出し) |

**解析**: **専用の解析スクリプトが無い** (結果はメモリ `fixed-replica-k6.md` に手で記録)。FOSE 版の `km2/experiments/summer2026/fixed4_summary.py` に相当するものは **TODO**。

**記録上の結論** (メモリより、未検算): 崖の位置は振り分けなしと同じ。分離の到達上限は 400 周/s で 354→295 に下がった (偏りが天井の原因という説は否定側)。softirq 削減は front3 −19〜−23%、mega −47〜−53% で維持。実 CPU 時間は振り分けで normal / front3 が +8〜16%、mega の得は −13〜21% に拡大。

**再現** (`km2/experiments/summer2026/` で): `ARMS="normal frontrecocatalog mega" WARM=90 MEAS=120 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 GRPC_LB=1 RATES=... CYCLES=4 [REST_ARM=60 REST_CYCLE=300] bash bundle-vs-loss2.sh`

---

## 2. `02-mix-cpu2/` ρ 精度向上の分離測定

**問い**: 各サービスの ρ を、区間付きで実測する。10/07 の mix-cpu は buy が 2 水準・3 サイクルで ρ が分けきれない、とアヌビス点検 (10/08) で指摘されたので測り直した。

**構成**: 分離・**HPA 無し**・全サービス 1 台固定 / 2 台固定 (redis-cart は常に 1 台) × 17 配合 (buy {0,25,50,75,100} × view {0,75,150,300}、b0v0・b75v300・b100v300 を除く) × 6 サイクル = 204 点 (203 点。cyc2 1 台 b100v75 が欠測)。
- WARM 60 s / MEAS 180 s、デプロイごとに b100 を 180 s 慣らし
- 各点の前に CPU 温度 70℃ 以下まで冷却待ち、点の後 60 s 休み
- 10/09 18:09〜10/10 13:46。自動再起動 2 回 (`km2/experiments/restart-audit.md`)

**枠**: 決めていない。`km2/normal/` のマニフェストのまま (7/14 版 = 適正化前の値)。HPA 無しなので使用量に効かない。limits だけ上書き (frontend・catalog 3000m、ad 1000m)。ρ は使用量 D から出すので枠は結果に入らない。

| フォルダ | ファイル |
|---|---|
| `data/` | `results-mix-cpu2.csv` (1 行 = 点 × サイクル × 台数 × Deployment、`usage_mc` が CPU 使用量)、`results-mix-cpu2-series.csv` (10 秒ごと)、`results-mix-cpu2.log` |
| `data/ref-mix-cpu-20261007/` | `results-mix-cpu.csv` (10/07 の旧測定。`analyze_rho2.py` が比較用に読む。pairval の予測の入力) |
| `scripts/` | `measure-mix-cpu.sh`, `_write_mixpoint.py` (**コミット `c4ce1d1`、10/09 17:57 = 測定 12 分前に固定した版**)、`grpc_lb_patch.py` (`d2f5fb1`) |
| `plan/` | `plan-rho2.md` (測定前に固定した計画。解析の規則もここ) |
| `analysis/` | `analyze_rho2.py` → `analysis-rho2.txt` |

**記録上の結論** (メモリより、未検算): ρ の区間は ±0.01 程度。front ≈ catalog だけが全配合で ±6% に揃う。

**再現** (リポジトリ直下で): `POINTS="v75 v150 v300 b25 b25v75 b25v150 b25v300 b50 b50v75 b50v150 b50v300 b75 b75v75 b75v150 b100 b100v75 b100v150" REPLICAS="1 2" CYCLES=6 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=km2/experiments/rightsizing/results-mix-cpu2.csv bash km2/experiments/rightsizing/measure-mix-cpu.sh`

---

## 3・4. pdist-k3 (分離 `03-pdist-k3-sep/` と 同居 `04-pdist-k3-pair/`)

2 つで 1 つの実験。**分離 (3) が比べる相手、同居 (4) が本体**。

**問い**: ρ の近いペアと遠いペアで、同居させたときの引きずり (余分な台数 Δn) がどう違うか。台数の予測が当たるかは問わない (ユーザ指示)。

**判定**: 同居 Pod の台数 n_st と、**同じ配合の分離 12 回の台数の最頻値** n_x を比べる。n_st > n_x なら引きずられた (Δn = n_st − n_x)。分離 12 回でそろわないサービスは「回ごとのブレ」、計測窓の中で台数が変わった回は「窓内の変化」として印を付け、除かずに併記する。

**構成 (共通)**: HPA 70%・コンテナ別 (ContainerResource)・SU 30 s / SD 60 s・min 1 / max 12・**開始 1 台**・点ごとにリセット × 4 配合 (b100v0 / b50v150 / b50v300 / b100v200)。WARM 180 s / MEAS 240 s (窓 = 180〜420 s)。冷却待ち 70℃。limits 上書き (frontend・catalog 3000m、ad 1000m)。GRPC_LB=1。
- **分離 (3)**: normal × 4 配合 × **12 サイクル** = 48 回 (10/15 15:21〜22:17)。cyc12 b50v300 は k6 集計の回収失敗で results に行が無い (時系列はある)。自動再起動 1 回
- **同居 (4)**: 6 アーム × 4 配合 × 3 サイクル = 72 回 (10/16 00:10〜10:47)。アームの順番はサイクルごとに回転

| アーム | ペア |
|---|---|
| pairsP1b | checkout+shipping, catalog+reco |
| pairsP2 | front+cart, catalog+checkout |
| pairsP3 | front+catalog, currency+checkout |
| pairsQ1 | front+currency, checkout+cart |
| pairsQ2 | front+reco |
| pairsQ3 | checkout+front |

**枠** (`plan/rightsize-pdist-k3.csv`、両方で同じ表): **基準の配合 b50v150 で 3 台になる枠** r = D1(b50v150) ÷ 1.5。D1 は mix-cpu2 の 1 台・b50v150 の 6 サイクル平均。例外: ad は 800m (ペアに入れない。JIT の跳ね上がりでも 77% を超えないように)、redis-cart は 300m のまま。同居 Pod の中でもコンテナごとに同じ値。

| フォルダ | ファイル |
|---|---|
| `data/` | `results-pdistk3{sep,pair}.csv`、`timeline-*.csv` (台数の判定はこれから出す)、`events-*.csv` (列ずれ・欠けあり、根拠に使わない)、`pdistk3*.log`、`stdout-*.txt` |
| `scripts/` | `bundle-vs-loss2.sh` と、それが呼ぶ補助 8 本。**コミット `d13e185` (10/15 14:06) の版** (分離・同居とも同じ) |
| `manifests/` | (3) `normal/`。(4) `pairs*.yaml` 6 本 + `redis-cart.yaml`、同居していないサービスは `normal-unbundled/` から立つ |
| `plan/` | `plan-pdist-k3.md` (追記 1〜5 で判定の主従・開始台数・配合が変わった経緯がある。**必ず追記まで読む**)、`rightsize-pdist-k3.csv` |
| `analysis/` | `analyze_pdist_k3.py` → `analysis-pdistk3.txt` (分離と同居をまとめて解析するので 3 と 4 に同じものを置いた) |

**解析出力の要点** (`analysis/analysis-pdistk3.txt` §2、未検算): ρ の差が 0.02 以下の 4 組は、12 回中 0〜1 回しか引きずられない。差が 0.17 以上の 5 組は 6〜10 回引きずられる。front+currency (差 0.09) は 3/12。

**限界** (計画 §6・追記 5):
- 分離と同居を交互でなく別の時間帯に測っている
- payment / shipping / email の枠は 24〜32m と小さく、アイドル時の揺れが利用率に大きく出る
- 同じアームのペアは同じ実行を共有するので、10 組は独立ではない
- cart・currency・reco の終了猶予は、分離 5 s・同居 30 s で違う

**再現**: `km2/experiments/summer2026/EXPERIMENTS.md` の該当行 (コマンド全文あり)。

---

## 実験を足すとき

ここに入れるのは、ルートの `../EXPERIMENTS.md` で ◎ を付けた実験だけ。足したら、この表とフォルダを足し、`scripts/` は実験時のコミットから取り出す (`git log -1 --until="<開始時刻> +0900" -- <パス>` で調べる)。
