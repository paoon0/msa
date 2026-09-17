# FOSE2026 ライブ論文 — 提出記録とデータの出所

作成 2026-09-18。目的: 論文に載せた数値を **どのデータから、どの計算で** 出したかを残し、
求められたときに開示・再現できるようにする。

## 1. 提出記録

- **提出日時**: 2026-09-14 (締切 17:00) に EasyChair (conf=fose2026) へ PDF を提出
- **提出版のスナップショット**: `FOSE2026-TeX-UTF8/submitted-20260914/` (tex / bib / pdf)

  | ファイル | MD5 |
  |---|---|
  | fose2026.tex | `86a5ec815c5e34a73559d90c8fd3dfbc` |
  | fose2026.bib | `1ef91a57f2beac5ecb2a71d0b6447a41` |
  | fose2026.pdf | `222835eccaa21a40cff3ab60a8b563bc` |

- **ビルド手順** (TeX Live 2026, `FOSE2026-TeX-UTF8/` で):
  `platex fose2026; pbibtex fose2026; platex fose2026; platex fose2026; dvipdfmx fose2026`
  (`latexmk` は未導入。`fose.cls`/`fose.sty`/`jssst.bst` は FOSE2026 配布テンプレート同梱)
- **題**: Kubernetes HPA 環境下におけるコンテナ同居の効果と選択条件 /
  Effects and Selection Conditions of Container Colocation under Kubernetes HPA
- **著者**: 田尾 瑞紀 (和歌山大学大学院 システム工学研究科), 満田 成紀 (和歌山大学戦略情報室)
- 採否通知 9/18、カメラレディ 9/25 17:00

## 2. 実験環境 (共通)

- 対象: Online Boutique **v0.10.3** (`GoogleCloudPlatform/microservices-demo`, Apache-2.0)。
  checkoutservice のみ `src/checkoutservice` から再ビルドした `mizuki0118/mygo:bunpupaymail` (メトリクス用ポート追加。ロジック変更なし)
- クラスタ: MicroK8s 単一ノード 16 コア (`km2/approach/hpa-experiment-method.md` に詳細)
- 負荷: k6 (open-loop, constant-arrival-rate)。スクリプト `km2/experiments/k6/checkout.js`, Job `km2/experiments/k6/k6-job.yaml`
- 同居の実現: 同一 Pod に複数コンテナ、呼び出し元の `*_SERVICE_ADDR` を `localhost:<port>` に変更。
  マニフェスト `km2/experiments/summer2026/manifests/*.yaml` (ペア), `km2/frontrecocatalogcart/` (front3), `km2/all/all.yaml` (mega)
- 主指標: node の softirq モード CPU (`node_cpu_seconds_total{mode="softirq"}` を Prometheus から `sum(rate(...))`)。
  取得の実装は各実験スクリプト内 (`promq` 関数)

## 3. 論文の数値 → データ → 計算スクリプト

再計算は 2026-09-18 に実施し、「再現」列は論文値と一致したかを示す。

### 3.1 §3 「単一ノードではバイト量がほとんど変わらない (実測 +2--4%)」

| 項目 | 値 |
|---|---|
| データ | `km2/experiments/results-icter-affinity.csv` (2026-09-10, `icter-affinity.sh`) |
| 条件 | 分離 / front3 / mega、全サービス 1 台固定・HPA 無し・buy(100)、ウォーム 30 s・計測 180 s・2 サイクル |
| 測り方 | 各 Pod の netns の `/proc/net/dev` を計測窓の前後で読み差分 (デバイス層 = ヘッダ込み)。k6→frontend のクライアント辺は k6 Pod の cAdvisor 送信バイトを差し引く |
| 計算 | `km2/experiments/icter_affinity_summary.py` |
| 結果 | 分離 31,173 B/周、front3 31,797 (+2.0%)、mega 32,478 (+4.2%)。パケット数 232→227 |
| 再現 | **一致** |

### 3.2 §3.1 予備実験 (台数 4 固定・HPA 無し)

