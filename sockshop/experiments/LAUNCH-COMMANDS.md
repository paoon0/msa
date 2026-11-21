# 実験の起動コマンド (Sock Shop)

実験を始めたときに**実際に打ったコマンドの原文**。索引 `EXPERIMENTS.md` の「再現コマンド」は読みやすく整えたもの、こちらは打った通りのもの。
2026-11-02 作成。10-17〜10-26 の分は Claude Code のセッション記録 (会話ログ) から取り出した。

書き方:
- 時刻は日本時間。「起動」はコマンドを打った時刻、「START」はログ冒頭行の時刻。
- 起動のあとに付けた確認用のコマンド (`; tail ...`、`sleep 20; head ...` など) は省いた。省いたところは `…` と書いた。それ以外は打った通り。
- 同じ実験を何度か起動したとき、止めたとき、起動しようとして実行されなかったときも載せ、どうなったかを「結果」に書く。
- 設定を書いていないものは、その時点のスクリプトの既定値で動いている (値はログの冒頭行に出る)。

---

## probe-cpu (枠決めの予備測定、試し)

- 起動 2026-10-17 16:11 / 最初の点 16:11:25。結果: 実行。ログ `probe-cpu.log`

```sh
bash /home/mizuki/ダウンロード/msa/sockshop/experiments/probe-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/probe-cpu.log 2>&1
```

## 初回 ρ のスモーク (試し、出力は残っていない)

2 回起動。1 回目 (2026-10-19 02:22、前面で実行) はユーザが拒否したので実行していない。2 回目 (02:26、背景) は実行したが、出力を一時フォルダ (scratchpad) に書いたため残っていない。

```sh
# 2 回目 2026-10-19 02:26 (実行、出力は消えた)
S=/tmp/claude-1000/-home-mizuki--------msa/f19a71cf-0131-4423-8285-543cfa375857/scratchpad; rm -f $S/smoke-mix*; POINTS="b10v50" CYCLES=1 WARM=20 MEAS=60 PREWARM=30 CSV=$S/smoke-mix.csv bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > $S/smoke-stdout.txt 2>&1 …
```

## ρ 初回 (results-mix-cpu、置換 → mix-cpu2b)

- 起動 2026-10-19 02:40 / START 02:40:04。設定は当時の既定値 (1 台・15 点・4 サイクル)。結果: 実行。ログ `results-mix-cpu.log`

```sh
bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-mix-cpu.txt 2>&1
```

## probe10 / probe10b (readinessProbe と Java の慣らし、試し)

- probe10: 起動 2026-10-19 14:45 / START 14:45:30。probe10b (接続設定 B′ を入れた再試験): 起動 15:21 / START 15:21:17。結果: どちらも実行。ログ `probe10.log`, `probe10b.log`

```sh
bash /home/mizuki/ダウンロード/msa/sockshop/experiments/probe-warmup-test.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/probe10-stdout.txt 2>&1
TAG=probe10b bash /home/mizuki/ダウンロード/msa/sockshop/experiments/probe-warmup-test.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/probe10b-stdout.txt 2>&1
```

## ρ 測り直しの早すぎた起動 (中止、データなし)

- 起動 2026-10-19 15:48。ユーザは「測りなおそう。他に考えなければいけないことは？」と相談していたのに、私が既定値を 6 サイクル・慣らし 300 s に変えて起動してしまった。15:49 に「止めて」の指示で止め、出力 (`results-mix-cpu2.log`, `stdout-mix-cpu2.txt`) は消した。測定点は 1 つも終わっていない。
- 同じコマンドの前に、スクリプトの既定値の書き換え (`sed -i ...`) とそのコミットをしている (省略)。

```sh
CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/results-mix-cpu2.csv nohup bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-mix-cpu2.txt 2>&1 &
```

## 耐久試験 (stress、試し)

1 サイクル目と、2〜3 サイクル目を分けて起動した。2〜3 サイクル目は「1 サイクル目が終わるのを待ってから、スクリプトを差し替えて続きを流す」小さなスクリプト (`chain-stress.sh`、一時フォルダに置いた) で起動した。実行中のスクリプトを書き換えないため。

