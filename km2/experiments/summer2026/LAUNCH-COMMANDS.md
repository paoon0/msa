# 実験の起動コマンド (Online Boutique)

実験を始めたときに**実際に打ったコマンドの原文**。索引 `EXPERIMENTS.md` の「再現」欄は読みやすく整えたもの、こちらは打った通りのもの。
2026-11-02 作成。2026-10-06〜10-19 の分は Claude Code のセッション記録 (会話ログ) から取り出した。それより前の実験は記録が無いので載せていない。

書き方:
- 時刻は日本時間。「起動」はコマンドを打った時刻、「START」はログ冒頭行の時刻。
- 起動のあとに付けた確認用のコマンド (`; tail ...`、`; grep -c ...`、`; echo exit=$?`) は省いた。省いたところは `…` と書いた。それ以外は打った通り。
- 「作業場所」は、コマンドに `cd` が無いときに、その時点でシェルがいた場所。
- 同じ実験を何度か起動したときは全部載せ、どれが実際にデータを残したかを「結果」に書く。

---

## lbcheck (gRPC 振り分けなしの偏り確認、試し)

- 起動 2026-10-06 13:09 / START 13:09:57。結果: 実行。ログ `smoke/lbcheck.log`

```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS=normal RATES="200 300" CYCLES=1 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 WARM=90 MEAS=120 CSV=smoke/results-lbcheck.csv TL=smoke/timeline-lbcheck.csv EV=smoke/events-lbcheck.csv LOG=smoke/lbcheck.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
```

## lbfix (振り分けあり GRPC_LB=1、試し)

3 回起動。2 回目と 3 回目は、前の出力を消してから取り直している。**データを残したのは 3 回目** (ログの START 2026-10-07 06:32:34)。

```sh
# 1 回目 2026-10-07 06:15
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS=normal RATES="200 300" CYCLES=1 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 WARM=90 MEAS=120 GRPC_LB=1 CSV=smoke/results-lbfix.csv TL=smoke/timeline-lbfix.csv EV=smoke/events-lbfix.csv LOG=smoke/lbfix.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
# 2 回目 2026-10-07 06:22 (cd なし)
rm -f smoke/results-lbfix.csv smoke/timeline-lbfix.csv smoke/events-lbfix.csv smoke/lbfix.log && ARMS=normal RATES="200 300" CYCLES=1 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 WARM=90 MEAS=120 GRPC_LB=1 CSV=smoke/results-lbfix.csv TL=smoke/timeline-lbfix.csv EV=smoke/events-lbfix.csv LOG=smoke/lbfix.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
# 3 回目 2026-10-07 06:32 (実行)
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && rm -f smoke/results-lbfix.csv smoke/timeline-lbfix.csv smoke/events-lbfix.csv smoke/lbfix.log && ARMS=normal RATES="200 300" CYCLES=1 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 WARM=90 MEAS=120 GRPC_LB=1 CSV=smoke/results-lbfix.csv TL=smoke/timeline-lbfix.csv EV=smoke/events-lbfix.csv LOG=smoke/lbfix.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
```

## lbctl (対照 GRPC_LB=2、試し)

- 起動 2026-10-07 06:47 / START 06:47:48。結果: 実行。ログ `smoke/lbctl.log`

```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS=normal RATES="200 300" CYCLES=1 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 WARM=90 MEAS=120 GRPC_LB=2 CSV=smoke/results-lbctl.csv TL=smoke/timeline-lbctl.csv EV=smoke/events-lbctl.csv LOG=smoke/lbctl.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
```

## lbarm0 / lbarm1 (front3・mega で振り分けなし/あり、試し)

- 起動 2026-10-07 07:22 / START 07:22:02 (lbarm0)、07:40:48 (lbarm1)。作業場所 `km2/experiments/summer2026/`。結果: 実行。ログ `smoke/lbarm0.log`, `smoke/lbarm1.log`

```sh
for lb in 0 1; do ARMS="frontrecocatalog mega" MEGA_REDIS=shared RATES="200 300" CYCLES=1 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 WARM=90 MEAS=120 GRPC_LB=$lb CSV=smoke/results-lbarm$lb.csv TL=smoke/timeline-lbarm$lb.csv EV=smoke/events-lbarm$lb.csv LOG=smoke/lbarm$lb.log bash bundle-vs-loss2.sh > /dev/null 2>&1; echo "lb=$lb exit=$?"; done
```

## smoke-mix (混合負荷 CPU のスモーク、試し)

- 起動 2026-10-07 11:27 / START 11:27:09。結果: 実行。ログ `../rightsizing/smoke/smoke-mix.log`

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="b100 b100v150" REPLICAS="1 2" CYCLES=1 WARM=30 MEAS=90 PREWARM=60 CSV=km2/experiments/rightsizing/smoke/smoke-mix.csv bash km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1 …
```

## 混合負荷 CPU (results-mix-cpu、置換 → mix-cpu2)

- 起動 2026-10-07 11:45。設定はスクリプトの既定値。結果: 実行。ログ `../rightsizing/results-mix-cpu.log`

```sh
cd /home/mizuki/ダウンロード/msa && bash km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1 …
```

(2026-10-07 16:49 に、2 台・3 台固定の追加スモーク `smoke-ext-*` を起動しようとしたが、ユーザが拒否したので実行していない。)

## fixed4-lb / fixed4b-lb (固定 4 台・振り分けあり、本番 (参考))

2 回起動した。1 回目 (16:50、60 分待ってから 3 サイクル/6 サイクル) は 2 回目に置き換えた。**実行したのは 2 回目** (ログの START は fixed4-lb 17:50:00 cycles=4、fixed4b-lb 21:21:58 cycles=4 の 1 回ずつ)。作業場所 `km2/experiments/summer2026/`。

```sh
# 1 回目 2026-10-07 16:50 (置き換え、実行されていない)
echo "start-after $(date -d '+60 min' '+%H:%M')" && sleep 3600 && \
COMMON='ARMS="normal frontrecocatalog mega" WARM=90 MEAS=120 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 GRPC_LB=1' && \
eval "$COMMON RATES='150 200 250 300' CYCLES=3 CSV=\$PWD/results-fixed4-lb.csv TL=\$PWD/timeline-fixed4-lb.csv EV=\$PWD/events-fixed4-lb.csv LOG=\$PWD/fixed4-lb.log bash bundle-vs-loss2.sh >/dev/null 2>&1"; \
eval "$COMMON RATES='350 400 450' CYCLES=6 REST_ARM=60 REST_CYCLE=300 CSV=\$PWD/results-fixed4b-lb.csv TL=\$PWD/timeline-fixed4b-lb.csv EV=\$PWD/events-fixed4b-lb.csv LOG=\$PWD/fixed4b-lb.log bash bundle-vs-loss2.sh >/dev/null 2>&1"; \
eval "$COMMON RATES='350 400' CYCLES=6 CYC_START=7 REST_ARM=60 REST_CYCLE=300 CSV=\$PWD/results-fixed4b-lb.csv TL=\$PWD/timeline-fixed4b-lb.csv EV=\$PWD/events-fixed4b-lb.csv LOG=\$PWD/fixed4b-lb.log bash bundle-vs-loss2.sh >/dev/null 2>&1"; …