| 項目 | 値 |
|---|---|
| データ | `km2/experiments/summer2026/fixed4-all-points.csv` (= `results-fixed4.csv` 基本帯 3 サイクル + `results-fixed4b.csv` 飽和帯 6 サイクル を 1 点 1 行に統合) |
| 実行 | `bundle-vs-loss2.sh` を `FIXED_REPLICAS=4 UNIFORM_REQ_M=150` で (全コンテナ requests 150m 一律 → 4 台 × 10 コンテナ + redis 1 = 6.30 コア)。**warm 90 s / meas 120 s** (`fixed4.log` 1 行目。§4 本実験の 180/240 s とは別で、本文 §3.1 には未記載)。ログ `fixed4.log` (2026-09-09 19:54 JST〜), `fixed4b.log` (09-10 02:53 JST〜) |
| 飽和帯の範囲 | `results-fixed4b.csv` には buy(350)/(400) だけの別走 cycle 7–12 (09-10 17:26 JST〜) も入っているが、450 と一緒に測った **cycle 1–6 に統一** (ユーザ判断 09-13)。`fixed4-all-points.csv` はその 6 サイクルのみ |
| 計算 | `km2/experiments/summer2026/fixed4_summary.py` (softirq[ms/周] = softirq[コア秒] / (目標レート × 120 s) × 1000) |
| 結果 | softirq/周 削減: front3 −22.9/−23.1/−17.4/−18.3% (buy 150/200/250/300)、mega −50.6/−48.2/−46.5/−42.9%、取りこぼし 0。buy(450): 分離 359.6±22.9、front3 439.5±5.5、mega 437.4±1.6 周/s (n=6、取りこぼし窓>0 は全構成 6/6)。参考: buy(350) 分離 348.0±4.0 (取りこぼし 3/6)、buy(400) 分離 361.6±26.8 (6/6) / front3 399.5 (5/6) / mega 399.9 (1/6) |
| 再現 | **一致** (本文 17–23% / 43–51% / 約440 / 359.6±22.9) |

### 3.3 §4 予約枠の適正化 (c0, c1, (c0+100c1)/0.7)

| 項目 | 値 |
|---|---|
| データ | `km2/experiments/results-perservice-cpu.csv` (2026-08-18 B測定: 分離・1 台固定・HPA 無し・buy 10/30/60/90/120/150 周/s の 6 点) |
| 計算 | `km2/experiments/summer2026/rightsize.py` (最小二乗で 1 次近似、frontend は上限到達の 2 点を除外) → `rightsize-requests.csv` |
| 使用値 | frontend 1077m, catalog 662m, reco 742m, cart 560m, checkout 321m, email 119m (列 `request_m`) |
| 適用 | `bundle-vs-loss2.sh` の `RIGHTSIZE=1 RS_SERVICES=...` (`apply_rightsize.py`)。limits は据え置き |

### 3.4 §4 本実験の HPA 設定・負荷

`bundle-vs-loss2.sh` の実行パラメータ (`fose2026-draft.md` 執筆メモ「5サイクル統一」に原文):
`RATES=100 BROWSE_RATE="0 100 200 300" HPA_TARGET=70 HPA_MIN=1 HPA_MAX=8 SU_WIN=30 SD_WIN=60 PRESCALE=1 WARM=180 MEAS=240 SAMPLE=15 PRE_VUS=600 MAX_VUS=4000 CYCLES=5 RIGHTSIZE=1`
HPA は `autoscaling/v2`、コンテナごとに `ContainerResource` (cpu, Utilization 70%) を 1 本ずつ (`make_hpa` 関数)。判断周期は Kubernetes 既定 15 s。

- 実行 2026-09-13 18:41 〜 09-14 04:00 頃 (5 サイクル統一)
- 結果: `results-mix.csv` (frontcatalog / frontreco / frontcart)、`results-mix2.csv` (frontemail / frontcheckout / checkoutemail / catalogcheckout)
- 時系列 (15 s ごとの利用率・台数): `timeline-mix.csv`, `timeline-mix2.csv`。HPA イベント: `events-mix*.csv`。ログ `mix.log`, `mix2.log`

### 3.5 表1 「必要台数の食い違い」

