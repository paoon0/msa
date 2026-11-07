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