- 1 サイクル目: 起動 2026-10-20 01:46 / START 01:46:47。ログ `results-stress.log`、標準出力 `stdout-stress.txt`
- 2〜3 サイクル目: 起動 01:48 (待機) / START 03:28:47、DONE 06:52:55。同じログに追記、標準出力 `stdout-stress-c23.txt`

```sh
# 1 サイクル目 (2026-10-20 01:46)
nohup bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-stress.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-stress.txt 2>&1 &

# 2〜3 サイクル目 (01:48)。差し替え後の measure-stress.sh は CYCLE_FROM を足したもの (今の measure-stress.sh と同じ)
nohup bash $SP/chain-stress.sh > /dev/null 2>&1 &
# chain-stress.sh の中身 ($SP = 一時フォルダ):
#   D=/home/mizuki/ダウンロード/msa/sockshop/experiments
#   until grep -q "SS-STRESS DONE" $D/stdout-stress.txt; do sleep 30; done
#   mv $SP/measure-stress.new $D/measure-stress.sh
#   CYCLES=2 CYCLE_FROM=2 bash $D/measure-stress.sh > $D/stdout-stress-c23.txt 2>&1
```

## smoke-mix2b / smoke-mix2b-corner (格子の角の試し)

- smoke-mix2b: 起動 2026-10-20 16:10 / START 16:10:53。smoke-mix2b-corner: 起動 17:13 / START 17:13:50。結果: どちらも実行。ログ `smoke-mix2b.log`, `smoke-mix2b-corner.log`

```sh
cd /home/mizuki/ダウンロード/msa/sockshop/experiments; POINTS="b48 v240 b48v240" REPLICAS="1 2" CYCLES=1 ORDER=asc CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/smoke-mix2b.csv nohup bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-smoke-mix2b.txt 2>&1 &
cd /home/mizuki/ダウンロード/msa/sockshop/experiments; POINTS="b48v160 b32v240" REPLICAS="1" CYCLES=1 ORDER=asc CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/smoke-mix2b-corner.csv nohup bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-smoke-mix2b-corner.txt 2>&1 &
```

## ρ 本測定 (mix-cpu2b、本番)

- 起動 2026-10-20 17:38 / START 17:38:04、DONE 10-21 10:42:15。設定はスクリプトの既定値 (15 点 × 1 台/2 台 × 6 サイクル、慣らし b20v100 300 s、利用者 200 人、冷却待ち 70℃、点の後 60 s 休み、PRE_VUS 50 / MAX_VUS 400)。結果: 実行 (cyc2 × 2 台は再起動で壊れ、下の取り直しと差し替え)。ログ `results-mix-cpu2b.log`

```sh
cd /home/mizuki/ダウンロード/msa/sockshop/experiments; … nohup bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-mix-cpu2b.txt 2>&1 &
```

(`…` の部分は、起動前の確認 `pgrep -af measure- | grep -v pgrep; ls results-mix-cpu2b* 2>/dev/null`。)

## mix-cpu2b-redo2 (2 台・2 サイクル目の取り直し、本番)

- 起動 2026-10-26 15:22 / START 15:22:26、DONE 16:47:33。ユーザの「実験初めていいよ」を受けて起動。結果: 実行。ログ `results-mix-cpu2b-redo2.log`

```sh
REPLICAS=2 CYCLES=1 CYCLE_START=2 CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/results-mix-cpu2b-redo2.csv bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-mix-cpu2b-redo2.txt 2>&1
```

## smoke-ss-times (時刻の表・生の記録を入れた measure-mix-cpu.sh のスモーク、試し)

- 2026-11-07 16:04 起動 (START 16:04:49)。結果: **中止** (ユーザ「いやストップ、まだ確認が足りていない」、16:16 に Claude が停止。1 台の 1 点目の後の休憩中、k6 は走っていなかった)。ユーザ指示「OB と同様に SS でも、mesure-mix の実験結果をたどれるようにして計測をし直す」。スクリプト変更 (未コミット): `measure-mix-cpu.sh` (区間をログに出す・生の記録 range vector・`-times.csv`/`-raw.csv`、既定 CSV を results-mix-cpu3b.csv に)、`../k6/sockshop.js` (集計に k6_start_ms / k6_warmup_s / k6_summary_ms)。本番と同じ WARM 60 / MEAS 180 / 慣らし 300 s で、3 点 (購入のみ b16・閲覧のみ v240・重い角 b48v240) × 1 台/2 台 × 1 サイクル。見るもの: 余裕が両方正、生の記録、series の新形式、取りこぼし。