| 項目 | 値 |
|---|---|
| 定義 | n(s) = 分離配置 (arm=normal) で HPA が到達した台数 (`results-*.csv` の `replicas` 列)。同じ (cycle, view) で n(左) < n(右) なら「左が引きずられる」= `n<`、逆は `n>`。4 view × 5 cycle = 20 点 |
| 分母 | 同居アームの測定も存在する点だけ (frontcart の cycle1 view300 が欠測 → 19) |
| 計算 | `km2/experiments/summer2026/table1_mismatch.py` |
| 再現 | **全 6 行一致** (3/20, 7/20, 6/20, 9/20, 10/19, 11/20 とセル内容) |
| 6 組の選び方 | mix (frontcatalog / frontreco / frontcart) と mix2 (frontemail / frontcheckout / checkoutemail / catalogcheckout) にある 2 サービス同居 7 組のうち、**catalog+checkout を除いた 6 組** (ユーザ判断 09-13)。3〜4 サービス同居 (frontrecocatalog, frontrecocartcatalog) は対象外。除いた catalog+checkout は 4/20 で反転あり (v0: catalog 1<、v100: checkout 2>、v300: 1>) — スクリプトに参考行として出力。査読「6 組を選んだ理由」への答えはこの列挙になる |
| 旧版 | 3 サイクル時点 (09-13 17:10) の損点数は frontcatalog 4/24・frontreco 1/12・frontcart 6/11・frontemail 7/12・frontcheckout 6/12・checkoutemail 5/12・catalogcheckout 2/12。5 サイクル完了 (09-14 04:39) で表1に置換 |

### 3.6 §5 「向きが一定な3組は 5--9%，反転する3組は 28--48%」

