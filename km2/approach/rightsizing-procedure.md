# 予約枠 (CPU requests) 適正化の手順 — 第2版 (2026-10-06)

修士論文で **Online Boutique と Sock Shop に同じ手順を当てる** ための標準手順。
FOSE2026 で使った第1版 (`summer2026/rightsize.py`、論文 §3.2 の「(c0 + 100 c1) / 0.7」) は論文の記録として変更しない。

スクリプト: `km2/experiments/rightsizing/`
- `measure-class-cpu.sh` — STEP 1/2 の測定 (クラス別 CPU カーブ + 台数差でアイドル分)
- `rightsize2.py` — STEP 3 (係数の推定と枠の計算)
- `calibrate.py` — STEP 4/5 (検証と較正)
- `additivity.py` — 加法性の確認 (クラス別の係数を足してよいか)

**2026-10-07 改訂** (修正項目 1〜7 を反映): 判定の言葉を「合格」から **採用条件 (i)・(ii)** に変更、設計利用率 θ を 0.70 → **0.66**、帯を 66〜74% → **64〜68%**、検証を PRESCALE=1 と 2 の両方で回す、慣らし負荷、過渡の除外と中央値、誤差をサイクル間ばらつきから、較正前の誤差だけを精度として報告、gRPC 振り分け (GRPC_LB=1) を全段で入れる。

---

## なぜ第2版が要るか (第1版の診断, 2026-10-06)

mix / mix2 の分離アーム (計測窓のみ、10サイクル) で第1版の予測を検証した結果:

| 問題 | 実測での現れ方 |
|---|---|
| buy だけで測った (クラスが1つ) | view を足すと CPU を 60〜80% 過小評価 |
| 1サイクル・6点・全範囲で1本の直線 | 設計点 buy100 での誤差は frontend +2.1 / catalog −4.4 / reco −4.3 / checkout +0.8 / cart +2.6 / email +11.6% (2026-10-06 レフェリー検算。当初書いた cart +10% は過渡が混ざった誤り) |
| 検証の段階がない | email は枠の過小推定で 78%。cart / checkout は起動直後の跳ね上がりで2台になり、HPA の非対称 (77%超で増、≤70%でないと減らない) で戻らなかった |
| c0 を切片から推定 | 台数が増えたときの予測 (とヒステリシス) が狂う |

要点: HPA は利用率 63〜77% (目標 70% ± 許容幅 10%) では台数を変えないので、**枠の誤差は ±10% より十分小さくなければならない**。第1版はその精度に届いていなかった。

---

## モデル

1台あたりの CPU:

```
CPU_s = c0_s + Σ_j a_sj × x_j
```

| 記号 | 意味 |
|---|---|
| c0_s | アイドル分。負荷ゼロでも Pod 1台ごとにかかる CPU [m] |
| a_sj | クラス j のリクエスト 1周/秒 あたりに、サービス s が使う CPU [m/(周/秒)] |
| x_j | その Pod 1台が担当するクラス j の負荷 [周/秒] |

枠: `r_s = U_ref,s / θ`。U_ref は基準ミックス (1台が担当する負荷 k_j の組) での1台時 CPU、θ = **0.66** (設計利用率)。

θ を HPA の目標 70% より低くする理由: HPA は利用率が 77% (70% × 1.1) を超えると台数を増やしますが、減らすのは「全台の需要を足して、1台少ない台数で割っても 70% 以下」になったときだけです。なので u1 が 70〜77% のサービスは、起動直後に一度2台になると1台に戻りません (同じ負荷でも、履歴によって1台にも2台にもなる)。u1 をこの帯から外して 64〜68% に置くのが θ = 0.66 です。

---

## 手順

### STEP 0: クラスと基準ミックスを決める (アプリごとに1回)

- **クラス** = 同じサービスを同じような割合で呼ぶリクエストのまとまり。負荷シナリオ (k6 スクリプト) か、アクセスログの URL 比率から決める。全体の数%しかない種類は近いクラスに混ぜる。
- **基準ミックス** = 「1台にどれだけ担当させるか」。Online Boutique は第1版と揃えて `buy=100`。
- 決めたら `measure-class-cpu.sh` の「アプリ固有の設定」の節 (SERVICES / STATEFUL / class_env) を書く。

