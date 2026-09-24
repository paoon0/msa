# km2/experiments — 実験スクリプト & 結果インデックス

このフォルダは修士研究「コンテナ集約(co-location)の資源効率」の**負荷実験一式**。
2026-09-18 にテーマ別フォルダへ整理した。この索引で「実験名 → スクリプト → 結果CSV → 何を見たか」を一覧する。
Claude 向けの運用ガイド(実行の作法・出力規約・アーム名対応・指標定義)は同じフォルダの `CLAUDE.md`。

## 実行時の共通事項
- スクリプトは**リポジトリ直下から** `bash km2/experiments/<dir>/xxx.sh` で実行(内部パスは絶対参照)。
- 出力(CSV/ログ)はスクリプトと同じフォルダに書かれる。
- 全部入りマニフェスト `all.yaml` だけは `km2/variants/all/all.yaml`(別フォルダ)を参照する。
- 束ねトポロジのマニフェストは `km2/variants/frontrecocatalogcart/`(別フォルダ)。
- ログの扱い: `*.log` のうち **論文の数値出所やスクリプト・memory から参照されるもの**(`edge-traffic/*.log`, `perservice-cpu/*.log`, `summer2026/*.log`)は生データなので消さない。それ以外の `last-logs-*.txt` 等は再生成されるので随時削除可。

## 共有ファイル(`shared/`)
| ファイル | 役割 |
|---|---|
| `shared/loadgen-csv.yaml` | 計測用 loadgen(locust headless, `_stats.csv` 採取)。**16スクリプトが参照** |
| `shared/loadgen-csv-fail.yaml` | 失敗採取版(`_failures.csv`/`_exceptions.csv` も吐く) |

---

## 1. 基線・診断(`softirq/`)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `baseline-probe.sh` | `baseline-probe.csv` | 基線ドリフト診断(冷えた直後 vs 温まった無負荷の基線差) |
| `baseline-repeat.sh` | `baseline-repeat.csv` | 基線の再現性チェック(無負荷基線をN回連続測定) |
| `netmeasure.sh` | `netmeasure.csv` | normal構成で各サービスの packets/bytes を実測(通信量の内訳) |

## 2. CPU/softirq 比較・スイープ(分離 vs 全部入り)(`softirq/`)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `compare.sh` | `results-cpu.csv` (+`results-compare.csv`, `results-cpu-smoke.csv`, `results-softirq-smoke.csv`) | 分離(1Pod1サービス) vs 全部入り(megapod) の CPU 比較 |
| `sweep.sh` | `results-sweep.csv` | 負荷スイープで normal vs mega を複数負荷レベル比較 |

## 3. 単発トポロジ(部分集約アーム)の softirq 用量反応(`softirq/`)
frontend や checkout に特定サービスを1つずつ同居させ、softirq/req の削減量を測る。
| スクリプト | 出力 | 同居させたもの |
|---|---|---|
| `outmail-softirq.sh` | `results-outmail.csv` | email を checkout に同居 |
| `outpy-softirq.sh` | `results-outpy.csv` | payment を checkout に同居 |
| `paymail-softirq.sh` | `results-paymail.csv` | email + payment を同居 |
| `frontcart-softirq.sh` | `results-frontcart.csv` | frontend + cart + redis を同居 |
| `frontcatalog-softirq.sh` | `results-frontcatalog.csv` | frontend + productcatalog を同居 |
| `frontreco-softirq.sh` | `results-frontreco.csv` | frontend + recommendation を同居 |
| `frontrecocatalogcart-softirq.sh` | `results-front4.csv` | frontend+reco+catalog+cart(front4) |
| `replica-sweep-softirq.sh` | `results-replicasweep.csv` | レプリカ数を振って softirq/req の変化を見る |

## 4. HPA 実験(オートスケール下の資源効率)(`hpa/`)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `hpa-sweep-softirq.sh` | `results-hpasweep.csv` | normal+全HPAで、スケールしても softirq/req がフラットと確認 |
| `hpa-compare-softirq.sh` | `results-hpacompare.csv` | 束ね(front3) vs 分離(normal) 同3サービスをHPAでスケール比較 |
| `hpa-percontainer-softirq.sh` | `results-hpapercont.csv`, `results-hpapercont-allscale.csv`, `results-hpapercont-allscale-max8.csv` | 束ねPodのHPAを Pod平均 vs コンテナ別しきい値で比較(3アーム)。`SCALE_ALL=1` で全固定サービスもHPA化 |
| (図・表) | `hpa-blindspot.svg`, `hpa-allscale-results.md` | 「HPA盲点(softirqはHPAに見えない)」の図、SCALE_ALL本走の詳細結果表 |