| 項目 | 値 |
|---|---|
| データ | `timeline-mix.csv`, `timeline-mix2.csv` の arm=normal 行 (cycle 1–5)、列 `hpa_util_pct`, `current_replicas` |
| 元の計算 | 2026-09-13 20:27 に awk ワンライナーで計算し TeX に直接記載 (セッション記録 `~/.claude/projects/c--msa/8798bd8a-….jsonl` 行 3211 にのみ残存) |
| 方法 | 需要 D_s(cycle, view) = 利用率/100 × 台数 を時系列の**全サンプル**で平均。組 (A, B) の予約枠をそれぞれ kA, kB 倍 (0.20–4.00、0.01 刻み) し、必要台数 n = max(1, ceil(D/k/**0.77**)) が全 20 点で n_A = n_B となる (kA, kB) のうち max(\|kA−1\|, \|kB−1\|) 最小のものを解とする。0.77 = 目標 70% × HPA 許容幅 1.1 |
| 計算 | `km2/experiments/summer2026/requests_shift_search.py` (awk を Python に移植、2026-09-18) |
| 結果 | reco 9% (frontend×0.98, reco×0.91)、catalog 8% (×1.08, ×0.92)、checkout+email 5% (×0.98, ×1.05) → **5–9%**。cart 28% (×1.28, ×1.17)、frontend+checkout 48% (×0.80, ×0.52)、frontend+email 47% (×0.80, ×0.53) → **28–48%** |
| 再現 | **一致** (2026-09-18 に Python 移植版で確認) |
| 注意 | 条件を変えると値は変わる (片側のみ・θ=0.70・計測窓のみ → 一定組 1–11%、反転組 37–39%、cart は解なし: `--variant`)。論文に書いた「28–48%」は上の方法 (両側・θ=0.77・全区間) に固有の値なので、開示時はこの条件を添える。§5.1 の記述「各組の全20点で損を消せる予約枠を探すと」は両サービスの枠を同時に動かした探索である |
| **★不整合 (2026-09-18 判明)** | 元の awk は需要の平均に**ウォームアップ中 (t=0–180 s) のサンプルも含めている** (時系列は 0–411 s の 28 サンプル、awk は `hpa_util_pct` が空でない行を全部使い、`t_rel` で絞っていない)。論文本文は「180 秒のウォームアップ後 240 秒を計測」なので**記述と計算が食い違う**。計測窓のみ (`--window`) で同じ探索をすると **一定組 7 / 11 / 8% → 7–11%、反転組 24 / 19 / 42% → 19–42%** (frontend+checkout が 48%→19% と大きく動く)。結論「反転する組は大きなずらしを要する」は変わらないが数値は変わる |
| 原因 | 締切前日 (9/13 20:15–20:28) に使い捨ての awk をゼロから書き、既存スクリプト (`cyc5_summary.py`) の窓の慣例 (`WARM<=t<=WARM+MEAS`) を流用しなかった。結果が仮説どおりに分かれたため検算を省略し、ファイルにも保存しなかった (指示側の問題ではない) |
| **カメラレディの判断** | 本文と整合させるなら `--window` の値 (7–11% / 19–42%) に差し替える。ウォームアップ中の需要は HPA が追従し切っていない過渡値で、§2 の「必要台数 = HPA が到達した台数」の定義とも合わないため、計測窓のみが筋。**未決 (ユーザ判断待ち)** |
| 探索方法に至った経緯 | (前セッションの記録、`fose2026-draft.md`「前セッションの未保存の計算・判断」A1–A4) ① 片側だけ動かす探索では checkout+email (email×1.06) 以外に解なし → 「frontend+checkout は少し動かせば解消」を削除 ② 両側・0.30–3.00 の探索では全 6 組に解あり → 「解が存在しない」は誤りと判明し「事実上消せない」に ③ ±20% に限る探索は境界が恣意的 (ユーザ指摘) として撤回 ④ 最小ずらし (max\|k−1\|) に確定 = 現行。§5 の「28–48%」は片側探索の「解なし」より弱い主張に意図的に落としたもの |

### 3.7 §5 affinity の割合 (38.8 / 4.8 / 4.1 / 2.5 / 1.7%)

| 項目 | 値 |
|---|---|
| データ | `km2/experiments/results-edge-pairs.csv` (2026-09-08, `edge-pairs.sh` + `edge_pairs.py`: 各 Pod にエフェメラルコンテナ netshoot を入れ `ss -tin` を窓の前後で読み接続ごとに差分) |
| 条件 | ラベル `購入100_閲覧0` (buy(100) のみ、分離・全サービス 1 台固定・HPA 無し) |
| 計算 | `km2/experiments/edge_pair_shares.py` — ヘッダ込みバイト = ペイロード + 66 B × セグメント数、分母はサービス間エッジ 15 本の合計。エッジは両端から観測されるので片側のみ採用、IP 直指定 (k6) は除外 |
| 再現 | **一致** (2026-09-14 に同じ計算で TeX に記載) |

### 3.7b 計算を伴わない記述の根拠 (前セッションの記録より)

- **view が到達する 6 サービス** (§3): `km2/experiments/k6/checkout.js` の browse シナリオは `GET /product/{id}` のみ。`src/frontend/handlers.go` の productHandler が呼ぶのは catalog・currency・cart・reco・ad → frontend 込みで 6。shipping は /cart ページ (getShippingQuote) でしか呼ばれないので view では不到達
- **「10 サービス」** (§3): 公式 11 サービスから loadgenerator を除く (k6 で代替)。redis-cart はデータストアなので数えない
- **需要 = 利用率 × 台数** (§2, §5): HPA の利用率は Pod ごとの CPU 使用量 ÷ requests の平均なので、利用率 × 台数 = 合計 CPU ÷ 予約枠 = 「枠何台分」。必要台数 = ceil(需要 / 0.77)
- **飽和帯・基本帯とも平均で語らない** (§3.1): 取りこぼしや p50 は分布が歪む (ユーザ指示) → 本文は達成レートの平均±SD と「約 2 割上回った」のみ
- **fixed4 が HPA 無し 4 台固定であること**: `fixed4.log` 3, 6 行目「HPA無し・4台固定, 枠 req=150m一律/limits据置」で確認。ログ 1 行目の「HPA=70%/1-8台」は既定値の表示で実際には未使用

### 3.8 §1 先行研究の引用

- Wickramanayaka, N. N., Keppitiyagama, C. I., Thilakarathna, K.: Communication-Affinity Aware Colocation and Merging of Containers, Int. J. on Advances in ICT for Emerging Regions, 15(3), pp. 33–45, 2022. DOI 10.4038/icter.v15i3.7251 (Crossref で著者・ページを確認)
- affinity の定義 (カプセル化込み総バイト量) は原著 §III (p. 36)、58.5% は §V (p. 41)。抽出テキストは執筆時の scratchpad にのみ保存 (原著 PDF は journal.icter.org から再取得可)

## 4. 再現コマンド一覧

```sh
cd km2/experiments
python3 icter_affinity_summary.py          # §3  +2--4%
python3 edge_pair_shares.py                # §5  affinity 割合
cd summer2026
python3 fixed4_summary.py                  # §3.1 softirq 削減率・飽和帯スループット
python3 table1_mismatch.py                 # 表1
python3 requests_shift_search.py           # §5  5--9% / 28--48% (awk 原本の移植、一致。ただしウォームアップ込み)
python3 requests_shift_search.py --window  # §5  計測窓のみ版 7--11% / 19--42% (本文の記述と整合。カメラレディ候補)
python3 cyc5_summary.py                    # 参考: 需要の伸び・帰属方式の粒度損 [m]
```

Windows では `python3` を `py -3` に、日本語出力は `PYTHONIOENCODING=utf-8` を付ける。