### STEP 1: クラス別の CPU カーブを測る

- 分離構成・**全サービス1台固定・HPA 無し**・requests/limits はマニフェストのまま。
- クラスを **1つずつ** 流す (混ぜると、増えた CPU がどのクラスのせいか分からない)。
- 点は **設計点 k の周辺 (0.6k〜1.4k) に集める** + 低負荷を1点。**3サイクル以上**、サイクルごとに順番をシャッフルする。
- ウォームアップは CPU が落ち着くまで (既定 60s。JVM は長めに)。さらに **デプロイごとに慣らし負荷 180 秒** (PREWARM、buy 100) を流して結果を捨てる。
- gRPC の振り分け (GRPC_LB=1) を入れる。1台の点では振り分け先が1つなので結果は変わらないが、STEP 2 の2台点と、以後の実験の条件に揃える。
- スロットリング >5% の点と、取りこぼし (達成率 <97%) の点は解析で捨てる。

### STEP 2: アイドル分 c0 を台数差で測る

同じ負荷 (既定 buy=100) で 2台と1台を同じサイクル内で測り、`c0 = U(2台) − U(1台)`。測る順番はサイクルごとに入れ替える (奇数サイクルは2台が先、偶数は1台が先)。時間とともに CPU がずれても、差に入り込まないようにするため。
切片から推定すると、カーブの凹みで過大になる (第1版で email 16m だったものが、HPA 実験からの再推定では ≈0)。

### STEP 3: 係数を推定し、枠を計算する

```sh
python3 km2/experiments/rightsizing/rightsize2.py \
  --src km2/experiments/rightsizing/results-class-cpu.csv --ref buy=100
```

- U_ref は **設計点の周辺 (±40%) だけで当てはめた直線の、設計点での値**。
- 出力の `誤差%` (設計点での標準誤差) を見る。サイクルごとに設計点の値を出し、**サイクル間のばらつき ÷ √サイクル数** で出す (全点まとめた回帰の残差から出すと、同じサイクルの点どうしが似ている分だけ小さく出すぎる)。帯 64〜68% は 66% の ±3% (相対) なので、**2倍しても 3% 未満** でなければ STEP 1 のサイクルを足す。

### STEP 4: 検証 — 新しい枠で HPA を回し、採用条件 (i)・(ii) を満たすか

**開始台数 1台 (PRESCALE=1) と 2台 (PRESCALE=2) の両方で回す。** 片方だけだと、履歴で台数が決まる帯 (u1 70〜77%) に入っていても気づけない。

```sh
cd km2/experiments/summer2026
for P in 1 2; do
ARMS=normal RATES=100 BROWSE_RATE=0 CYCLES=3 RIGHTSIZE=1 PRESCALE=$P \
  RSTABLE=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/rightsize2-requests.csv \
  RS_SERVICES="frontend productcatalogservice recommendationservice cartservice checkoutservice currencyservice paymentservice shippingservice emailservice adservice" \
  CSV=../rightsizing/results-rs2-verify-p$P.csv TL=../rightsizing/timeline-rs2-verify-p$P.csv \
  EV=../rightsizing/events-rs2-verify-p$P.csv LOG=../rightsizing/rs2-verify-p$P.log \
  bash bundle-vs-loss2.sh
done
python3 ../rightsizing/calibrate.py \
  --timeline ../rightsizing/timeline-rs2-verify-p1.csv ../rightsizing/timeline-rs2-verify-p2.csv \
  --table ../rightsizing/rightsize2-requests.csv --out ../rightsizing/rightsize2-requests-cal1.csv
```

