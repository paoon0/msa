---
name: scale-third-experiment
description: 【枠1/3実験 2026-09-04完了・58/60点、解析2026-09-07完了】requests だけ1/3で台数3倍化。★limits も1/3にすると絞りで遅延150倍悪化→枠だけ縮めるのが正解。★解析: 得はcgroup CPUで確実(frontcatalog−1.7%/frontrecocatalog−2.9%)、softirq−16〜26%は超加算(reco→catalogエッジ)、予約枠の得損はHPA77%線の整数閾値効果
metadata:
  type: project
---

**資産: `km2/experiments/summer2026/` の `results-scale3.csv` / `timeline-scale3.csv` / `events-scale3.csv` / `scale3.log`。索引は `EXPERIMENTS.md`。**

## なぜやったか(ユーザ発案)
予約枠は「台数 × 枠」なので**整数の台数でしか動かない**。等倍の枠では台数が1〜2台しかなく、粒度損が「0か1台分か」の二択で中間が測れなかった(実際、閲覧型100/200/300 では5構成すべてが完全に同じ確保CPUになった)。
**枠を1/3にすると利用率が3倍→必要台数も約3倍**になり、損の分解能が上がる。予約枠の総量はほぼ変わらない。

## 条件
5構成(normal / frontcatalog / frontreco / frontcart / frontrecocatalog)× 購入型100周/s固定 × 閲覧型0/100/200/300 × 3サイクル = 60点。取得58点(欠測2=ConfigMapマウント失敗、序盤のみ)。
**枠 requests のみ1/3**(frontend 1077→359 / reco 742→247 / catalog 662→221 / cart 361→120m)。**上限 limits はマニフェストのまま**。
開始3台(PRESCALE=3)・HPA上限20・ウォームアップ180s・計測240s。所要7時間26分。
新つまみ: `RS_SCALE` / `LIMIT_SCALE`(apply_rightsize.py)、CSVに `rs_scale` / `limit_scale` 列。

## ★★最大の発見: limits も1/3にすると絞りで壊れる
スモークを3本回して切り分けた。
| 枠 / 上限 / 開始 | p50(閲覧0) | p50(閲覧300) |
|---|---|---|
| 1/3 / **1/3** / 1台 | **1390 ms** | 746 ms |
| 1/3 / **1/3** / 3台 | **277 ms** | 397 ms |
| **1/3 / 等倍 / 3台** | **6 ms** | **9 ms** |
| (参考)等倍 / 等倍 | 6 ms | 9 ms |
**原因を実測で特定**: 上限1/3のとき productcatalog **94.8%**・recommendation **92.5%** がスロットリング。**ノードCPUは6.58/16コアで空きがあるのに絞られていた**。
⇒ **台数を増やしても1台あたりの瞬間的な処理能力は上がらない。requests だけ縮めて limits は据え置くのが正解。**
※ 私は当初「requests と limits は同じ倍率にすべき(比が変わると条件が揃わない)」と主張したが、**遅延が40〜150倍悪化する状態では比較にならない**ため撤回した。requests:limits の比が 1:1.5→1:4.5 に変わる点は結果に付記が必要。

## ★ユーザ指摘「limits はノードを支配しないか」→ しない
limits 合計は閲覧300で **34.16コア**(ノード16コアの2倍以上)だが、**スケジューリングは requests だけで判定**するため Pending は起きない(実測でも全58点 Pending ゼロ、requests合計は9.21コア)。競合時は CFS が requests の比で配分するので公平性も保たれる。

## 結果(全点で捌け切っている)
取りこぼし最大32件(0.03%)、p50 購入5.8-8.2ms / 閲覧5.2-6.7ms、Pending全点0、HPA上限20への到達なし(最大7台)。
**台数は狙い通り約3倍に**: frontend Pod は閲覧0で3-4台、100で4-5台、200で6台、300で7台(等倍時は1-2台)。Pod総数14-35(等倍時10-18)。