```sh
POINTS="b16 v240 b48v240" CYCLES=1 CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/smoke-ss-times-20261107.csv bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/stdout-smoke-ss-times-20261107.txt 2>&1; echo "exit=$?"
```

## smoke-ss-times2 (スモーク 2 回目、試し)

- 2026-11-07 16:40 起動 (START 16:40:33、版の行 commit=c52e224 dirty=0)。結果: 実行 (DONE 17:27:48、exit 0)。ユーザ「全てやって構わない」(アヌビス点検の 6 項目)。スクリプトはコミット c52e224 の版 (閲覧の失敗率の分母・t_end+15 s 待ち・版の記録を追加)。中身は 1 回目と同じ 3 点 × 1 台・2 台 × 1 サイクル、本番と同じ WARM 60 / MEAS 180 / 慣らし 300 s。見るもの: 6 点すべてで余裕が両端とも正、START に commit/dirty=0、browse_reqs と閲覧の失敗率が 0〜1 の割合、生の記録、取りこぼし。

```sh
POINTS="b16 v240 b48v240" CYCLES=1 CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/smoke-ss-times2-20261107.csv bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/stdout-smoke-ss-times2-20261107.txt 2>&1; echo "exit=$?"
```

## mix-cpu3b (ρ 本測定の取り直し、本番)

- 2026-11-07 17:28 起動 (START 17:28:20、版の行 commit=c52e224 dirty=0)。結果: **実行 (DONE 2026-11-08 11:06:10、exit=0、180/180 点)**。ユーザ「スモークが機能していれば、実験を回しておいて」「始まったら、終了予定時刻も記載しておいて」(smoke-ss-times2 の確認後)。スクリプトはコミット c52e224 の版。設定は旧 mix-cpu2b と同じ既定値 (15 点 × 1 台・2 台 × 6 サイクル、WARM 60 / MEAS 180 / 慣らし 300 s、休憩 60 s、冷却 70℃)。旧 mix-cpu2b (+ redo2) とは別ファイルで、混ぜない。
- **終了予定: 11/08 11:20 ごろ** (1 点約 5.5 分 × 180 点 + 慣らし約 7 分 × 12 ブロック ≈ 17.9 時間。スモーク 2 回目の実測から)。

```sh
CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/results-mix-cpu3b.csv bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-mix-cpu.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/stdout-mix-cpu3b.txt 2>&1; echo "exit=$?"
```

## smoke-edge-ss (通信量の測定のスモーク)

- 2026-11-10 15:40 起動 (START 15:40:35、版の行 commit=c52e224 dirty=2 = 新しい 2 ファイルが未コミット)。結果: **やり直し要 (スクリプトの不具合で停止)**。パケットの記録 (15:45:13〜15:45:53、40 s) と k6 (取りこぼし 0、失敗 0) は終わったが、引数なしの `wait` が `exec > >(tee)` のプロセス置換を待ち続けて止まった。16:30 に Claude が止め (k6 は終わっていて負荷は無し)、録れた pcap を手で集計した (`edge_pairs_ss.py` を同じ引数で実行、時刻の表の 1 行も手で書いた)。k6 の Pod の IP が対応表に無く front-end → k6 の応答 18.5 MB が other になっていた。直したもの: PID を名指しで wait、k6 の IP を対応表に足す。ユーザ「基準の負荷で通信の太さを調べて」。新しいスクリプト `edge-traffic-ss.sh` + `edge_pairs_ss.py` (未コミット) の動作確認。基準 b32v160 × 1 回、MEAS 60 s、慣らし 60 s。見るもの: 全 Pod でエフェメラルコンテナが起動するか、pcap が録れるか、録った区間が k6 の窓の内側か、取りこぼし。

```sh
REPEATS=1 MEAS=60 PREWARM=60 CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/smoke-edge-ss-20261110.csv PCAP_DIR=/tmp/claude-1000/-home-mizuki--------msa/79ed5039-ad0e-4c07-9dc8-15de8c3cc2cf/scratchpad/pcap-smoke-edge-ss bash /home/mizuki/ダウンロード/msa/sockshop/experiments/edge-traffic-ss.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/stdout-smoke-edge-ss-20261110.txt 2>&1; echo "exit=$?"
```