- `RS_SERVICES` は **全サービスを列挙する** (空にするとスクリプトの既定の4サービスに戻る)。
- **採用条件 (i)**: 1台時の利用率 u1 が **64〜68%**。u1 = 1台で担当したときの CPU ÷ 枠。計測窓のサンプルのうち、台数が変わってから 60 秒以内のものは捨て、サイクルごとに中央値を取り、サイクル間で平均する。
- **採用条件 (ii)**: 開始1台でも開始2台でも、計測窓の終わりに1台になっている。
- 両方満たしたサービスの枠を「採用」とする (「合格」という言葉は使わない)。

### STEP 5: 較正

採用条件を満たさないサービスだけ `枠 ← U1 / 0.66` (U1 = 1台時の実測 CPU) に置き換えた表を `calibrate.py --out` が書き出す。その表で STEP 4 をもう一度回し、**全サービスが採用条件 (i)・(ii) を満たしたら確定**。確定した表と、検証結果 (各サービスの u1 と終わりの台数) を記録に残す。

**較正と評価を分ける。** 手順の精度として報告するのは、`calibrate.py` が出す **較正前の誤差** (= rightsize2.py の予測 U_ref と STEP 4 の実測 U1 の差) だけ。較正後の表は STEP 4 の実測に合わせ込んだものなので、同じデータで誤差を測っても精度の証拠にならない。

### 加法性の確認 (クラスが2つ以上のとき)

モデルは「クラスごとの CPU を足せる」ことを前提にしている。STEP 1 の係数で、クラスを混ぜた実測 (mix 実験など) を予測して確かめる:

```sh
python3 km2/experiments/rightsizing/additivity.py --runs km2/experiments/summer2026/mix km2/experiments/summer2026/mix2 \
  --p50-max 20 --table km2/experiments/rightsizing/rightsize2-requests.csv
```

---

## 所要時間の目安 (Online Boutique、既定値)

| 段階 | 1点 | 1サイクル | 合計 |
|---|---|---|---|
| STEP 1+2 (buy 6点 + view 6点 + c0 の対 2点 + 慣らし 3回) | 約5分 | 約85分 | 3サイクルで約4.5時間 |
| STEP 4 (1点 × 3サイクル × 開始台数 2通り) | 約8分 | — | 約50分 / 1回 |

## 既存データでの試運転 (2026-10-06)

- `calibrate.py` に第1版の結果 (mix / mix2, buy=100, view=0) を通すと、cart 77.1% と email 78.3% が旧基準 (66〜74%) を外れ、frontend / reco / catalog / checkout は内側 (66.8〜71.5%) だった。**cart の 77.1% は2台化直後の過渡が混ざった誤り** (1台で落ち着いた値は 71.9%)。
- 2026-10-07 に過渡除去 (台数変化後 60s)・中央値・採用条件 (i)(ii) を入れた版で再実行 (mix は4サービス、mix2 は checkout/email。表ごとに当てた枠が違うので分けて通す): u1 = reco 66.7 / catalog 66.4 (採用条件 (i) を満たす)、frontend 71.3 / checkout 70.6 / cart 73.6 / email 78.0 (満たさない)。第1版は θ=0.70 で設計しているので、新しい帯 64〜68% から外れるのは当然。(ii) は PRESCALE=1 のデータしかないので未判定。
- `rightsize2.py --old-format` に第1版の元データを通すと、設計点の周辺だけで当てはめた値は reco 742→634m、currency 523→545m と動く。元データが1サイクル・6点しかないので、点の選び方次第で 10% 以上動く = STEP 1 をやり直す理由。

## Sock Shop に移すときの注意

- 状態を持つもの (各 DB、RabbitMQ) は STATEFUL に入れ、同居候補から外す。
- Java (Spring) のサービスは JIT と GC でカーブが曲がり、アイドル分も大きい → WARM を延ばし、STEP 2 の台数差を必ず取る。
- front-end (Node.js) は1プロセスがほぼ1コアで頭打ち → 設計点 k をその手前に置く。
- 注文は RabbitMQ 経由の非同期処理 → queue-master / shipping の CPU は負荷と時間がずれる。計測窓を長めにする。
- k6 シナリオは Sock Shop 用に書き直し、クラスごとに独立にレートを指定できるようにする (`class_env` で対応付け)。
