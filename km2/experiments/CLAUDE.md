# km2/experiments — Claude 向け運用ガイド

このフォルダで作業するときに、毎回同じことを調べ直さないためのメモ。
人向けの索引(実験名→スクリプト→CSV)は `README.md`、夏休み以降の日付付き索引は `summer2026/EXPERIMENTS.md`。
研究の結論や経緯は `.claude/memory/`(= `~/.claude/projects/.../memory/` と同一内容)にある。**ここには結論を書かない**(結論は memory、手順はここ)。

## フォルダの見取り図(2026-09-18 に平置きから整理)

| フォルダ | 時期 | 役割 | 現役? |
|---|---|---|---|
| `shared/` | — | 全実験共通の負荷マニフェスト `loadgen-csv.yaml`(locust headless)/`loadgen-csv-fail.yaml`(失敗も採取) | 現役 |
| `softirq/` | 2026-06〜07 | 分離 vs 部分集約 vs 全部入りの softirq/req 用量反応。`*-softirq.sh` はアームごとに1本 | 完了(参照のみ) |
| `hpa/` | 2026-07 | HPA 下の比較(Pod平均 vs コンテナ別、SCALE_ALL)、ボトルネック診断、fails の正体 | 完了(参照のみ) |
| `latency-breakdown/` | 2026-07〜09 | 「なぜ分離は頭打ちするか」レイテンシ分解・固定台数スイープ・3アーム固定4台 | 完了 |
| `k6/` | 2026-07〜09 | locust(閉ループ)の双安定を外すため k6 で開ループ化。容量の崖を測る | 現役(負荷生成の標準) |
| `perservice-cpu/` | 2026-08-18 | B測定: サービス別の利用率カーブ → 枠の適正化テーブルの元データ | 完了(論文の数値出所) |
| `rightsizing/` | 2026-10〜 | 枠適正化の第2版(クラス別測定・台数差c0・検証/較正)。手順書は `km2/approach/rightsizing-procedure.md` | 現役(未測定) |
| `summer2026/` | 2026-08〜09 | **主力**。適正化・決着実験・混合ワークロード・枠1/3・需要ズレ・固定4台。ドライバは `bundle-vs-loss2.sh` | 現役 |
| `edge-traffic/` | 2026-09-08〜10 | サービスペア単位の通信量実測(`ss -tin`)、ICTer 指標の再現 | 完了(論文の数値出所) |
| `archive-202606/` | 2026-06-15 | 初期 megapod 実験 CSV(リポジトリ直下にあったもの) | 保管 |

## 実行の作法

- **リポジトリ直下から** `bash km2/experiments/<dir>/<script>.sh` で実行する。スクリプト内部は `REPO=/home/mizuki/ダウンロード/msa` の絶対パス参照なので、**cwd に依存しない**が、ファイルを動かすときは参照側も書き換える(下記「移動するとき」)。
- 解析用 Python(`*_summary.py`, `*_shares.py`, `rightsize.py` 等)は **自分のフォルダで `python3 xxx.py`** か、`--src` でパスを渡す。`summer2026/rightsize.py` だけはリポジトリ直下からの相対パスが既定。
- 長時間実験は Bash の `run_in_background` で回し、待機は `until` ループで**完了時に1回だけ**報告する(Monitor ツールで進捗通知しない — ユーザの方針、memory `no-progress-monitors`)。
- 環境: MicroK8s 単一ノード(~16 vCPU)、namespace `exp`、Istio 無し(`inject:false`)、監視は kube-prometheus-stack(Prometheus は `prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090`)。到達方法は memory `monitoring-stack`。
- `km2/normal/CMD` には平文の認証情報がある。読まない・写さない。

## 出力ファイルの規約(summer2026 以降の「4点セット」)

`bundle-vs-loss2.sh` は 1 実験につき次の 4 ファイルを吐く。名前は環境変数 `CSV`/`TL`/`EV`/`LOG` で指定する(既定は `results-bundle-vs-loss2.*`)。

| ファイル | 中身 | 消してよいか |
|---|---|---|
| `results-<name>.csv` | 1測定=1行(アーム, レート, サイクル, rps, dropped_win, p50/p99, softirq, CPU時間, 予約枠 …) | **消さない** |
| `timeline-<name>.csv` | HPA 判断周期(15秒)ごとの利用率・台数の時系列 | **消さない** |
| `events-<name>.csv` | Pod の Pending/Ready 落ち/HPA 上限などのイベント | **消さない** |
| `<name>.log` | 実行ログ。**論文の数値出所から参照されているものがある**(`mix.log`, `fixed4.log` 等) | 原則消さない |

古い実験(`softirq/`, `hpa/`)は `results-*.csv` と `last-logs-*.txt`(直近の kubectl logs、再生成される)だけ。`last-logs-*` は消してよい。
**スモーク出力**(`summer2026/smoke/`)はどこからも参照されない使い捨て。

## アーム名 → マニフェストの対応