## 5. ボトルネック / 失敗診断(2026-07)(`hpa/`)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `bottleneck-diag.sh` | `bottleneck-diag.txt` | u480 rps崩落の律速特定 → **emailservice が96.7%スロットリング** |
| `fail-capture.sh` | (loadgen `_failures.csv` を回収) | 束ねの fails の正体採取(1回) |
| `fail-capture-multi.sh` | `fail-capture-multi.txt` | 上をN回反復。**fails=HTTP500・間欠(email等の1sプローブが混雑ピークにtimeout→一過性NotReady→frontend500)** |

## 6. サービス別利用率カーブ(B測定, 2026-08-18)(`perservice-cpu/`)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `perservice-cpu.sh` | `results-perservice-cpu.csv`, `perservice-cpu.log`(生データ) | 分離・全サービス1台固定・HPA無しで 10〜150周/s の6点を測り、各サービスの利用率カーブ(枠に対する高さ)を取る |
| `perservice-cpu-analyze.py` | (stdout) | 上のCSVを1次近似し `枠=(アイドル+1周CPU×100)/0.7` の適正化テーブルを出す |

## 7. 通信量の実測(エッジ単位, 2026-09-08〜10)(`edge-traffic/`)
softirq から間接的に推定していた「エッジの太さ」を直接測る。
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `edge-traffic.sh` + `edge_traffic_row.py` | `results-edge-traffic.csv`, `edge-traffic.log` | cAdvisor の Pod 単位ネットワークカウンタ(ヘッダ込み)。閲覧型/購入型を分けて差分で定常分を除去 |
| `edge-pairs.sh` + `edge_pairs.py` | `results-edge-pairs.csv`, `edge-pairs.log` | 全Podにエフェメラルコンテナを入れ `ss -tin` でサービス**ペア**単位のバイト/セグメント/RTT/再送を実測。上位2本で6割超、2位は catalog↔reco |
| `edge-pairs-only.sh` | 同上 | netprobe 投入済みの Pod に対して計測だけやり直す |
| `edge_pair_shares.py` | (stdout) | ペア別シェア表(論文の数値出所 `fose2026-data-provenance.md` で使用) |
| `icter-affinity.sh` + `icter_affinity.py` | `results-icter-affinity.csv`, `icter-affinity.log` | 先行研究 ICTer 2022 と同じ指標(カプセル化込みバイト量)で同居前後を比較 → バイト量は減らない(+2〜4%)が softirq は −47% |
| `icter_affinity_summary.py` | (stdout) | 上の要約表 |

## 8. その他のサブフォルダ
| フォルダ | 内容 | 索引 |
|---|---|---|
| `summer2026/` | **2026-08〜09 の主力実験**(適正化・決着実験・混合ワークロード・枠1/3・需要ズレ)。実行は `bundle-vs-loss2.sh`、結果は `results-*.csv`/`timeline-*.csv`/`events-*.csv`/`*.log` の4点セット。`manifests/` は夏休み用の束ねマニフェスト、`smoke/` はスモークテストの出力(参照なし) | `summer2026/EXPERIMENTS.md`(日付で引ける表)、解析は `analysis-*.md` |
| `latency-breakdown/` | 2026-07-14〜09-09。「なぜ分離は頭打ちするか」のレイテンシ分解と固定台数(HPA無し)スイープ。`fixed4-3arm.sh` が 3アーム×4台固定の本走 | `latency-breakdown/investigation-writeup.md` |
| `k6/` | 2026-07-15〜09。閉ループ(locust)の双安定を外すため k6 で開ループ化し容量(崖)を測る。`run-k6-sweep.sh` + `checkout.js` + `k6-job.yaml`、結果 `k6-sweep*.csv` | `k6/README.md` |
| `archive-202606/` | 2026-06-15 の初期 megapod 実験(分離 vs 全部入りの CPU/req)。当時リポジトリ直下にあった `results.csv`/`results_v1_brokennet.csv`(v1 はネットワーク計測が壊れていた版) | — |

---

## 主要な結論(7月時点。8月以降の結論は `summer2026/EXPERIMENTS.md`・`.claude/memory/`・`FOSE2026-TeX-UTF8/fose2026-data-provenance.md` を参照)
- **softirq/req は束ねが分離より −32〜−56%**(通信をlocalhost化した削減。HPA下でも堅牢)。
- **資源効率**: 束ねは分離より少Pod数で同等以上のスループット。
- **u480の双安定**: 束ねは高負荷で「高い枝~960rps ↔ 低い枝~630rps」を行き来(単一HPA判定に賭ける脆さ)。
- **fails**: 束ねが高スループットを出すと弱い下流(email→payment/ad)の1sヘルスチェックが混雑で揺れ、稀にHTTP500。email CPUを300m→800mにすると解消するが犯人が次サービスへ移動(モグラ叩き)。
