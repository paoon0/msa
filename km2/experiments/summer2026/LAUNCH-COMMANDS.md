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