| アーム名 | 中身 | マニフェスト |
|---|---|---|
| `normal` | 分離(1 Pod 1 サービス)ベースライン | `km2/normal/*.yaml`(`kustomization`/`loadgenerator` は除く) |
| `mega` | 全 11 コンテナを 1 Pod に同居 | `km2/variants/all/all.yaml`(`MEGA_REDIS=shared` で redis を外出し) |
| `front3` / `f3perc` / `frontrecocatalog` | frontend+reco+catalog 同居(主力の束ねアーム)。`f3perc` はコンテナ別 HPA 版 | `km2/variants/frontrecocatalogcart/`。**ディレクトリ名に cart が付くが中身は 3 コンテナ**(旧計画の名残。cart は redis 分裂を避けるため別 Pod)。7 月の `softirq/results-front4.csv` は cart も同居していた当時の測定 |
| `frontcatalog` / `frontreco` / `frontcart` | frontend と 1 サービス同居 | `km2/variants/<name>/` (`frontcart` は summer2026 では `summer2026/manifests/frontcart.yaml` = redis 外出し版) |
| `frontrecocartcatalog` | 4 つ束ね | `summer2026/manifests/frontrecocartcatalog.yaml` |
| `frontemail` / `frontcheckout` / `checkoutemail` / `catalogcheckout` | 需要ズレ実験用のペア(2026-09-07) | `summer2026/manifests/<name>.yaml` |
| `outmail` / `outpy` / `paymail` | checkout に email/payment を同居(7月の用量反応) | `km2/variants/<name>/` |

束ねで操作しているレバーは各マニフェストの `*_SERVICE_ADDR` 環境変数(`localhost:port` か `Service名:port` か)。

## 主要スクリプトの環境変数(bundle-vs-loss2.sh)

`ARMS`(空白区切り)/`RATES`(購入型 周/s)/`BROWSE_RATE`(閲覧型 周/s)/`CYCLES`/`WARM`(既定180s)/`MEAS`(既定240s)/`PRESCALE`(開始台数)/`HPA_MIN`/`HPA_MAX`/`HPA_TARGET`(既定70)/`RIGHTSIZE=1`(枠を `rightsize-requests.csv` で置換)/`RS_SCALE`(枠の倍率、1/3 実験は 0.333)/`LIMIT_SCALE`(limits の倍率、**0=据え置きが正解**)/`FIXED_REPLICAS=N`(HPA 無し固定台数)/`UNIFORM_REQ_M`(requests 一律)/`PROBE_TIMEOUT`(readiness timeoutSeconds)/`MEGA_REDIS`/`CYC_START`(サイクル番号の通し)。
再現コマンドの実例は `summer2026/EXPERIMENTS.md` の各実験の「再現コマンド」に残してある。**新しい実験を回したら同じ形式で行を足す**。

## 指標の定義(名前が紛らわしいもの)

- **softirq/req(周)**: ノードの `mode="softirq"` CPU 秒 ÷ 周回数。通信コストの主指標(user モードはアプリのノイズが乗るので使わない)。cgroup の外にあるので **HPA には見えない**。
- **cgroup CPU** = `hpa_util × 枠 × 台数`。ノード CPU より分解能が一桁高い(2026-09-07 以降の主指標)。
- **dropped_win**: 計測窓の中だけの取りこぼし(k6 の `dropped_iterations` は全体累積なので窓に切り直したもの)。崩壊判定はこれを使う。
- **予約枠(reserved)** = Σ requests × 台数。HPA のつまみに依存するので主指標にしない(条件付き主張)。
- **1周** = k6 の checkout シナリオ 1 回(locust では 3 HTTP リクエスト)。負荷は「周/s」で表す。
- **計測窓**: ウォームアップ(既定 180s)を捨て、その後 `MEAS` 秒だけを集計。Prometheus の累積カウンタを窓の両端 2 点で引き算する(memory `exact-window-measurement`)。

## 数値を報告するときの決まり

- CSV から **Python で再計算してから**出す(memory `verify-numbers-python`)。平均だけでなく sd と n を添える。
- 論文に載った数値は `FOSE2026-TeX-UTF8/fose2026-data-provenance.md` に出所と再計算スクリプトがある。**論文の数値を触る前にそこを読む**。
- サイクル間ばらつき(2〜3%)より小さい差は「差がある」と言わない。

## 移動・改名するとき

絶対パス参照なので、ファイルを動かしたら次を grep して書き換える:
`km2/experiments/**/*.sh`, `**/*.py`, `**/*.md`、`km2/approach/*.md`、`FOSE2026-TeX-UTF8/*.md`、`.claude/memory/*.md`、`~/.claude/projects/-home-mizuki--------msa/memory/*.md`、ルートの `CLAUDE.md`。
検証は `grep -rnoE 'km2/experiments/[^ ]+'` で列挙し、各パスが実在するか確認する(2026-09-18 の整理でやった手順)。

## 新しい実験を足すときのテンプレ

1. スクリプトは既存の `bundle-vs-loss2.sh` のつまみで済むならスクリプトを増やさない(環境変数で回す)。
2. 出力名は `results-<短い名前>.csv` + 4点セット。`smoke-` 接頭辞はスモーク用(`summer2026/smoke/` へ)。
3. `summer2026/EXPERIMENTS.md` の表に「呼び名・日付・内容・CSV・時系列・ログ」と再現コマンドを足す。
4. 解析結果は `analysis-<名前>.md` に書き、結論は memory に要約する(ここには書かない)。
5. 論文で使う数値になったら `fose2026-data-provenance.md` に出所を足す。
