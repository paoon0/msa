---
name: fixed-replica-k6
description: 【2026-09-09完了36点】台数4台固定・HPA無し・予約6.30コア一致でk6開ループ比較。softirq front3 −23%/mega −48%、CPU時間 mega −8〜10%、300周/sで分離だけp50暴れる。崖は300より上
metadata:
  type: project
---

**資産: `km2/experiments/summer2026/results-fixed4.csv`(36点)/ `timeline-fixed4.csv` / `fixed4.log`。実行は `bundle-vs-loss2.sh` に 2026-09-09 追加した3つのつまみ。**

## 何をした実験か
HPA を切って**全 Deployment を4台に固定**し、「オートスケーラが何台選んだか」という交絡を外して通信の得だけを見た。
- アーム: `normal`(分離) / `frontrecocatalog`(front3 = frontend+reco+catalog 同居、cart は外) / **`mega`(全部入り、新規追加)**
- 枠: **requests を全コンテナ一律 150m、limits はマニフェスト据え置き**(2026-07-14 `latency-breakdown/fixed-replicas.sh` の規則を踏襲)。
  → 予約が3アームとも **6.30 コア**(4台×10コンテナ×150m + redis 300m)で**完全一致**。limits は3アームともサービス単位で同一と確認済み(frontend 1600m/reco 1600m/catalog 1000m…)。
- 負荷: k6 開ループ、購入型のみ 150/200/250/300 周/s、ウォーム90秒+計測120秒、3サイクル。

## スクリプトに足したつまみ(`bundle-vs-loss2.sh`)
- `FIXED_REPLICAS=N` … HPA を作らず全 Deployment を N 台に固定(redis-cart は1)
- `UNIFORM_REQ_M=150` … requests を一律化(limits は触らない)
- `mega` アーム … `km2/all/all.yaml`。**`MEGA_REDIS=shared`(既定)で redis を Pod の外に出す**。複数台にすると Pod内 redis が台数分でき、カートが割れて1周の仕事量が他アームと変わるため。`extract_redis.py` で redis-cart を切り出し、megapod から redis コンテナを JSON patch で除去し `REDIS_ADDR=redis-cart:6379` に向ける。

## ★結果(3サイクル平均±sd。全36点で取りこぼし0・失敗0・実測=目標)
**softirq [ms/周]**: 150周/s normal 3.034±0.028 / front3 2.340±0.006(**−22.9%**) / mega 1.499±0.029(**−50.6%**)。
300周/s では front3 −18.3% / mega −42.9% と削減率がやや縮む(mega の per-周 softirq が 1.50→1.68 と負荷とともに増える。normal は 2.91〜3.03 でフラット)。
**sd が 0.006〜0.075 に対し差は 0.5〜1.5 = sd の10倍以上**で決定的。

**実CPU時間 [コア秒/1万周](k6分を除く)**: mega は 150/200/250 で **−7.9〜−10.4%**、front3 は 150/200 で −2.4%、250/300 では ±1% 以内。300周/s は normal のばらつきが急増(±16.8)。

**p50 [ms]**: 300周/s で normal 23/79/64(平均55)に対し front3 19/21/20・mega 18/17/16。**高負荷では分離だけが暴れる**。250周/s でも normal 12/18/14 vs 束ね 10〜12。

## 位置づけ
7月の locust 閉ループ・HPA下の値(mega −52%、front系 −9〜−15%)を、**開ループ・台数固定・予約完全一致**という交絡のない条件で再現した。「束ねの得 = HPA が台数を1台減らしたから」ではないことの直接証拠になる。

## 未完
**崖(SLOを満たせる最大レート)は 300周/s より上**。4台固定でも全アームが300を取りこぼし0で捌いた(9月のHPA実験で normal が250で崩壊したのは最大3台だったため)。表1を容量で書くなら **350/400/450 周/s の追加スイープ**が要る。

関連: [[fose2026-live-paper]] [[softirq-cpu-metric]] [[coloc-gain-replica-saving]] [[hpa-scaling-angle]]
