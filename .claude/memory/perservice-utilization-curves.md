---
name: perservice-utilization-curves
description: 【B測定完了 2026-08-18】分離1台固定・枠不変・HPA無しで全サービスのCPU利用率カーブを実測。高さは3群に分離、reco が「通信は重いが損が最大」=通信量ルールと順位が逆転する反例候補
metadata: 
  node_type: memory
  type: project
  originSessionId: 2dd4d9c3-6c10-4a75-b1fc-d1c8c040f86d
  modified: 2026-08-18T14:13:27.230Z
---

**2026-08-18 実施。判定平面の【縦軸=粒度損の予測子】を作る測定が完了。** 資産: `km2/experiments/perservice-cpu.sh`(測定) / `perservice-cpu-analyze.py`(解析) / `results-perservice-cpu.csv`(6レート×11コンテナ) / `perservice-cpu.log`。

**条件(ユーザ確定)**: 分離(normal)・**全サービス1台固定**・**枠(requests/limits)はマニフェストのまま一切変更しない**(=つまみ固定)・HPA無し・Istio無し・k6開ループ 10/30/60/90/120/150 周/s(warm30s+計測180s)・1サイクル。全点 failed=0、drop は120で9・150で20のみ。

**結果1: 高さは3群に分かれる(120周/sでの利用率, 70%到達レート)**
- 熱い: **productcatalog 87%(95周/s)・frontend 85%(90周/s)**
- 中間: currency 57%(171)・cart 56%(166)・email 49%(185)・**recommendation 45%(147)**
- 冷たい: payment 40%(308)・shipping 35%(268)・**checkout 31%(271)**
- 負荷に反応せず: ad 16%(JVM常時分が支配, 傾き≒0)・redis 12%

**結果2: 使用CPUの順位 ≠ 高さの順位(枠で決まる)。** checkout はオーケストレーターで使用CPU 4位(120周/sで247m)なのに**枠800mのせいで最も冷たい**。email/payment は使用CPU最小(80-99m)だが枠200mなので checkout より熱い。⇒ 効くのは重さでなく **重さ÷枠** を実データで確認。

**結果3(★次の実験の核): frontend と束ねる候補で、通信量ルールと損の順位が逆転する。**
| 相方 | 70%到達 | frontendとのズレ | 枠 | 通信量(既測softirq) | 粒度損=無駄枠 |
|---|---|---|---|---|---|
| productcatalog | 95 | **1.05倍** | 600m | **最重量(1.18→1.00)** | **全負荷で0m** |
| recommendation | 147 | 1.63倍 | **1200m** | 2番目(→1.07) | **1200〜2400m** |
| cart | 166 | 1.84倍 | 560m | 3番目(→1.12) | 560〜1120m |
- **reco はズレが cart より小さいのに枠が2.1倍大きいので損は約2倍** ⇒ 通信量だけなら reco>cart、2軸なら cart≧reco で**順位が逆転** = 先行研究(ICTer=通信量Knapsack)との差が実験で決着可能。
- frontend+catalog は**唯一の損ゼロ**かつ通信最重量 = 両軸一致で「まず束ねるならここ」。
- 前回 front4(reco込み)が2レプリカで失速した件([[hpa-scaling-angle]])は、reco の1200mが死に枠になった説明と整合。

**測定上の注意(次に効く)**
- **frontend は 90周/s で4%・120で7%・150で63%スロットリング**(平均使用は limit の半分でも Go のマルチスレッドが CFS 100ms 枠内でバーストするため)。**150の点は frontend では使えない**。
- カーブは高レート側でやや上に反る(superlinear)。k6のVUがcookieを保持しカートが育つ可能性あり=要注意(checkout/cart/recoの1リクCPUが負荷とともに増える)。
- 冷たいサービスの70%到達は外挿値(測定帯150周/sでは届かない)。定性的な群分けには十分だが数値として引用する時は外挿と明記。
- 1サイクルのみ=反復未実施。群分けの結論は堅いが、個々の到達レートは±で語ること([[verify-numbers-python]])。

**次の一手**: HPA有りで frontend+catalog / frontend+reco / frontend+cart を比べ、**「達成スループット ÷ 総予約枠」と Pod 数**で 2軸ルールの予測(cart≧reco, catalog最強)が当たるか検証。マニフェストは `km2/frontcatalog/` `km2/frontreco/` `km2/frontcart/` に既存(枠は分離時と同値のまま同居)。

関連: [[coloc-bundling-decision-rule]] [[softirq-cpu-metric]] [[hpa-scaling-angle]] [[openloop-k6-capacity]]
