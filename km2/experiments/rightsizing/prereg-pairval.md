# 事前登録: 同居ペアの台数・損の予測の前向き検証 (pairval)

作成 2026-10-08。**このファイルと下に列挙した予測ファイルは、同居実験 (pairval) の結果を見る前にコミットする。** 以後、ここに書いた判定・採点の規則は変えない。変えたくなったら、変更前の規則での結果も必ず併記する。

## 1. 問い

分離構成 (1 Pod 1 サービス) の測定だけから、2 つのサービスを 1 Pod に同居させたときに、HPA が決める台数と「損」(予約枠 = requests × 台数 の増加) を予測できるか。特に、buy:view の配合が変わったときに台数が揃ったままか、ずれて損が出るか。

## 2. 予測の入力と方法 (固定)

- 入力: `results-mix-cpu.csv` (2026-10-07 実測。分離・HPA 無し・全サービス 1 台固定 / 2 台固定 × 配合 10 点 × 3 サイクル、GRPC_LB=1)。
- 予測スクリプト: `predict_pairs.py` (このコミットの版)。実行コマンド:
  ```sh
  python3 predict_pairs.py --theta 0.50 --ref-buy 50 --ref-view 100 --grid-buy 50 100 --grid-view 0 50 100 150 \
      --delta-k 1 --out-pred predictions-pairval-K1.csv --out-req rightsize-pairval.csv
  python3 predict_pairs.py --theta 0.50 --ref-buy 50 --ref-view 100 --grid-buy 50 100 --grid-view 0 50 100 150 \
      --delta-k 2 --out-pred predictions-pairval-K2.csv --out-req rightsize-pairval.csv
  ```
- 枠: `rightsize-pairval.csv` (θ = 0.50、基準ミックス buy 50 / view 100、全 10 サービス + redis-cart 50m)。
- 需要モデル: 台数 n = 1, 2 それぞれ、buy>0 の 8 点で D = c + β·buy + ν·view。n ≥ 3 は外挿で「不明」。
- 不確かさ: 共通のずれ δ_common と、サービス固有のずれ δ_indiv を ±K·δ で振る 27 通り。**主評価 K = 1、副評価 K = 2。**
- 判定: 27 通りすべてで損 = 0 → 「損なし」、すべてで損 > 0 → 「損あり」、それ以外・外挿・振動 → 「不明」。
- `bistable` 列 = 開始台数 1 と 2 で中心値 (n_s, n_t, n_st) が違うセル。**副次評価に回す。**

### 基準ミックスと θ の選び方 (開示事項)

同居実験の結果を一切見ていない段階で、6 基準 × 5 θ の 30 案を測定済み 8 点の上で走査し (`pairval_design_search.py`、結果 `pairval-design-search.txt`)、確定率が高く、かつ「開始 1 台で損あり」が確定する案として b50v100 θ = 0.50 を選んだ。

**この選び方そのものを限界として報告する:**
- 主張の範囲は「θ = 0.50 という、しきい値まで余裕の大きい使い方での検証」。
- 確定セルの約 6 割は、全員 1 台の自明なセル (アヌビス 2026-10-08 の検算)。
- 損ありの確定セル数は K に敏感 (K = 0 → 80、1 → 28、1.5 → 16、2 → 9)。

## 3. 検証実験の設計 (固定)

- 構成 (アーム): `normal` (分離) / `pairsX` / `pairsY` / `pairsY2`。1 アームに互いに素なペアを同時に束ねる。

| アーム | ペア | 新規性 |
|---|---|---|
| pairsX | catalog+reco, checkout+payment, shipping+email | catalog+reco と checkout+payment は台数の問いとしては新規 (注記付き)、shipping+email は新規 |
| pairsY | catalog+payment, shipping+reco, front+checkout | front+checkout は 2026-09 に同じ問いで結果を見ているので**新規に数えない** |
| pairsY2 | catalog+email, payment+reco, front+shipping | すべて新規 |

- 点: buy 100 × view {0, 100, 150} (`b100v0` = 損ありの主検証、`b100v150` = 単純な規則と判定式が食い違う識別セル、`b100v100` = 双安定が多く副次)。
- 開始台数: 1 と 2。**点ごとにリセット**する: HPA を消す → 開始台数に scale → 全 Ready → k6 開始 → 直後に HPA 作成。
- 3 サイクル。点 × 開始台数の順番はサイクルごとにシャッフルし、アームの順番はサイクルごとに回す。
- WARM 180 s / MEAS 240 s。HPA は目標 70%、コンテナ別、SU_WIN 30 s / SD_WIN 60 s (K8s 既定の縮み 300 s とは違うことを明記)、min 1 / max 8。
- limits は測定時と同じにする: frontend / catalog = 3000m、ad = 1000m (同居 Pod 内のコンテナも)。他はマニフェストのまま。GRPC_LB = 1。

## 4. 採点の規則 (固定)

