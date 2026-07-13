# km2/experiments — 実験スクリプト & 結果インデックス

このフォルダは修士研究「コンテナ集約(co-location)の資源効率」の**負荷実験一式**。
ファイルは実験ごとに物理フォルダ分けせず、この索引で「実験名 → スクリプト → 結果CSV → 何を見たか」を一覧する。

## 実行時の共通事項
- スクリプトは**リポジトリ直下から** `bash km2/experiments/xxx.sh` で実行(内部パスは絶対参照)。
- 出力(CSV/ログ)は `km2/experiments/` に書かれる。
- 全部入りマニフェスト `all.yaml` だけは `km2/all/all.yaml`(別フォルダ)を参照する。
- 束ねトポロジのマニフェストは `km2/frontrecocatalogcart/`(別フォルダ)。
- 使い捨てログ(`*.log`, `last-logs-*.txt`)は実行のたび再生成されるので随時削除可。

## 共有ファイル(特定の実験に属さない)
| ファイル | 役割 |
|---|---|
| `loadgen-csv.yaml` | 計測用 loadgen(locust headless, `_stats.csv` 採取)。**16スクリプトが参照** |
| `loadgen-csv-fail.yaml` | 失敗採取版(`_failures.csv`/`_exceptions.csv` も吐く) |
| `hpa-blindspot.svg` | 「HPA盲点(softirqはHPAに見えない)」の図 |
| `hpa-allscale-results.md` | SCALE_ALL本走の詳細結果表 |

---

## 1. 基線・診断
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `baseline-probe.sh` | `baseline-probe.csv` | 基線ドリフト診断(冷えた直後 vs 温まった無負荷の基線差) |
| `baseline-repeat.sh` | `baseline-repeat.csv` | 基線の再現性チェック(無負荷基線をN回連続測定) |
| `netmeasure.sh` | `netmeasure.csv` | normal構成で各サービスの packets/bytes を実測(通信量の内訳) |

## 2. CPU/softirq 比較・スイープ(分離 vs 全部入り)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `compare.sh` | `results-cpu.csv` (+`results-compare.csv`, `results-cpu-smoke.csv`, `results-softirq-smoke.csv`) | 分離(1Pod1サービス) vs 全部入り(megapod) の CPU 比較 |
| `sweep.sh` | `results-sweep.csv` | 負荷スイープで normal vs mega を複数負荷レベル比較 |

## 3. 単発トポロジ(部分集約アーム)の softirq 用量反応
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

## 4. HPA 実験(オートスケール下の資源効率)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `hpa-sweep-softirq.sh` | `results-hpasweep.csv` | normal+全HPAで、スケールしても softirq/req がフラットと確認 |
| `hpa-compare-softirq.sh` | `results-hpacompare.csv` | 束ね(front3) vs 分離(normal) 同3サービスをHPAでスケール比較 |
| `hpa-percontainer-softirq.sh` | `results-hpapercont.csv`, `results-hpapercont-allscale.csv` | 束ねPodのHPAを Pod平均 vs コンテナ別しきい値で比較(3アーム)。`SCALE_ALL=1` で全固定サービスもHPA化 |

## 5. ボトルネック / 失敗診断(2026-07)
| スクリプト | 出力 | 何を見たか |
|---|---|---|
| `bottleneck-diag.sh` | `bottleneck-diag.txt` | u480 rps崩落の律速特定 → **emailservice が96.7%スロットリング** |
| `fail-capture.sh` | (loadgen `_failures.csv` を回収) | 束ねの fails の正体採取(1回) |
| `fail-capture-multi.sh` | `fail-capture-multi.txt` | 上をN回反復。**fails=HTTP500・間欠(email等の1sプローブが混雑ピークにtimeout→一過性NotReady→frontend500)** |

---

## 主要な結論(詳細は .claude/memory/ と hpa-allscale-results.md)
- **softirq/req は束ねが分離より −32〜−56%**(通信をlocalhost化した削減。HPA下でも堅牢)。
- **資源効率**: 束ねは分離より少Pod数で同等以上のスループット。
- **u480の双安定**: 束ねは高負荷で「高い枝~960rps ↔ 低い枝~630rps」を行き来(単一HPA判定に賭ける脆さ)。
- **fails**: 束ねが高スループットを出すと弱い下流(email→payment/ad)の1sヘルスチェックが混雑で揺れ、稀にHTTP500。email CPUを300m→800mにすると解消するが犯人が次サービスへ移動(モグラ叩き)。