## smoke-hpa-arm1 (HPA 下の同居、アーム 1 と分離のスモーク)

- 2026-11-10 18:12 起動 (START 18:12:51、版の行 commit=c52e224 dirty=4 = 新しいファイルが未コミット)。結果: **中止** (ユーザ「一回止めていいよ」、18:38 に Claude が停止。2 点目 cyc1 normal b32v160 の k6 の途中で、k6 の Job と HPA を消した)。測れたのは 1 点 (cyc1 normal b16v160) だけ: Java のサービスが暴走して増えた (shipping・queue-master が上限 12 台、carts 6、orders 5〜8、Go の payment・user は 2 台)。ユーザ「一旦アーム1と分離でのスモークを3さいくるほどしてほしい」。新しいスクリプト (未コミット): `hpa-pair-ss.sh` (OB の pdist-k3 と同じ手順の SS 版)、`_write_hpapoint_ss.py`、`make_rightsize_ss.py` → `rightsize-ss-k3.csv` (基準 b32v160 で 3 台 = mix-cpu3b の 1 台の CPU ÷ 1.5。基準と台数は提案のままで、ユーザの最終確認はまだ)、`../variants/make_group.py` → `../variants/arm1/buygroup.yaml` (購入型 6 つを 1 Pod、ポートを 8081〜8086 に変え、呼び出しは Service 名のまま = 方式 B)。
- 設定: アーム normal / arm1 (サイクルごとに順番を回す)、点 b48 / b32v160 / b16v160 / b48v240 (サイクル × アームごとにシャッフル)、3 サイクル、WARM 180 / MEAS 240 s、開始 1 台、HPA 70% コンテナ別 1〜12 台 増 30 s / 減 60 s (pdist-k3 と同じ)、慣らし 300 s (b20v100、HPA 無し)、冷却 70℃、休憩 60 s。見込み約 5 時間。

```sh
CYCLES=3 CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/smoke-hpa-arm1-20261110.csv bash /home/mizuki/ダウンロード/msa/sockshop/experiments/hpa-pair-ss.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/stdout-smoke-hpa-arm1-20261110.txt 2>&1; echo "exit=$?"
```

## smoke-hpa-arm1-ready180 (案 3: Java を 180 秒 Ready にしない、1 点ずつ)

- 2026-11-10 18:55 起動 (START 18:55:36、版の行 commit=c52e224 dirty=4、java_ready_delay=180 を確認)。結果: **実行 (DONE 19:35:46、exit 0、2/2 点)**。分離: carts 2 [2〜5]・orders 2 [2〜4]・queue-master 2 [1〜2] は暴走が収まったが shipping は 12 [5〜12]。アーム 1: buygroup 5 [5〜12]。shipping は (1) 最初の Pod が負荷開始 47 s で 327% → 1→5 台、(2) 新しい Pod が Ready になった直後 (t≈250 s) に再び 250〜360% → 5→8→12 台 (Ready の後の跳ね上がりは案 3 では除けない)。取りこぼし 0・失敗 0。Pending は Pod の作成中 (FailedScheduling のイベントは無し)。ユーザ「一回それでやってみたい」(案 3 = 新しく立った Java の Pod を温まるまで Ready にしない)。smoke-hpa-arm1 (中止) で Java の台数が暴走した対策の試し。`hpa-pair-ss.sh` に `JAVA_READY_DELAY` を足した (未コミット。Java 4 つ carts / orders / shipping / queue-master の readinessProbe の initialDelaySeconds を 10 → 180 s、マニフェストは変えず apply の後に書き換え)。点は暴走した b16v160 だけ、分離とアーム 1 を 1 サイクル。見るもの: 台数が暴走しないか、Ready の後にまた跳ねないか、取りこぼし・遅延。見込み約 40 分。

```sh
JAVA_READY_DELAY=180 POINTS="b16v160" CYCLES=1 CSV=/home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/smoke-hpa-arm1-ready180-20261110.csv bash /home/mizuki/ダウンロード/msa/sockshop/experiments/hpa-pair-ss.sh > /home/mizuki/ダウンロード/msa/sockshop/experiments/smoke/stdout-smoke-hpa-arm1-ready180-20261110.txt 2>&1; echo "exit=$?"
```
