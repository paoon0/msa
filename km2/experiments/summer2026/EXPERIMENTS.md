# 実験インデックス(km2/experiments/summer2026/)

日付で呼び出せるようにした索引。「実験9/1」と言えばこの表の該当行を指す。

| 呼び名 | 日付 | 内容 | 結果CSV | 時系列 | ログ |
|---|---|---|---|---|---|
| **通信量実測(エッジ単位)** | 2026-09-08 | **サービスペアごとの通信量を `ss -tin` で実測**(全Podにエフェメラルコンテナを入れnetnsから読む)。ペイロード/セグメント/RTT/再送をエッジ単位で取得。両端から観測して0.1〜0.3%で一致 | `../results-edge-pairs.csv` | — | `../edge-pairs.log` |
| **通信量実測(Pod単位)** | 2026-09-08 | cAdvisor の per-Pod ネットワークカウンタ。ヘッダ込みの実線量。閲覧型/購入型を分けて流し差分で定常分を除去 | `../results-edge-traffic.csv` | — | `../edge-traffic.log` |
| **実験9/7(需要ズレ最大)** | 2026-09-07 | **frontemail / frontcheckout / checkoutemail / catalogcheckout + normal × 閲覧型0/100/200/300 × 3サイクル**。checkout・email は閲覧型に反応しないので需要のズレが最大になる。枠は適正化・等倍(frontend/catalog/checkout/email のみ)。解析 → `analysis-mix2.md` | `results-mix2.csv` | `timeline-mix2.csv` | `mix2.log` |
| **実験9/7(購入スイープ)** | 2026-09-07 | 9/7と同じ5構成 × **購入型100/150/200/250周/s** × 3サイクル(閲覧0固定)。★**購入150周/sで4ペアすべて損ゼロ**=枠が揃えば損は消える証拠。**250周/sは全構成が崩壊**(取りこぼし1064〜6802・p50 2.9〜5.7秒)で比較不能。reco の Ready落ちが窓の74% | `results-ratesweep2.csv` | `timeline-ratesweep2.csv` | `ratesweep2.log` |
| **実験9/4(枠1/3)** | 2026-09-04 | **5構成 × 閲覧型0/100/200/300 × 3サイクル。束ね候補4つの requests のみ1/3(台数約3倍)、limits は等倍**。解析 → `analysis-scale3.md`(2026-09-07) | `results-scale3.csv` | `timeline-scale3.csv` | `scale3.log` |
| **実験9/3(4つ束ね)** | 2026-09-03 | frontcatalog / frontrecocatalog / **frontrecocartcatalog** × 閲覧型4段階 × 3サイクル(cyc4-6) | `results-mix.csv` | `timeline-mix.csv` | `mix.log` |
| **実験9/2(混合)** | 2026-09-02 | 5構成 × 購入型100固定+閲覧型0/100/200/300 × 3サイクル(cyc1-3) | `results-mix.csv` | `timeline-mix.csv` | `mix.log` |
| **実験9/1** | 2026-09-01 | **4構成 × 150/200/250周/s × 3サイクル**(開始1台・部分適正化) | `results-rs4.csv` | `timeline-rs4.csv` | `rs4.log` |
| 実験8/30 (250) | 2026-08-30 | 開始台数3台の検証 @250周/s | `results-prescale250.csv` | `timeline-prescale250.csv` | `prescale250.log` |
| 実験8/30 (300) | 2026-08-30 | 開始台数3台の検証 @300周/s | `results-prescale.csv` | `timeline-prescale.csv` | `prescale.log` |
| 実験9/1 (開始1台) | 2026-09-01 | 開始1台 @200/250周/s × 3 | `results-prescale1.csv` | `timeline-prescale1.csv` | `prescale1.log` |
| 実験B | 2026-08-29 | CPU上限の因果検証(上限あり/×10) | `results-expB-limits.csv` | `timeline-expB-limits.csv` | `expB-limits.log` |
| 負荷スイープ | 2026-08-20 | 4構成 × 150/200/250/300 × 2 | `results-loadsweep.csv` | `timeline-loadsweep.csv` | `loadsweep.log` |
| 適正化検証 | 2026-08-19 | 枠の適正化 @200周/s × 3 | `results-rightsized.csv` | `timeline-rightsized.csv` | `rightsized.log` |
| 決着実験 第2版 | 2026-08-19 | 束ね vs 粒度損 | `results-bundle-vs-loss2.csv` | `timeline-bundle-vs-loss2.csv` | `bundle-vs-loss2.log` |
| **B測定(利用率カーブ)** | 2026-08-18 | 分離・**全サービス1台固定・HPA無し・枠はマニフェストのまま**で 10/30/60/90/120/150周/s の6点。最小二乗法で1次近似し `枠=(アイドル+1周CPU×100)/0.7` の適正化テーブルを作成。frontendは上限に当たった2点を除外し4点 | `../results-perservice-cpu.csv` | — | `../perservice-cpu.log` |
| 決着実験 第1版 | 2026-08-19 | 同上(結論撤回済み) | `results-bundle-vs-loss.csv` | — | `bundle-vs-loss.log` |