# 2 回目 2026-10-07 16:52 (実行。17:50 まで待ってから開始)
W=$(( $(date -d '17:50' +%s) - $(date +%s) )) && echo "start-at 17:50 (wait ${W}s)" && sleep $W && \
COMMON='ARMS="normal frontrecocatalog mega" WARM=90 MEAS=120 FIXED_REPLICAS=4 UNIFORM_REQ_M=150 PRESCALE=4 GRPC_LB=1' && \
eval "$COMMON RATES='150 200 250 300' CYCLES=4 CSV=\$PWD/results-fixed4-lb.csv TL=\$PWD/timeline-fixed4-lb.csv EV=\$PWD/events-fixed4-lb.csv LOG=\$PWD/fixed4-lb.log bash bundle-vs-loss2.sh >/dev/null 2>&1"; \
eval "$COMMON RATES='350 400 450' CYCLES=4 REST_ARM=60 REST_CYCLE=300 CSV=\$PWD/results-fixed4b-lb.csv TL=\$PWD/timeline-fixed4b-lb.csv EV=\$PWD/events-fixed4b-lb.csv LOG=\$PWD/fixed4b-lb.log bash bundle-vs-loss2.sh >/dev/null 2>&1"; …
```

## smoke-pairval (pairval のスモーク、試し)

- 起動 2026-10-08 02:01 / START 02:01:48。結果: 実行 (exit 0)。ログ `smoke/smoke-pairval.log`

```sh
cd /home/mizuki/ダウンロード/msa && D=$PWD/km2/experiments/summer2026 && rm -f $D/smoke/*smoke-pairval* && \
ARMS="normal pairsY2" CYCLES=1 RESET_EACH_POINT=1 POINTS="b100v100" STARTS="2" WARM=30 MEAS=60 \
RIGHTSIZE=1 RSTABLE=$PWD/km2/experiments/rightsizing/rightsize-pairval.csv RS_STRICT=1 CHECK_FRAMES=1 \
RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" \
LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" \
CSV=$D/smoke/results-smoke-pairval.csv TL=$D/smoke/timeline-smoke-pairval.csv EV=$D/smoke/events-smoke-pairval.csv LOG=$D/smoke/smoke-pairval.log \
timeout 1500 bash $D/bundle-vs-loss2.sh >/dev/null 2>&1 …
```

## pairval (同居ペアの台数予測の前向き検証、本番)

- 起動 2026-10-08 02:11。作業場所 リポジトリ直下 (`$PWD` = `/home/mizuki/ダウンロード/msa`)。結果: 実行。ログ `pairval.log`

```sh
D=$PWD/km2/experiments/summer2026 && \
ARMS="normal pairsX pairsY pairsY2" ROTATE_ARMS=1 CYCLES=3 REST_ARM=60 REST_CYCLE=300 \
RESET_EACH_POINT=1 POINTS="b100v0 b100v100 b100v150" STARTS="1 2" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 \
RIGHTSIZE=1 RSTABLE=$PWD/km2/experiments/rightsizing/rightsize-pairval.csv RS_STRICT=1 CHECK_FRAMES=1 \
RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" \
LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" \
WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=8 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 \
CSV=$D/results-pairval.csv TL=$D/timeline-pairval.csv EV=$D/events-pairval.csv LOG=$D/pairval.log \
bash $D/bundle-vs-loss2.sh >/dev/null 2>&1 …
```

## smoke-mix2 (mix-cpu2 の重い点のスモーク、試し)

- 起動 2026-10-09 17:57 / START 17:57:35。作業場所 リポジトリ直下。結果: 実行。ログ `smoke/smoke-mix2.log`

```sh
S=km2/experiments/summer2026/smoke && POINTS="v300 b25v300 b50v300" REPLICAS="1" CYCLES=1 WARM=30 MEAS=90 PREWARM=30 REST_POINT=10 COOL_TEMP=70 CSV=$S/smoke-mix2.csv bash km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1 …
```

## mix-cpu2 (ρ の測定、本番)

- 起動 2026-10-09 18:09。結果: 実行。ログ `../rightsizing/results-mix-cpu2.log`

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="v75 v150 v300 b25 b25v75 b25v150 b25v300 b50 b50v75 b50v150 b50v300 b75 b75v75 b75v150 b100 b100v75 b100v150" REPLICAS="1 2" CYCLES=6 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=km2/experiments/rightsizing/results-mix-cpu2.csv bash km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1 …
```

## smoke-pdist (pdist のスモーク、試し)

- 起動 2026-10-13 23:55 / START 23:55:03。結果: 実行。ログ `smoke/smoke-pdist.log`

```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS="pairsP1 pairsP2 pairsP3" CYCLES=1 RESET_EACH_POINT=1 POINTS="b50v300" STARTS="1" RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=30 MEAS=60 HPA_MIN=1 HPA_MAX=8 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=smoke/results-smoke-pdist.csv TL=smoke/timeline-smoke-pdist.csv EV=smoke/events-smoke-pdist.csv LOG=smoke/smoke-pdist.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
```

## pdist (P の近さと引きずり、本番)

- 起動 2026-10-14 00:11。結果: 実行。ログ `pdist.log`

```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS="normal pairsP1 pairsP2 pairsP3" ROTATE_ARMS=1 CYCLES=3 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300" STARTS="1 2" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=8 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=results-pdist.csv TL=timeline-pdist.csv EV=events-pdist.csv LOG=pdist.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
```

## smoke-pdist2 (pdist2 のスモーク、失敗)

- 起動 2026-10-15 13:28 / START 13:28:23。結果: **失敗**。実行中にドライバ `bundle-vs-loss2.sh` を書き換えたため、613 行目で構文エラーになり止まった。pdist2 はこのあと中止 (pdist-k3 に置き換え)。ログ `smoke/smoke-pdist2.log`

```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS="pairsQ1 pairsQ2 pairsQ3" CYCLES=1 RESET_EACH_POINT=1 POINTS="b50v300" STARTS="1" RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=30 MEAS=60 HPA_MIN=1 HPA_MAX=8 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=smoke/results-smoke-pdist2.csv TL=smoke/timeline-smoke-pdist2.csv EV=smoke/events-smoke-pdist2.csv LOG=smoke/smoke-pdist2.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
```

## smoke-pdistk3 (pdist-k3 のスモーク 開始 4 台、試し)

3 回起動。ログ `smoke/smoke-pdistk3.log` に START が 2 つある (13:43:45 = 全 7 アーム、14:00:46 = normal だけ)。13:43 の 1 回目はすぐ止めて、出力先 `smoke/stdout-pdistk3.txt` を足した 2 回目に置き換えた。13:43 の回は枠不一致 (ad 600m が limits 500m を超えて拒否) で全アーム中止 → 直してから 14:00 に normal だけ再確認。作業場所 `km2/experiments/summer2026/`。

```sh
# 1 回目 2026-10-15 13:43 (すぐ置き換え)
ARMS="normal pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3" CYCLES=1 RESET_EACH_POINT=1 POINTS="b50v300" STARTS="4" RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=60 MEAS=60 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=smoke/results-smoke-pdistk3.csv TL=smoke/timeline-smoke-pdistk3.csv EV=smoke/events-smoke-pdistk3.csv LOG=smoke/smoke-pdistk3.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
# 2 回目 2026-10-15 13:43 (実行。枠不一致で全アーム中止)
ARMS="normal pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3" CYCLES=1 RESET_EACH_POINT=1 POINTS="b50v300" STARTS="4" RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=60 MEAS=60 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=smoke/results-smoke-pdistk3.csv TL=smoke/timeline-smoke-pdistk3.csv EV=smoke/events-smoke-pdistk3.csv LOG=smoke/smoke-pdistk3.log bash bundle-vs-loss2.sh > smoke/stdout-pdistk3.txt 2>&1 …
# 3 回目 2026-10-15 14:00 (実行。枠を直したあと normal だけ)
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS="normal" CYCLES=1 RESET_EACH_POINT=1 POINTS="b50v300" STARTS="4" RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=60 MEAS=60 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=smoke/results-smoke-pdistk3.csv TL=smoke/timeline-smoke-pdistk3.csv EV=smoke/events-smoke-pdistk3.csv LOG=smoke/smoke-pdistk3.log bash bundle-vs-loss2.sh > smoke/stdout-pdistk3.txt 2>&1 …
```

## pdistk3n (pdist-k3 分離 開始 3/4 台、中止)

2 回起動、**実行したのは 2 回目** (ログの START 14:07:01 が 1 つ)。アヌビスの点検を待つため、ユーザ指示で 14:30 ごろに止めた (2 点だけ測れた。本集計に使わない)。作業場所 `km2/experiments/summer2026/`。

```sh
# 1 回目 2026-10-15 14:06 (置き換え)
ARMS="normal" CYCLES=12 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300" STARTS="3 4" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=results-pdistk3n.csv TL=timeline-pdistk3n.csv EV=events-pdistk3n.csv LOG=pdistk3n.log bash bundle-vs-loss2.sh > /dev/null 2>&1 …
# 2 回目 2026-10-15 14:07 (実行 → 14:30 ごろ中止)
ARMS="normal" CYCLES=12 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300" STARTS="3 4" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=results-pdistk3n.csv TL=timeline-pdistk3n.csv EV=events-pdistk3n.csv LOG=pdistk3n.log bash bundle-vs-loss2.sh > stdout-pdistk3n.txt 2>&1 …
```

## smoke-k3b (b100v200 開始 1 台 全 7 アームのスモーク、試し)

- 起動 2026-10-15 14:45 / START 14:45:16。結果: 実行。ログ `smoke/smoke-k3b.log`
- 同じコマンドの前に、計画書 `../rightsizing/plan-pdist-k3.md` に「追記 3」を書き足している (省略)。

```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026 && ARMS="normal pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3" CYCLES=1 RESET_EACH_POINT=1 POINTS="b100v200" STARTS="1" RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=60 MEAS=60 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=smoke/results-smoke-k3b.csv TL=smoke/timeline-smoke-k3b.csv EV=smoke/events-smoke-k3b.csv LOG=smoke/smoke-k3b.log nohup bash bundle-vs-loss2.sh > smoke/stdout-k3b.txt 2>&1 &
```

## pdistk3sep (pdist-k3 分離 12 サイクル、本番)

2 回起動、**実行したのは 2 回目** (ログの START 15:21:48)。1 回目は相対パスのまま背景で起動したため、作業場所が合わずに始まらなかった (この失敗から「背景で起動するときは絶対パス」の決まりを作った)。

```sh
# 1 回目 2026-10-15 15:20 (失敗、cd なし・相対パス)
ARMS="normal" CYCLES=12 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=../rightsizing/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=results-pdistk3sep.csv TL=timeline-pdistk3sep.csv EV=events-pdistk3sep.csv LOG=pdistk3sep.log bash bundle-vs-loss2.sh > stdout-pdistk3sep.txt 2>&1 …
# 2 回目 2026-10-15 15:21 (実行)
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; ARMS="normal" CYCLES=12 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=$S/results-pdistk3sep.csv TL=$S/timeline-pdistk3sep.csv EV=$S/events-pdistk3sep.csv LOG=$S/pdistk3sep.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3sep.txt 2>&1 …
```

## pdistk3pair (pdist-k3 同居 10 組、本番)

- 起動 2026-10-16 00:10。結果: 実行。ログ `pdistk3pair.log`

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; ARMS="pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3" ROTATE_ARMS=1 CYCLES=3 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=$S/results-pdistk3pair.csv TL=$S/timeline-pdistk3pair.csv EV=$S/events-pdistk3pair.csv LOG=$S/pdistk3pair.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3pair.txt 2>&1
```

## limit-coarse (OB の限界測定、試し)

- 起動 2026-10-19 23:59 / START 23:59:15、DONE 10-20 01:04:21。設定はスクリプト `../rightsizing/measure-limit.sh` の既定値 (購入 b100〜b300、閲覧 v300〜v1000、1 サイクル、取りこぼし 1% 超で打ち切り)。結果: 実行。ログ `../rightsizing/results-limit-coarse.log`

```sh
nohup bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-limit.sh > /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/stdout-limit-coarse.txt 2>&1 &
```

## smoke-times (時刻記録 -times.csv の動作確認スモーク、試し)

- 起動 2026-11-02 22:57 / START 22:57:26。Claude が起動 (ユーザ了承済み、exp の Sock Shop はスクリプトの deploy で消える了承も取得)。スクリプトはコミット `3edba80` 時点 (`measure-mix-cpu.sh`・`_write_mixpoint.py`・`../k6/checkout.js` は `2ee602a` の版、未コミット変更なし)。結果: 実行 (DONE 23:16:04、exit 0、4 点すべて回収)。ログ `../rightsizing/smoke/smoke-times-20261102.log`

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="b100 b100v150" REPLICAS="1 2" CYCLES=1 WARM=30 MEAS=90 PREWARM=60 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/smoke-times-20261102.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```

## smoke-prod (本番 mix-cpu2 と同じ設定のスモーク、試し)

- 起動 2026-11-03 00:46 / START 00:46:26。Claude が起動 (ユーザ指示「本番用のスモークを流して」)。設定は mix-cpu2 本番と同じ (WARM 60 / MEAS 180 / PREWARM 180 @b100 / REST_POINT 60 / COOL_TEMP 70 / limits 上書き既定 / GRPC_LB=1 / VU は既定 300・3000) で、点だけ 3 つに絞った。スクリプトは 2026-11-03 の未コミット変更 (10 秒系列 → 生の記録 `-raw.csv` と記録間の差 `-series.csv`) を含む版で、実機で回すのはこれが初めて。結果: 実行 (DONE 01:31:36、exit 0、6 点すべて回収)。ログ `../rightsizing/smoke/smoke-prod-20261103.log`

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="b100 b100v150 b50v300" REPLICAS="1 2" CYCLES=1 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/smoke-prod-20261103.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```

## mix-cpu3 (mix-cpu2 と同じ設定の取り直し、本番)

- 起動 2026-11-03 03:59 / START 03:59:41。Claude が起動 (ユーザ指示「流して」)。設定は mix-cpu2 本番の再現コマンドと同じで、違いは出力先 (`results-mix-cpu3.csv`) だけ。スクリプトはコミット e785dc3 の版 (時刻の表 `-times.csv`・生の記録 `-raw.csv`・記録間の差 `-series.csv` を書く)。VU は既定 300・3000。見込み約 20 時間。結果: 実行 (DONE 2026-11-03 23:34:43、exit 0、204 点すべて回収)

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="v75 v150 v300 b25 b25v75 b25v150 b25v300 b50 b50v75 b50v150 b50v300 b75 b75v75 b75v150 b100 b100v75 b100v150" REPLICAS="1 2" CYCLES=6 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/results-mix-cpu3.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```

## smoke-k3times (pdist-k3 用ドライバの時刻・内側区間の確認スモーク、試し)

- 2026-11-06。Claude が起動しようとした (ユーザ指示「スモークを回してほしい」) が、**ユーザが起動を拒否** (実行されていない。出力ファイルなし)。直後にユーザから質問 (ノード CPU・softirq の聞き直し) があったため。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; ARMS="normal" CYCLES=1 RESET_EACH_POINT=1 POINTS="b50v150" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=$O/smoke-k3times-20261106.csv TL=$O/timeline-smoke-k3times-20261106.csv EV=$O/events-smoke-k3times-20261106.csv LOG=$O/smoke-k3times-20261106.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3times-20261106.txt 2>&1; echo "exit=$?"
```

- 2026-11-06 04:01 に同じコマンドで起動し直した (ユーザ指示「スモークを」)。START 04:01:56。見るもの: `-times.csv` の余裕が両方正 (内側 220 s が k6 の窓に収まる)、`-raw.csv` が書けるか、周波数・温度、新しい枠 (`rightsize-pdist-k3-mc3.csv`) の枠検査。結果: 実行 (DONE 04:11:42、exit 0)。ログ `smoke/smoke-k3times-20261106.log`

## smoke-k3pair (pdist-k3 同居アームを新しい枠・新しい区間で 1 回ずつ、試し)

- 2026-11-06 08:18 起動 (START 08:18:15)。結果: 実行 (DONE 09:17:50、exit 0)。ユーザ指示「同居のスモークもしておいて」。6 アーム × b100v200 (いちばん重い配合) × 開始 1 台 × 1 回。窓は本走と同じ WARM 180 / MEAS 240。見るもの: 新しい枠 (`rightsize-pdist-k3-mc3.csv`) で同居 Pod が立つか (枠検査・start_ok)、`-times.csv` の余裕、`-raw.csv`、取りこぼし。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; ARMS="pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3" ROTATE_ARMS=1 CYCLES=1 RESET_EACH_POINT=1 POINTS="b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=$O/smoke-k3pair-20261106.csv TL=$O/timeline-smoke-k3pair-20261106.csv EV=$O/events-smoke-k3pair-20261106.csv LOG=$O/smoke-k3pair-20261106.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3pair-20261106.txt 2>&1; echo "exit=$?"
```


## pdistk3sep2 → pdistk3pair2 (pdist-k3 のやり直し、本番)

- 2026-11-06 09:19 起動 (分離の START 09:19:26)。結果: 分離は実行 (DONE 16:12:44、48/48)、同居も実行 (16:12:44〜11/07 02:48:34、72/72、exit 0)。ユーザ指示「それらが終わったら本走まで流しておいて構わない」(smoke-k3times / smoke-k3pair の確認後)。**スクリプトはコミット 68ef35c の版** (内側 220 秒の区間、予約枠も同じ区間、`-times.csv` / `-raw.csv`)。枠の表は `../rightsizing/rightsize-pdist-k3-mc3.csv` (mix-cpu3 由来)。旧 pdistk3sep / pdistk3pair (旧枠・240 秒) とは別ファイルで、混ぜない。
- 分離 48 回 (4 配合 × 12 サイクル) を流し、続けて同居 72 回 (6 組 × 4 配合 × 3 サイクル)。1 回約 9.8 分 (スモークの実測) から、**終わる予定: 分離 11/06 17:10 ごろ、同居 11/07 05:00 ごろ**。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing
ARMS="normal" CYCLES=12 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=$S/results-pdistk3sep2.csv TL=$S/timeline-pdistk3sep2.csv EV=$S/events-pdistk3sep2.csv LOG=$S/pdistk3sep2.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3sep2.txt 2>&1; echo "sep exit=$?"; ARMS="pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3" ROTATE_ARMS=1 CYCLES=3 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=180 MEAS=240 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=60 COOL_TEMP=70 CSV=$S/results-pdistk3pair2.csv TL=$S/timeline-pdistk3pair2.csv EV=$S/events-pdistk3pair2.csv LOG=$S/pdistk3pair2.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3pair2.txt 2>&1; echo "pair exit=$?"
```


## smoke-k3win (HPA の窓・慣らし・計測時間を変えたスモーク、試し)

- 2026-11-17 起動 (ユーザ指示「増設窓は90s、減少窓は30s、慣らしを300s、計測時間を300sとしてスモークを一旦してみてほしい」)。動機: pdistk3sep2 で計測窓の中に台数が変わった点が 48 点中 41 点 (payment が立ち上がりで増やしすぎ → 60 秒に 1 台ずつ減る途中を測っていた)。直前に namespace sn-test を削除 (ユーザ選択、予約 1.05 コアに戻した)。pdistk3sep2 のコマンドから変えたのは SU_WIN 30→90・SD_WIN 60→30・WARM 180→300・MEAS 240→300、POINTS を増やしすぎの大きい 2 配合に、CYCLES=1、出力先だけ。ドライバはコミット 68ef35c の版 (未変更)。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; ARMS="normal" CYCLES=1 RESET_EACH_POINT=1 POINTS="b100v0 b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=90 SD_WIN=30 COOL_TEMP=70 CSV=$O/smoke-k3win-20261117.csv TL=$O/timeline-smoke-k3win-20261117.csv EV=$O/events-smoke-k3win-20261117.csv LOG=$O/smoke-k3win-20261117.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3win-20261117.txt 2>&1; echo "exit=$?"
```
- 2026-11-17 15:09 起動、ログの START 15:09:53 (warm=300s meas=300s 様子見=増90s/減30s を確認。「開始2台」の表示は STARTS="1" で上書きされる既知の表示、pdistk3sep2 と同じ)。結果: 実行 (DONE 15:33:59、exit 0、2/2)

## smoke-k3su30 (増設窓だけ 30 秒に戻したスモーク、試し)

- 2026-11-17 起動 (ユーザ指示「次のスモークでは、増設窓30秒にしてほしい」→ 起動の確認に「今すぐ起動する」)。smoke-k3win から SU_WIN 90→30 だけ変更 (SD_WIN 30・WARM 300・MEAS 300 は同じ)。目的: 増設窓 90 秒で増やしすぎが減った代わりに境目のサービス (b100v200 の checkout) が 1 台少なく落ち着いた疑い → 増設窓の効果を切り分ける。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; ARMS="normal" CYCLES=1 RESET_EACH_POINT=1 POINTS="b100v0 b100v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc3.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 CSV=$O/smoke-k3su30-20261117.csv TL=$O/timeline-smoke-k3su30-20261117.csv EV=$O/events-smoke-k3su30-20261117.csv LOG=$O/smoke-k3su30-20261117.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3su30-20261117.txt 2>&1; echo "exit=$?"
```
- 2026-11-17 起動、ログの START 15:49:55 (warm=300s meas=300s 様子見=増30s/減30s を確認)。結果: 実行 (DONE 16:13:55、exit 0、2/2)

## smoke-pinfreq (周波数固定後の ρ 測定のスモーク、試し)

- 2026-11-17 起動 (ユーザ指示「ρは計測し直す形でいく。前回計測方法を改めた計測方法で計測したい」→ 進め方の確認に「先にスモーク (推奨)」)。CPU 周波数は 16:56:21 から固定 (ターボ無し、P 2.1 / E 1.5 GHz、`km2/experiments/shared/cpufreq.sh pin`、起動前に status で no_turbo=1 を確認)。mix-cpu3 本番のコマンドから POINTS を負荷の高い 4 点に、CYCLES=6→1、出力先だけ変更。スクリプトはコミット e785dc3 の版 (未変更)。見るもの: 1 台・2 台固定で取りこぼし (buy/view_dropped_win) と絞り (throttle_pct) が出ないか。

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="b100v150 b75v150 b25v300 v300" REPLICAS="1 2" CYCLES=1 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/smoke-pinfreq-20261117.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```
- 2026-11-17 16:58 起動、ログ `../rightsizing/smoke/smoke-pinfreq-20261117.log` の START 16:59:01。結果: **中止** (17:0x、ユーザ指示「先にそれを調べてほしい」= b25 の確認を先に。最初の慣らし負荷 (b100、180 s) の途中で止めた。残った Job k6load を削除。測定点は 0 点)

## smoke-pinfreq-b25 (周波数固定で「閲覧を足すと無関係なサービスの CPU が下がる」が消えるかのスモーク、試し)

- 2026-11-17 仕掛け → smoke-pinfreq の中止とともに**待ち合わせを止め、すぐ起動に変更** (下の 2 行目)。仕掛けの理由 (ユーザ指示「周波数が低いと逆転が起こりうるポイントもお願いしたい」「SSでの低負荷帯では…Dが変わらない、もしくは下がった現象…周波数を固定するのはそれが目的では？」)。related_work.md §8 の記録: OB は購入 25 で閲覧 0→300 にすると checkout/payment/shipping/email が −26〜−32% (mix-cpu2、周波数 2.30→3.08 GHz)。b25 / b25v150 / b25v300 を 1 台固定 × 1 サイクル。smoke-pinfreq の DONE をログで待ってから自動で起動する (同じ測定スクリプトを同時に 2 本走らせないため)。設定は mix-cpu3 本番と同じ。

```sh
until grep -q 'MEASURE-MIX-CPU DONE' /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/smoke-pinfreq-20261117.log 2>/dev/null; do sleep 30; done; cd /home/mizuki/ダウンロード/msa && POINTS="b25 b25v150 b25v300" REPLICAS="1" CYCLES=1 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/smoke-pinfreq-b25-20261117.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```
- 2026-11-17 すぐ起動に変更して起動 (コマンドは上の until 行を除いた部分と同じ)。ログ `../rightsizing/smoke/smoke-pinfreq-b25-20261117.log` の START 17:05:57。結果: 実行 (DONE 17:28:32、exit 0、3/3)

## smoke-pinfreq-hi + smoke-pinfreq-b25x3 (周波数固定後の残りのスモーク 2 本を続けて実行、試し)

- 2026-11-17 起動 (ユーザ指示「残りのスモークはやってくれてるんだっけ」→「やっておいて」)。周波数は固定のまま (起動前に status で no_turbo=1、cpu0 2100/2100、cpu8 1500/1500 を確認。Job なし)。1 本目 = 中止した smoke-pinfreq と同じ点 (高負荷 4 点 × 1・2 台、1 サイクル)、出力名だけ変更。2 本目 = smoke-pinfreq-b25 の確かめ直し (CYCLES=1→3、点の順番はスクリプト既定の ORDER=shuffle でサイクルごとにばらばら)。1 本目が終わってから 2 本目が始まる (同じ測定スクリプトを同時に走らせない)。スクリプトはコミット e785dc3 の版 (未変更)。

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="b100v150 b75v150 b25v300 v300" REPLICAS="1 2" CYCLES=1 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/smoke-pinfreq-hi-20261117.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit1=$?"; cd /home/mizuki/ダウンロード/msa && POINTS="b25 b25v150 b25v300" REPLICAS="1" CYCLES=3 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/smoke-pinfreq-b25x3-20261117.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit2=$?"
```
- 2026-11-17 21:38 起動、ログ `../rightsizing/smoke/smoke-pinfreq-hi-20261117.log` の START 21:38:40。結果: 実行 (1 本目 DONE 22:35:17、exit1=0、8/8。2 本目はログ `../rightsizing/smoke/smoke-pinfreq-b25x3-20261117.log` の START 22:35:17、DONE 23:43:01、exit2=0、9/9)

## mix-cpu4 (周波数固定での ρ の測り直し、本番)

- 2026-11-18 起動 (ユーザ指示「ρは計測し直す形でいく。前回計測方法を改めた計測方法で計測したい」→ スモーク 3 本 (smoke-pinfreq-b25 / -hi / -b25x3) の確認後「ρはそのまま計測し、一点を除外するとどうなるかは後で確かめる」「起動していい」)。CPU 周波数は 2026-11-17 16:56:21 から固定 (ターボ無し、P 2.1 / E 1.5 GHz、`km2/experiments/shared/cpufreq.sh pin`、起動直前に status で no_turbo=1・cpu0 2100/2100・cpu8 1500/1500 を確認、Job なし)。コマンドは mix-cpu3 本番と同じで、違いは出力先 (`results-mix-cpu4.csv`) だけ。スクリプトはコミット e785dc3 の版 (未変更)、`km2/normal/` と `km2/experiments/k6/` も mix-cpu3 から未変更。注意: smoke-pinfreq-hi で 1 台の b100v150 は購入の取りこぼし 248 (1.4%) で、`analyze_rho2.py` の除外の決まり (1% 超え) に掛かりうる → 除外の決まりはそのまま、b100v150 (1 台) あり/なしの ρ の比較は測り終えてから行う (ユーザ決定)。見込み約 20 時間。

```sh
cd /home/mizuki/ダウンロード/msa && POINTS="v75 v150 v300 b25 b25v75 b25v150 b25v300 b50 b50v75 b50v150 b50v300 b75 b75v75 b75v150 b100 b100v75 b100v150" REPLICAS="1 2" CYCLES=6 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/results-mix-cpu4.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```
- 2026-11-18 00:29 起動、ログ `../rightsizing/results-mix-cpu4.log` の START 00:29:19。結果: 実行 (DONE 2026-11-18 20:16:35、exit 0、204/204)

## smoke-k3cap (新しい枠 mc4 で容量が足りるかのスモーク)

- 2026-11-19 起動 (ユーザ指示「スモークは流して」)。目的: 周波数固定で作り直した枠 `../rightsizing/rightsize-pdist-k3-mc4.csv` で、重い配合 b75v200 / b50v300 の Pending 0・予約合計 ≤ 16 コア、b50v150 で checkout/shipping が 3 台に届くか、計測窓内の email の絞り、ad の起動時 CPU を見る。アームは分離と、前回本番で高負荷時の予約が最大だった pairsQ3。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3cap-20261119.txt; ARMS="normal pairsQ3" CYCLES=1 RESET_EACH_POINT=1 POINTS="b75v200 b50v300 b50v150" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc4.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 CSV=$O/smoke-k3cap-20261119.csv TL=$O/timeline-smoke-k3cap-20261119.csv EV=$O/events-smoke-k3cap-20261119.csv LOG=$O/smoke-k3cap-20261119.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3cap-20261119.txt 2>&1; echo "exit=$?"
```
- 2026-11-19 13:12:04 起動、ログ `smoke/smoke-k3cap-20261119.log` の START 13:12:04。起動前の周波数 `smoke/cpufreq-smoke-k3cap-20261119.txt` (no_turbo=1、P 2100 固定)。結果: 実行 (DONE 2026-11-19 14:23:26、exit 0、6/6)

## smoke-k3sd45 (減少窓 45 秒で reco の往復が止まるか)

- 2026-11-19 起動 (ユーザ指示「減少窓を45秒にしてみて」)。smoke-k3cap の normal b50v300 で reco が慣らし中に 1↔4 を往復したため、減少窓 (SD_WIN) だけ 30→45 s にして同じ点を 3 サイクル。他は smoke-k3cap と同じ。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3sd45-20261119.txt; ARMS="normal" CYCLES=3 RESET_EACH_POINT=1 POINTS="b50v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc4.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=45 COOL_TEMP=70 CSV=$O/smoke-k3sd45-20261119.csv TL=$O/timeline-smoke-k3sd45-20261119.csv EV=$O/events-smoke-k3sd45-20261119.csv LOG=$O/smoke-k3sd45-20261119.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3sd45-20261119.txt 2>&1; echo "exit=$?"
```
- 2026-11-19 14:35 起動、ログ `smoke/smoke-k3sd45-20261119.log` の START 14:35:02 (「減45s」を確認)。結果: 実行 (DONE 2026-11-19 15:13:56、exit 0、3/3)

## smoke-k3probe5 (reco のヘルスチェック待ち時間 1→5 秒で往復が止まるか)

- 2026-11-19 起動 (ユーザ指示「ヘルスチェックを伸ばそう / また、減少窓は30sに戻して」)。smoke-k3sd45 (減少窓 45 s) で reco の往復が 3/3 で止まらなかったため、減少窓を 30 s に戻し、`PROBE_TIMEOUT=5` (reco のコンテナだけ readiness/liveness の timeoutSeconds を 5 に) で同じ点を 3 サイクル。他は smoke-k3cap と同じ。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3probe5-20261119.txt; ARMS="normal" CYCLES=3 RESET_EACH_POINT=1 POINTS="b50v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc4.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 CSV=$O/smoke-k3probe5-20261119.csv TL=$O/timeline-smoke-k3probe5-20261119.csv EV=$O/events-smoke-k3probe5-20261119.csv LOG=$O/smoke-k3probe5-20261119.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3probe5-20261119.txt 2>&1; echo "exit=$?"
```
- 2026-11-19 16:00 起動、ログ `smoke/smoke-k3probe5-20261119.log` の START 16:00:41 (「減30s」「プローブ緩和: recommendationservice/server timeoutSeconds=5」を確認、Deployment の readinessProbe.timeoutSeconds=5 も確認)。結果: 実行 (DONE 2026-11-19 16:39:38、exit 0、3/3)

## smoke-k3f3 (3 つ同居 front3 = frontrecocatalog を新しい枠・本番設定で通す)

- 2026-11-20 起動 (ユーザ指示「スモークをしていいよ」)。2026-11-19 に本番へ足すと決めた frontend+catalog+reco 同居アーム (`frontrecocatalog`) を、本番と同じ設定 (枠 mc4、LIMIT_OVERRIDE、PROBE_TIMEOUT=5、SU/SD 30 s、WARM/MEAS 300 s、開始 1 台) で、本番の 5 配合 × 1 サイクル。目的: Pending 0・予約 ≤ 容量・窓内の取りこぼし・台数の往復・枠検査の通過。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3f3-20261120.txt; ARMS="frontrecocatalog" CYCLES=1 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b75v200 b0v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc4.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 CSV=$O/smoke-k3f3-20261120.csv TL=$O/timeline-smoke-k3f3-20261120.csv EV=$O/events-smoke-k3f3-20261120.csv LOG=$O/smoke-k3f3-20261120.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3f3-20261120.txt 2>&1; echo "exit=$?"
```
- 2026-11-20 01:14 起動、ログ `smoke/smoke-k3f3-20261120.log` の START 01:14:09 (「点ごとリセット: points=[b100v0 b50v150 b50v300 b75v200 b0v300] starts=[1]」「プローブ緩和: frontend/recommendation timeoutSeconds=5」を確認。Deployment frontend の requests は server 906m / recommendation 584m / productcatalog 533m、limits は 3000m / 1600m / 3000m)。起動前の周波数 `smoke/cpufreq-smoke-k3f3-20261120.txt` (no_turbo=1)。結果: 実行 (DONE 2026-11-20 02:14:36、exit 0、5/5)。ただし b50v300 で p50 1784 ms (k6 → frontend の接続が 1 Pod に張り付き、その Pod の reco が頭打ち)。ユーザの条件「現在のスモークで問題がなく…なければ本実験に」を満たさないので、修正確認のスモークと本番は起動していない。

## noreuse-chk (k6 の接続を要求ごとに張り直すと frontend の CPU・ρ がどれだけ動くかの確認、試し)

- 2026-11-20 起動 (ユーザ指示「はりなおしでいい」→ 確認の測定の提案に「いいよ」)。smoke-k3f3 で k6 → frontend の負荷が 1 Pod に張り付いたため、k6 に `NO_REUSE=1` (noConnectionReuse、SN と同じ) を追加 (`../k6/checkout.js`・`../k6/k6-job.yaml`・`../rightsizing/measure-mix-cpu.sh`・`bundle-vs-loss2.sh`、既定 0 = 従来どおり)。mix-cpu4 本番と同じ測り方で、1 台固定 × 3 点 (b100 / v300 / b50v150) × 2 サイクルだけ張り直しで測り、mix-cpu4 の同じ点と比べる。判定の目安 (起動前に決定): frontend の D が基準の配合で 3% 以内かつ ρ の差 0.02 以内なら今の ρ と枠の表のまま。

```sh
bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/cpufreq-noreuse-chk-20261120.txt; cd /home/mizuki/ダウンロード/msa && NO_REUSE=1 POINTS="b100 v300 b50v150" REPLICAS="1" CYCLES=2 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/smoke/noreuse-chk-20261120.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```
- 2026-11-20 02:44 起動、ログ `../rightsizing/smoke/noreuse-chk-20261120.log` の START 02:44:21 (「no_reuse=1」を確認、k6 Job の環境変数 NO_REUSE=1 も確認)。起動前の周波数 `../rightsizing/smoke/cpufreq-noreuse-chk-20261120.txt` (no_turbo=1)。結果: 実行 (DONE 2026-11-20 03:29:31、exit 0、6/6)。判定の目安を満たさない (frontend の D が基準の配合で +11.8%) → 修正確認のスモークと本番は起動せず、ユーザに相談。

## smoke-k3close20 → close20-chk (③ ときどき張り直す: 要求 20 回に 1 回 Connection: close、試し)

- 2026-11-20 起動 (ユーザ指示「3も試してみたい」)。k6 に `CLOSE_EVERY=N` を追加 (`../k6/checkout.js` が VU ごとに要求 N 回に 1 回 `Connection: close` を付ける。`../k6/k6-job.yaml`・`bundle-vs-loss2.sh`・`../rightsizing/measure-mix-cpu.sh` から渡す。既定 0 = しない)。NO_REUSE は 0 (使わない)。
  - smoke-k3close20: 分離・3 つ同居・catalog+reco (pairsP1b) × b50v300 / b0v300 × 1 サイクル、本番設定。見るもの: frontend の負荷が Pod に均等に分かれるか (Prometheus の Pod 別 CPU)、待ち時間、ドライバ修正 A (PROBE_TIMEOUT が pairsP1b の reco にも当たり読み返しが 5/5) と B (browse_failed の列)。
  - 続けて close20-chk: noreuse-chk と同じ 1 台固定 × b100 / v300 / b50v150 × 2 サイクル、CLOSE_EVERY=20。mix-cpu4 と比べて frontend の CPU の増え方を見る (目安は noreuse-chk と同じ: 基準の配合で 3% 以内・ρ の差 0.02 以内)。

```sh
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3close20-20261120.txt; CLOSE_EVERY=20 ARMS="normal frontrecocatalog pairsP1b" CYCLES=1 RESET_EACH_POINT=1 POINTS="b50v300 b0v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc4.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 CSV=$O/smoke-k3close20-20261120.csv TL=$O/timeline-smoke-k3close20-20261120.csv EV=$O/events-smoke-k3close20-20261120.csv LOG=$O/smoke-k3close20-20261120.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3close20-20261120.txt 2>&1; echo "smoke exit=$?"; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $R/smoke/cpufreq-close20-chk-20261120.txt; cd /home/mizuki/ダウンロード/msa && CLOSE_EVERY=20 POINTS="b100 v300 b50v150" REPLICAS="1" CYCLES=2 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=$R/smoke/close20-chk-20261120.csv bash $R/measure-mix-cpu.sh > /dev/null 2>&1; echo "chk exit=$?"
```
- 2026-11-20 12:27 起動、ログ `smoke/smoke-k3close20-20261120.log` の START 12:27:21 (「no_reuse=0 close_every=20 probe_timeout=5 vus=600/4000 commit=c52e224+未コミットの変更あり」を確認、「プローブ緩和: recommendationservice/server … 読み返し 5/5」、k6 が閲覧 300 周/s で動き始めたことを確認)。結果: 実行 (smoke DONE 13:41:25 exit 0、6/6 点。close20-chk は START 13:41:25「close_every=20」/ DONE 14:26:34 exit 0、6/6)。frontend の Pod 別 CPU が均等 (分離 b50v300 で 624/596/594/580m)、3 つ同居の b50v300 p50 12 ms、frontend の CPU は mix-cpu4 比 b50v150 +0.3%・粗い ρ 0.331→0.314 で目安内。本番は未起動 (ユーザ判断待ち)。

## mix-cpu5 (ときどき張り直す CLOSE_EVERY=20 での ρ の測り直し、本番)

- 2026-11-20 ユーザ指示「ρをもう一度計測したい」→「6回で。」(③ CLOSE_EVERY=20 の採用は同日決定)。mix-cpu4 と同じ設定で、違いは CLOSE_EVERY=20 と出力先だけ。起動前の確認: 周波数固定 (no_turbo=1、cpu0 2100/2100、`../rightsizing/cpufreq-mix-cpu5-start.txt`)、他の実験・Job なし。スクリプトはコミット c52e224 + 未コミットの変更 (CLOSE_EVERY 追加)。k6 の版は Job の中で確認: k6 v2.4.0 (commit dd9395906d)、イメージ docker.io/grafana/k6@sha256:3d8e5c7f1d53ec59408c2ffbd9943602a0985ffcbd4a2430ec00f3ffca89796e (k6-job.yaml は latest 指定のまま)。解析では CPU を生カウンタ (-raw.csv) の差分から出す予定 (rate() の端の過小対策)。見込み約 20 時間。

```
bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/cpufreq-mix-cpu5-start.txt; cd /home/mizuki/ダウンロード/msa && CLOSE_EVERY=20 POINTS="v75 v150 v300 b25 b25v75 b25v150 b25v300 b50 b50v75 b50v150 b50v300 b75 b75v75 b75v150 b100 b100v75 b100v150" REPLICAS="1 2" CYCLES=6 WARM=60 MEAS=180 PREWARM=180 REST_POINT=60 COOL_TEMP=70 COOL_MAX_WAIT=600 CSV=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/results-mix-cpu5.csv bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-mix-cpu.sh > /dev/null 2>&1; echo "exit=$?"
```

- 2026-11-20 16:51:04 起動、ログ `../rightsizing/results-mix-cpu5.log` の START 16:51:04 (「no_reuse=0 close_every=20 … cycles=6」を確認、k6 Pod の環境変数 CLOSE_EVERY=20 を確認)。結果: **実行 (完了)**、ログの DONE 2026-11-21 12:38:28、exit 0、6 サイクル × 2 台 × 17 点 = 204 点すべて回収 (summary 未回収 0)。

## smoke-k3mc5 (新しい枠 mc5 での容量スモーク、試し)

- 2026-11-21 ユーザ指示「スモークしておいてくれる？」。目的: 本番 pdistk3sep3 / pdistk3pair3 の前に、新しい枠 (`../rightsizing/rightsize-pdist-k3-mc5.csv`) + CLOSE_EVERY=20 + k6 固定 (v2.4.0 digest) で、予約の大きい 2 配合が載るかを見る。分離・3 つ同居 × b75v200 / b50v300 × 1 サイクル (4 点、約 50 分)。見るもの: 載らない Pod (FailedScheduling) 0 件、枠不一致 0、email の絞り、b75v200 の予約、k6 imageID の一致、START 行の sha256 / no_turbo。ドライバは 11/21 の修正 (imageID・FailedScheduling・周波数の止め役・sha256) を含む初回の実機。

```
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3mc5-20261121.txt; CLOSE_EVERY=20 RESET_EACH_POINT=1 POINTS="b75v200 b50v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc5.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 ARMS="normal frontrecocatalog" CYCLES=1 CSV=$O/smoke-k3mc5-20261121.csv TL=$O/timeline-smoke-k3mc5-20261121.csv EV=$O/events-smoke-k3mc5-20261121.csv LOG=$O/smoke-k3mc5-20261121.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3mc5-20261121.txt 2>&1; echo "smoke exit=$?"
```

- 2026-11-21 16:37 起動、ログ `smoke/smoke-k3mc5-20261121.log` の START 16:37:41 (close_every=20、k6=sha256:3d8e5c7f…、probe_timeout=5、枠検査 OK、最初の点の k6 imageID が指定と一致を確認)。結果: **実行 (完了)**、DONE 17:27:18、exit 0、4/4 点。載らない Pod 0 件・取りこぼし 0・枠検査 OK・start_ok/frames_ok 全 1・k6 imageID 4/4 一致。

## smoke-k3ev (イベント回収の修正の確認、試し)

- 2026-11-21 ユーザ指示「スモークしておいて。問題なければ本番で」。目的: 計測窓の始まりにもイベントを取って uid で重ねる修正 (bundle-vs-loss2.sh / collect_events.py の EARLY) の初回の実機。ウォームアップ中の台数を増やすイベント (above target) が events に残るかを見る。分離・3 つ同居 × b75v200 × 1 サイクル (2 点、約 25 分)。他の設定は本番 / smoke-k3mc5 と同じ。

```
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3ev-20261121.txt; CLOSE_EVERY=20 RESET_EACH_POINT=1 POINTS="b75v200" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc5.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 ARMS="normal frontrecocatalog" CYCLES=1 CSV=$O/smoke-k3ev-20261121.csv TL=$O/timeline-smoke-k3ev-20261121.csv EV=$O/events-smoke-k3ev-20261121.csv LOG=$O/smoke-k3ev-20261121.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3ev-20261121.txt 2>&1; echo "smoke exit=$?"
```
- 2026-11-21 18:49 起動、ログ `smoke/smoke-k3ev-20261121.log` の START 18:49:14。結果: **実行 (完了)**、DONE 19:15:47、exit 0、2/2 点。events にウォームアップ中の台数を増やすイベントが残った (分離 20 件・同居 15 件、最初は t_run から数十秒)、重複行 0、timeline の台数の変化 18 系列すべてが events と一致 (events の方が多いのは負荷停止後の縮小)。載らない Pod 0 件、取りこぼし (窓) 0、k6 imageID 2/2 一致、枠検査 OK。→ ユーザ指示どおり本番へ。


## pdistk3sep3 → pdistk3pair3 (本番 3 回目)

- 2026-11-21 ユーザ指示「スモークしておいて。問題なければ本番で」。smoke-k3ev 合格を受けて起動。分離 normal × 5 配合 × 12 サイクル → ペア 6 種 + 3 つ同居 frontrecocatalog × 5 配合 × 3 サイクル (ROTATE_ARMS=1)、約 33 時間。枠 `../rightsizing/rightsize-pdist-k3-mc5.csv`、k6 v2.4.0 digest 固定、CLOSE_EVERY=20、イベントの早め回収あり。ドライバは未コミット (START 行に sha256)。

```
S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $S/cpufreq-pdistk3sep3-start.txt; CLOSE_EVERY=20 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b75v200 b0v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc5.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 ARMS="normal" CYCLES=12 CSV=$S/results-pdistk3sep3.csv TL=$S/timeline-pdistk3sep3.csv EV=$S/events-pdistk3sep3.csv LOG=$S/pdistk3sep3.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3sep3.txt 2>&1; echo "sep exit=$?"; CLOSE_EVERY=20 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b75v200 b0v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc5.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 ARMS="pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3 frontrecocatalog" ROTATE_ARMS=1 CYCLES=3 CSV=$S/results-pdistk3pair3.csv TL=$S/timeline-pdistk3pair3.csv EV=$S/events-pdistk3pair3.csv LOG=$S/pdistk3pair3.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3pair3.txt 2>&1; echo "pair exit=$?"
```
- 2026-11-21 19:16 起動、ログ `pdistk3sep3.log` の START 19:16:30 (close_every=20、k6 digest 一致、枠検査 OK を最初の点で確認)。結果: pdistk3sep3 は**実行 (完了)** DONE 2026-11-22 06:58:10、60/60 点。pdistk3pair3 は続けて自動で開始し**実行 (完了)** DONE 2026-11-23 03:53:05、105/105 点、両方 exit 0

## edge-pairs-mc5 (affinity を ρ と同じ条件で測り直す、試し)

- 2026-11-23 ユーザ指示「affinityを基準の配合で計り直せない？」→「枠はρを計測した時の枠でいい。配合はb50v50のみで。張り直しは最新のもので。」。9/08 の `../edge-traffic/results-edge-pairs.csv` (購入100_閲覧0) を、mix-cpu5 と同じ条件 (分離 1 台固定・HPA 無し・requests は km2/normal のマニフェストのまま・limits 上書き frontend/catalog 3000m・ad 1000m・GRPC_LB=1・CLOSE_EVERY=20・k6 v2.4.0 digest 固定・周波数固定) で測り直す。`../edge-traffic/edge-pairs.sh` を 11/23 に修正 (k6 の場所、CLOSE_EVERY/NO_REUSE の埋め込み、limits 上書き・gRPC 振り分け・Terminating 待ち)。既定値は 9/08 と同じ。注意: exp の Deployment/HPA を全部消して立て直す。見込み約 10〜15 分。解析は `python3 edge_pair_shares.py results-edge-pairs-mc5.csv 購入50_閲覧50` (edge-traffic/ で)。

```sh
cd /home/mizuki/ダウンロード/msa && E=/home/mizuki/ダウンロード/msa/km2/experiments/edge-traffic; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $E/cpufreq-edgepairs-mc5-start.txt; CASES="50:50" WARM=60 MEAS=180 CLOSE_EVERY=20 GRPC_LB=1 LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" CSV=$E/results-edge-pairs-mc5.csv LOG=$E/edge-pairs-mc5.log bash $E/edge-pairs.sh > /dev/null 2>&1; echo "exit=$?"
```

- 2026-11-23 ユーザ「大丈夫。やっといて」(b50v50 で確定) → 23:39 に私が起動、ログ `../edge-traffic/edge-pairs-mc5.log` の START 23:39:07 (close_every=20・grpc_lb=1・limits 上書きを確認)。結果: **実行 (完了)**、DONE 23:44:17、exit 0、15 エッジすべて両端から観測。
