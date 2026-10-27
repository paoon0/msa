# 実験インデックス (sockshop/experiments/)

Sock Shop の実験の日付付き索引 (OB の `../../km2/experiments/summer2026/EXPERIMENTS.md` と同じ形)。2026-10-27 作成。
**パスはすべてこのファイル (`sockshop/experiments/`) から見た相対パス**。`../k6/` は `sockshop/k6/`、`../../km2/` はリポジトリ直下の `km2/`。
論文に書くこと (方法・限界・査読への備え) は `../../km2/approach/related_work.md` §9.5〜9.10 にある。

共通: namespace `exp`、マニフェスト `../normal/`、負荷は k6 (`../k6/sockshop.js`, `../k6/k6-job.yaml`)、HPA 無し。
**2026-10-19 に接続設定 B′** (k6 `noVUConnectionReuse`、orders `-Dhttp.keepAlive=false`) を入れた。それより前の測定 (probe-cpu, probe10, results-mix-cpu) は B′ 無し。

状態の意味: **本番** = 論文の数値に使う / **置換** = 後の測定で置き換えた (使わない) / **試し** = 設定確認・格子決め用。

| 呼び名 | 日付 | 状態 | 内容 | 結果 CSV | 時系列 | ログ・標準出力 | 解析 → 出力 |
|---|---|---|---|---|---|---|---|
| **枠決めの予備測定 (probe-cpu)** | 2026-10-17 | 試し | 1 台・枠は `../normal/` のまま。b5〜b40 (購入のみ)、v25〜v200 (閲覧のみ) の 8 点 × 1 回、WARM 60 / MEAS 120 s | `probe-cpu.csv` | なし | `probe-cpu.log` | なし (CSV を直接見た) |
| **readinessProbe 10 s と Java の慣らし (probe10)** | 2026-10-19 | 試し (方法節の根拠) | 立て直し → b24v120 を 1200 s、720 s 目にアプリ 8 つを 2 台へ。起動 → Ready の秒数、Ready 落ち、2 台目の分担。B′ 無し → **新 Pod に負荷が来ない問題を発見** | `probe10-cpu.csv`, `probe10-ready.csv` | (同左) | `probe10.log`, `probe10-stdout.txt`, `probe10-startup.txt`, `probe10-afterscale.txt`, `probe10-unhealthy.txt` | `analyze_probe10.py probe10-cpu.csv` → `analysis-probe10.txt` |
| **同 再試験 B′ (probe10b)** | 2026-10-19 | 試し (方法節の根拠) | probe10 と同じ手順を B′ を入れて再実行。2 台目の分担が均等になった | `probe10b-cpu.csv`, `probe10b-ready.csv` | (同左) | `probe10b.log`, `probe10b-stdout.txt`, `probe10b-startup.txt`, `probe10b-afterscale.txt`, `probe10b-unhealthy.txt` | `analyze_probe10.py probe10b-cpu.csv` → `analysis-probe10b.txt` |
| **ρ 初回 (results-mix-cpu)** | 2026-10-19 02:40〜07:44 | **置換** (mix-cpu2b へ) | 1 台・15 点 (b8〜b24 × v40〜v120) × 4 サイクル = 60 点。B′ 無し・点ごとに利用者登録。front-end ρ 0.262 | `results-mix-cpu.csv` | `results-mix-cpu-series.csv` | `results-mix-cpu.log`, `stdout-mix-cpu.txt` | `analyze_rho.py` → `analysis-rho.txt` |
| **耐久試験 (stress)** | 2026-10-20 01:46〜06:52 | 試し (格子の上限決め) | 1 台・段階的負荷 3 本 (購入 b40〜b100 / 閲覧 v150〜v400 / 混合 b26v130〜b40v200)、取りこぼし 1% 超で打ち切り、3 サイクル。全 57 点で 1% 以下 (限界に届かず)。front-end は約 1 コアで頭打ち | `results-stress.csv` (cycle 1〜3) | `results-stress-series.csv` | `results-stress.log` (2 回の起動を追記)、`stdout-stress.txt` (cyc1)、`stdout-stress-c23.txt` (cyc2〜3) | `../../km2/experiments/rightsizing/analyze_limit.py results-stress.csv` (購入・閲覧)。混合は手計算 → **混合の集計スクリプトは TODO** |
| **格子の角の試し (smoke-mix2b)** | 2026-10-20 16:10〜16:56 | 試し | b48, v240, b48v240 × 1 台・2 台 × 1 回。1 台の b48v240 で front-end が約 1.04 コアに張り付く (頭打ち) | `smoke-mix2b.csv` | `smoke-mix2b-series.csv` | `smoke-mix2b.log`, `stdout-smoke-mix2b.txt` | なし (related_work.md §9.8 に手で記録) |
| **同 隣の点 (smoke-mix2b-corner)** | 2026-10-20 17:13〜17:31 | 試し | b48v160, b32v240 × 1 台 × 1 回。頭打ちは無し | `smoke-mix2b-corner.csv` | `smoke-mix2b-corner-series.csv` | `smoke-mix2b-corner.log`, `stdout-smoke-mix2b-corner.txt` | なし (同上) |
| **ρ 本測定 (mix-cpu2b)** | 2026-10-20 17:38〜10-21 10:42 | **本番** (cyc2 × 2 台を除く) | B′ あり・15 点 (b16〜b48 × v80〜v240) × 1 台/2 台 × 6 サイクル。慣らし b20v100 300 s、利用者登録はサイクルに 1 回、冷却待ち 70℃、点の後 60 s 休み。**cyc2 × 2 台の 15 点は MicroK8s の自動再起動 (10-20 21:08 / 21:28) で壊れたので使わない** | `results-mix-cpu2b.csv` | `results-mix-cpu2b-series.csv` | `results-mix-cpu2b.log`, `stdout-mix-cpu2b.txt` | `analyze_rho_ss.py` → `analysis-rho-ss.txt` (下の取り直しと合わせて) |
| **同 cyc2 × 2 台の取り直し (mix-cpu2b-redo2)** | 2026-10-26 15:22〜16:47 | **本番** (上の cyc2 × 2 台と差し替え) | 2 台 × 15 点 × 1 サイクル、設定は mix-cpu2b と同じ。cycle 列は 2 として記録。取りこぼし 0・失敗 0・再起動 0。最初の点 b48 で購入側 (orders, shipping, queue-master) が他サイクルより高い (要確認) | `results-mix-cpu2b-redo2.csv` | `results-mix-cpu2b-redo2-series.csv` | `results-mix-cpu2b-redo2.log`, `stdout-mix-cpu2b-redo2.txt` | 同上。結果 front-end ρ 1 台 0.287 / 2 台 0.288 |

## 再現コマンド (`sockshop/experiments/` で実行)

```sh
# ρ 本測定 (mix-cpu2b)。既定値が本測定の設定
bash measure-mix-cpu.sh 2>&1 | tee stdout-mix-cpu2b.txt
# cyc2 × 2 台の取り直し
REPLICAS=2 CYCLES=1 CYCLE_START=2 CSV=$PWD/results-mix-cpu2b-redo2.csv bash measure-mix-cpu.sh 2>&1 | tee stdout-mix-cpu2b-redo2.txt
# 耐久試験 (1 サイクル目、続きは CYCLES=2 CYCLE_FROM=2)
bash measure-stress.sh 2>&1 | tee stdout-stress.txt
# 格子の角の試し
POINTS="b48 v240 b48v240" CYCLES=1 CSV=$PWD/smoke-mix2b.csv bash measure-mix-cpu.sh
# 解析
python3 analyze_rho_ss.py > analysis-rho-ss.txt
```

## 実験を足したら

この表に行を足す (呼び名・日付・状態・内容・CSV・時系列・ログ・解析)。パスはこのファイルから見た相対パスで省略せずに書き、書いたら実在を照合する (リポジトリ直下 `../../CLAUDE.md`「実験の記録」)。