---

## 実験9/1 の詳細

**目的**: 束ねの得と損を、同じ単位で測る。

**条件**
| 項目 | 値 |
|---|---|
| 構成 | normal / frontcatalog / frontreco / frontcart |
| 負荷 | 150 / 200 / 250 周/s |
| サイクル | 3(1サイクル = 4構成 × 3負荷 = 12測定) |
| 開始台数 | 1 |
| 枠(requests) | **束ね候補4つだけ適正化**: frontend 1077m / productcatalog 662m / recommendation 742m / cartservice 361m。残り7サービスはマニフェストの値 |
| 上限(limits) | マニフェストのまま |
| HPA | コンテナ別・目標70%・1〜8台・増30s/減60s |
| ウォームアップ / 計測 | 180秒 / 240秒 |
| 測定数 | 38(計画36 + 中断再開による重複2) |

**再現コマンド**
```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026
ARMS="normal frontcatalog frontreco frontcart" RATES="150 200 250" CYCLES=3 \
RIGHTSIZE=1 LIMIT_X=0 PRESCALE=1 \
RS_SERVICES="frontend productcatalogservice recommendationservice cartservice" \
CSV=$PWD/results-rs4.csv TL=$PWD/timeline-rs4.csv EV=$PWD/events-rs4.csv LOG=$PWD/rs4.log \
bash bundle-vs-loss2.sh
```

**主結果**(実CPU時間、測定240秒あたり)
| 負荷 | 構成 | CPU時間 | 1万回あたり | normal比 | 取りこぼし(窓) |
|---|---|---|---|---|---|
| 150 | normal | 1247s | 346.5s | 基準 | 0,0,0,0 |
| 150 | **frontcatalog** | **1213s** | **337.0s** | **−2.7%** | 0,0,0 |
| 150 | frontreco | 1233s | 342.4s | −1.2% | 0,0,0 |
| 150 | frontcart | 1231s | 342.0s | −1.3% | 0,0,0 |
| 200 | normal | 1716s | 357.5s | 基準 | 0,0,0 |
| 200 | **frontcatalog** | **1609s** | **335.3s** | **−6.2%** | 0,0,0 |
| 200 | frontreco | 1684s | 351.4s | −1.7% | 0,183,0 |
| 200 | frontcart | 1730s | 360.8s | +0.9% | 0,109,0 |
| 250 | — | 比較不可(取りこぼし発生: frontcatalog 1130 / frontcart 637) | | | |

**台数**(200周/s): 分離の frontend は3サイクルとも3台。frontcatalog の束ねPodは3サイクルとも2台。
**機構**: 束ねた frontend コンテナは2台で70%、分離 frontend は3台で50%(=2台なら約75%)。同居で frontend のCPUが5〜7ポイント下がる。
**粒度損**: 台数が増えた瞬間の利用率で直接判定した結果、**0件**(2→3台の増加は全回で両コンテナとも70%超)。

**解析スクリプト**
| ファイル | 用途 |
|---|---|
| `loss_attributed.py` | 束ね起因の粒度損(帰属方式) |
| `scale_timing.py` | 各サービスがN台目に到達した時刻 |
| `loss_restricted.py` | 旧・合計引き算方式(参考。無関係サービスのゆらぎが混ざるので非推奨) |

**注意**
- `dropped`(全体)にはウォームアップ中の取りこぼしが混ざる。判定には `dropped_win`(計測窓のみ)を使う
- サイクル2の normal に重複行がある(中断前 + 再開後)。解析では後の行を基準にする
- 250周/s は開始1台では不安定。安定させるには開始3台(実験8/30で 3/3 健全を確認)

## FOSE2026 ライブ論文 (2026-09-14 提出) の数値を再計算するスクリプト

出所と再現状況の一覧は `FOSE2026-TeX-UTF8/fose2026-data-provenance.md`。

| スクリプト | 論文の箇所 | 入力 |
|---|---|---|
| `table1_mismatch.py` | 表1 必要台数の食い違い | `results-mix.csv`, `results-mix2.csv` |
| `fixed4_summary.py` | §3.1 softirq 削減率・飽和帯スループット | `fixed4-all-points.csv` |
| `requests_shift_search.py` | §5 予約枠のずらし探索 5--9% / 28--48% (awk 原本の Python 移植、一致) | `timeline-mix*.csv`, `results-mix*.csv` |
| `../icter_affinity_summary.py` | §3 バイト量 +2--4% | `../results-icter-affinity.csv` |
| `../edge_pair_shares.py` | §5 affinity 割合 | `../results-edge-pairs.csv` |