## 生データ(確保CPU / CPU時間 [コア秒]、各サイクル)
| 閲覧 | 構成 | n | 確保CPU | CPU時間 | Pod | FE台 |
|---|---|---|---|---|---|---|
| 0 | normal | 3 | 1498, 1498, 1498 | 845, 825, 873 | 21 | 4 |
| 0 | frontcatalog | 2 | 1411, 1411 | 852, 843 | 17 | 3 |
| 0 | frontreco | 3 | 1557, 1557, 1557 | 860, 851, 871 | 18 | 4 |
| 0 | frontcart | 3 | 1498, 1498, 1498 | 852, 842, 836 | 17 | 4 |
| 0 | frontrecocatalog | 3 | 1413, 1417, 1411 | 836, 840, 898 | 14 | 3 |
| 100 | normal | 3 | 1639, 1725, 1622 | 1059, 1066, 1071 | 24-25 | 4-5 |
| 100 | frontcatalog | 3 | 1708, 1612, 1635 | 1074, 1040, 1022 | 20 | 4 |
| 100 | frontreco | 3 | 1628, 1666, 1822 | 1073, 1088, 1109 | 20-21 | 4-5 |
| 100 | frontcart | 3 | 1725, 1610, 1689 | 1100, 1047, 1075 | 19-20 | 4-5 |
| 100 | frontrecocatalog | 3 | 1726, 1639, 1837 | 1014, 1060, 1163 | 16-17 | 4-5 |
| 200 | normal | 2 | 2256, 2064 | 1385, 1370 | 31-32 | 6 |
| 200 | frontcatalog | 3 | 2088, 2256, 2208 | 1371, 1286, 1354 | 26 | 6 |
| 200 | frontreco | 3 | 2228, 2256, 2255 | 1342, 1385, 1396 | 25-26 | 6 |
| 200 | frontcart | 3 | 2256, 2055, 2203 | 1361, 1343, 1380 | 24-26 | 6 |
| 200 | frontrecocatalog | 3 | 2172, 2064, 2064 | 1345, 1322, 1358 | 19-20 | 6 |
| 300 | normal | 3 | 2371, 2370, 2432 | 1575, 1556, 1564 | 34-35 | 7 |
| 300 | frontcatalog | 3 | 2424, 2464, 2424 | 1588, 1565, 1567 | 28-29 | 7 |
| 300 | frontreco | 3 | 2420, 2402, 2413 | 1568, 1575, 1591 | 27-29 | 7 |
| 300 | frontcart | 3 | 2371, 2484, 2424 | 1588, 1510, 1566 | 27-29 | 7 |
| 300 | frontrecocatalog | 3 | 2484, 2484, 2482 | 1544, 1558, 1549 | 22 | 7 |
## ★解析(2026-09-07完了) → 全文は `km2/experiments/summer2026/analysis-scale3.md`
1. **測り方の教訓**: ノード全体CPU(`node_cpu_sec`)はサイクル間±1〜3%で、束ねの1〜3%効果が埋もれ符号も安定しない。**代わりに `hpa_util_pct × 枠 × 台数` でコンテナ単位のcgroup CPUを復元**すると分解能が一桁上がる。候補4サービス合計(閲覧4水準×3サイクル=12点): frontrecocatalog **−2.88%**(t=−11.9, 12/12負)、frontcatalog **−1.67%**(t=−5.8, 12/12負)、frontcart −0.13%(効果なし)、frontreco **+1.25%**(わずかに損)。減るのは主に**呼ばれる側 catalog**(−4.6〜−8.7%)、frontend は−1.4〜−3.5%。
2. **softirq**: frontcatalog −16〜19%、frontrecocatalog −21〜26%、reco/cart ≈0。★**超加算**を発見: ペアの和(−20.3%)より3つ束ね(−26.2%)が5〜6pt大きい。理由=**reco→catalog エッジ**(`recommendation_server.py:70` の ListProducts)も同時にlocalhost化される。⇒便益の加算は「束ね主とのエッジ」だけでなく**仲間どうしのエッジも足す**。
3. **予約枠の得損は整数の閾値効果**。閲覧0: frontcatalog/frontrecocatalog −359m(frontend1台分)、frontreco +247m、frontcart 0m。閲覧300: 全構成が損(+147〜+386m)。
4. ★★**3台と4台の両方が安定**(HPA許容幅10%): frontend需要2.16枠 → 3台なら72%(<77%で増えない)、4台なら54%だが ceil(4×54/70)=4 で減らない。**どちらに落ちるかは立ち上がりのピークが77%線を踏むか**。同居のCPU−2〜3%がこの分岐を決めた=連続効果が離散節約に増幅。得359mはCPU削減20mに比例しない。
5. **設計則の更新**: 「利用率の高さ(%)が揃うか」では判定できない(HPAが70%に均すので全サービス54〜73%に見える)。**判定量は 需要=利用率×台数 で、同じ整数台数に落ちるか**。閲覧0: frontend2.16/cart2.40=4台側、catalog2.04/reco2.01=3台側 → frontcart損ゼロ・frontreco損、と実測が一致。
6. 次の候補: (a) reco+catalog だけの束ねで超加算を直接検証、(b) 枠を連続に振って得→ゼロ→損の境界を描く。

## 再現コマンド
```sh
cd /home/mizuki/ダウンロード/msa/km2/experiments/summer2026
ARMS="normal frontcatalog frontreco frontcart frontrecocatalog" \
RATES=100 BROWSE_RATE="0 100 200 300" CYCLES=3 \
RIGHTSIZE=1 LIMIT_X=0 PRESCALE=3 HPA_MAX=20 \
RS_SERVICES="frontend productcatalogservice recommendationservice cartservice" \
RS_SCALE=0.3333 LIMIT_SCALE=0 WARM=180 MEAS=240 \
CSV=$PWD/results-scale3.csv TL=$PWD/timeline-scale3.csv EV=$PWD/events-scale3.csv LOG=$PWD/scale3.log \
bash bundle-vs-loss2.sh
```

関連: [[mixed-workload-experiment]] [[coloc-gain-replica-saving]] [[coloc-bundling-decision-rule]] [[hpa-throttling-blindspot]]