1. **実測の台数** = 計測窓内の時系列 (sample_hpa.py、15 s 間隔) の current_replicas の最頻値。最頻値の占める割合が 80% 未満、または窓内で台数が変わったら「不安定」とし、**外れとして数える** (後から除外しない)。
2. **無効**: dropped_win > 0、Pending > 0、Ready 落ち、枠不一致 (frames_ok = no)、開始台数不一致 (start_ok = no) の点は無効。無効のセル (ペア, 点, 開始台数) は本走の後に 1 回だけ再実行する。再実行も無効なら、そのセルは「無効」として件数を報告し、正解率の分母から外す。
3. **実測の損** = n_st × (r_s + r_t) − (n_s × r_s + n_t × r_t)。n_st は同居アームでのその Pod の台数、n_s と n_t は**同じサイクル・同じ点・同じ開始台数の normal アーム**での台数。損 > 0 →「損あり」、= 0 →「損なし」、< 0 →「得」(別の区分。予測が損なしなら外れ)。
4. **採点単位**: (ペア, 点, 開始台数) ごとに 3 サイクルの多数決。同数なら外れ。サイクル単位の結果も併記する。
5. **主指標**: (a) (n_s, n_t, n_st) の 3 つ組の完全一致率、(b) 損の区分の一致率。どちらも予測が「不明」でない、bistable = no のセルが対象。Wilson 95% 区間を付ける。
6. **対照の単純な規則** (同じセルで正解率を出す):
   - R1 (クラス規則): {checkout, payment, shipping, email} (buy だけで呼ばれる側) と、それ以外のサービスの組で、buy = 100 なら「損あり」、それ以外は「損なし」。
   - R2 (利用率比の規則): その点の 1 台時利用率 u1 (予測表の u1_s, u1_t) の比 max/min が 1.2 を超えたら「損あり」、それ以外は「損なし」。
7. **合格条件** (主評価 K = 1、新規ペアのみ):
   - (i) 自明でない確定セル (中心値が全員 1 台でないもの) で、損の区分の一致率が 90% 以上。
   - (ii) R1 または R2 と判定式の予測が食い違うセル (識別セル) で、判定式が過半数で正しい。
   - 両方を満たして「合格」。K = 2 の結果、front+checkout、bistable セル、不明セルの実測の内訳は副次として全部出す。

## 5. 外れたときの診断 (事前に決めておく。外れを救済する目的では使わない)

- (i) normal アームで実測した各サービスの CPU と、実測の台数での予測 D を比べる (当日のずれ、κ の相手台数への依存)。
- (ii) 時系列の hpa_util から HPA の判定則を再生し、実測の台数が出るか (シミュレーション自体の正しさ)。
- (iii) 同居 Pod 内の各コンテナの CPU と、分離時の CPU を比べる (同居による通信 CPU の減少)。
- (iv) 同じ窓で、metrics-server の値 (hpa_util × r × n) と Prometheus の rate が一致するか。
- (v) (推奨・余裕があれば) 損ありの新規ペア 1〜2 組を単独で束ねたアームで 1 サイクル回し、同時に束ねた場合と台数が同じか。

## 6. 固定するファイル (このコミット)

`results-mix-cpu.csv` / `-series.csv` / `.log`、`measure-mix-cpu.sh`、`predict_pairs.py`、`predictions-pairval-K1.csv`、`predictions-pairval-K2.csv`、`rightsize-pairval.csv`、`pairval_design_search.py`、`pairval-design-search.txt`、このファイル。

ドライバの改修 (`summer2026/bundle-vs-loss2.sh` ほか) と同居マニフェスト (`summer2026/manifests/pairs{X,Y,Y2}.yaml`) は、本走の前に別のコミットで固定する。

**追記 (2026-10-08 02:15、本走開始の直前):**
- スモーク (`summer2026/smoke/*smoke-pairval*`、normal と pairsY2 を1点ずつ) で、枠検査 OK、limits の上書き、点ごとのリセットを確認した。start_ok が HPA 作成直後の空欄で 0 になる不具合があったので、空欄のときは ready_replicas で代用するよう `start_ok.py` を直した。
- 熱の影響を避けるため、アーム間 60 s・サイクル間 300 s の休憩を入れる (REST_ARM=60 REST_CYCLE=300)。
- **採点スクリプトは本走の開始後に書き、結果ファイルを開く前にコミットする** (予定より順番が遅れる。偽データで空回しして確認する)。
- スモークで adservice (Java) が負荷開始直後に利用率 291% まで跳ね、5〜6 台に増えた。ad は採点対象外だが、ノード負荷として記録する。

※ 旧既定 (b100v0, θ = 0.70) の `predictions-pairs.csv` / `rightsize3-requests.csv` も副次の比較用に同じコミットに入れる。

**追記 (2026-10-08、採点スクリプトのコミット時。本走の出力はまだ誰も開いていない):**
採点は `score_pairval.py` (偽データのテスト `test_score_pairval.py` は 28/28 OK) で、次のコマンドで行う:
```sh
python3 score_pairval.py --strict-browse --ready-ignore adservice              # 主評価 (K=1)
python3 score_pairval.py --strict-browse --ready-ignore adservice --pred predictions-pairval-K2.csv --out score-pairval-cells-K2.csv
```
§4 の文言で解釈が分かれる3点は、結果を見る前に次のように決めた:
- R1 の「組」= 片方だけが {checkout, payment, shipping, email} に属する組 (クラスをまたぐ組)。
- Ready 落ちの無効化は adservice を除く (ad は採点対象外で、負荷開始直後の跳ね上がりが既知)。他の Deployment の Ready 落ちは無効にする。
- 閲覧型の取りこぼし (browse_dropped_win > 0) も無効にする (負荷が流れていないため)。
- その他の細部 (窓 = t_rel ≥ WARM、台数の最頻値は Deployment 単位、Ready 落ちは timeline の ready_replicas の減少で検出、無効サイクルは票から外す) は score_pairval.py の docstring のとおり。
