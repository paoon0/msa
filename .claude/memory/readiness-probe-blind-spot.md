---
name: readiness-probe-blind-spot
description: 【2026-09-08発見】HPAの4つ目の盲点=プローブ失敗によるReady落ち。250周/sでrecoが窓の74%「2台あるのに1台しかReady」。束ねPodはReadyが全コンテナのANDなので影響範囲が広がる
metadata:
  type: project
---

**「スケールしたくてもできない」の実体は、ノード容量でもHPA上限でもなく readiness プローブだった。**

## 除外できたもの(夏期302点すべてで0件)
- **Pending Pod(ノード容量不足)= 0件**(9/1・9/2・9/3・9/4・9/7×2 のすべて)。枠の適正化で予約が20%減ったため、8/30 に見た容量不足は再現しない
- **HPA上限への到達 = 0件**(上限8台、9/4のみ20台。最大7台)
- **desired > current(増やしたいのに増えない)= ほぼ0**(最大11サンプル/3511)

## ★実際に起きていたもの: ready < current
`timeline-ratesweep2.csv` の計測窓での Ready落ち率:
| 負荷 | 100 | 150 | 200 | **250** |
|---|---|---|---|---|
| **recommendationservice** | 0% | 0% | 6% | **74%** |
| 他の全10サービス | 0〜1% | 0〜1% | 0% | 0〜1% |

例(cyc1 normal 250周/s): `183:2/1 199:2/1 214:2/1 ... 412:2/2` = **2台あるのに ready が1と2を行き来**。
HPA は台数を増やし、スケジューラも Pod を載せているが、**NotReady な Pod は Service のエンドポイントから外れる**ので実際に仕事を受けるのは1台。予約枠だけ2台分取られて処理能力は1台分。

取りこぼしと強く対応(cyc2 catalogcheckout 250: 未準備13/16・取りこぼし6802・p50 5686ms など)。**束ね/分離によらず全構成で発生**。

## なぜ reco だけか
recommendationservice は **Python の gRPC** で、readiness は gRPC ヘルスチェック・**timeoutSeconds は既定の1秒**。負荷が高いと GIL 競合で応答が遅れタイムアウトすると考えられる(未検証)。他は Go サービスで発生しない。
8月の「Ready落ちは構成でなく負荷で決まる(300周/sで全構成13〜31%)」の続きで、今回はサービスを特定でき割合も74%と桁が上がった。

## ★★束ねると影響範囲が広がる(論文で使える)
`km2/frontrecocatalogcart/frontrecocatalogcart.yaml` の3コンテナすべてに readiness プローブがある:
`server(http, timeout既定1s, period既定10s)` / `recommendation(gRPC, timeout既定1s, **period 5s**)` / `productcatalog(gRPC, timeout既定1s, period既定10s)`
**Pod の Ready は全コンテナの AND** なので、reco だけ落ちても **frontend と catalog も巻き添えで Service から外れる**。分離なら reco 1台が外れるだけ。
⇒ 粒度損とは別の、**部分集約のデメリット**。容量比較の実験では束ねが不利に出る要因にもなる。

## 未実施の対処
`timeoutSeconds` を 1 → 5 に緩める(7月から「general fix」として挙げていたが未実施)。ただし緩めると本当に死んだPodも切り離されなくなる。8/29 に「CPU上限を緩めたら悪化」の経験があるので **reco だけで試す**のが安全。

## HPA の盲点は4つになった
1. cgroup 外の **softirq**(通信コスト。全CPUの7〜8%)
2. **limits への衝突**(catalog 86〜94%絞りでも平均利用率は70%未満)
3. **平均に埋もれるバースト**(2の原因)
4. **プローブ失敗による Ready落ち**(本項)
「HPA は平均の利用率しか見ない」という一点から、この研究で見つけた現象がほぼ全部説明できる。

関連: [[hpa-throttling-blindspot]] [[softirq-cpu-metric]] [[fose2026-live-paper]] [[demand-mismatch-experiment]]
