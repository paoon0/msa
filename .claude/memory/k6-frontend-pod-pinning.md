---
name: k6-frontend-pod-pinning
description: 2026-11-20 発見 — k6 の HTTP 接続の使い回しで frontend の負荷がほぼ 1 Pod に集中 (分離・同居とも)。front3 では 1 Pod の reco が詰まり p50 1.78 s。過去結果への影響は未調査
metadata:
  type: project
---

2026-11-20 の smoke-k3f3 (3 つ同居 front3、本番設定) で b50v300 だけ p50 1784 ms。Prometheus のコンテナ別 CPU を見ると、k6 → frontend の負荷が全配合でほぼ 1 つの Pod (各点のリセットで残る最初の Pod) に集中し、他の Pod はほぼ 0。分離 (normal) の frontend も同じ (smoke-k3probe5: 2038m / 22 / 14 / 1m)。reco・catalog は GRPC_LB で均等。k6 の checkout.js には接続の使い回しを止める指定が無い (既定 = VU ごとに keep-alive) → ClusterIP は接続単位で振り分けるので、慣らし初めの 1 台に張り付くと推定。

- front3 では張り付いた Pod の reco が頭打ち (約 1.28 コア) → 待ち時間崩壊。HPA は Pod 平均 (55%) で満足 = 平均と実負荷のずれ。2 回目の本番 (周波数非固定) の pairsQ2 は p50 6〜8 ms で崩れていない (速い CPU で頭打ちに届かなかったと推定)。
- 予約枠 (台数) は使用量の合計で決まるのでほぼ影響なしの見込み。待ち時間・取りこぼし・容量の主張は影響を受けうる。

**Why:** 同居の損得の比較で、同居 Pod だけが負荷の偏りで崩れると「同居の欠点」と誤認する。過去の固定 4 台の「分離は 360 周/s で頭打ち・CPU が余る」も同じ偏りの可能性 (未調査)。
**How to apply:** pdist-k3 3 回目 (pdistk3sep3 / pdistk3pair3) の前に k6 の接続の扱いを決める (例: noVUConnectionReuse)。コンテナ別 CPU を Pod ごとに見て偏りを確かめる。記録 = km2/experiments/summer2026/EXPERIMENTS.md の smoke-k3f3 行、km2/approach/related_work.md §9.31。関連: [[grpc-pinning-imbalance]] [[fixed-replica-k6]] [[rho-pair-selection-focus]]
- 2026-11-20 試した対策: 要求ごと張り直し (NO_REUSE=1) は frontend の CPU +11.8% で ρ・枠が合わなくなる。**20 回に 1 回 Connection: close (CLOSE_EVERY=20) は偏りが消え (Pod 間 ±4%)、frontend の CPU +0.3%・ρ 0.331→0.314 で今の枠のまま使える見込み** → 2026-11-20 ユーザが採用を決定 (「とりあえずこの時々変更する方式で行こうと思う」)。別件: 周波数固定後は購入ありの点で p99 が 350〜840 ms (張り直しと無関係、原因未調査)。
- 2026-11-21 mix-cpu5 (CLOSE_EVERY=20、6 サイクル) 完了: 生カウンタで ρ は mix-cpu4 とほぼ同じ (2 台 |Δρ| ≤ 0.001、1 台 −0.002〜−0.004、cart −0.009)。km2/experiments/rightsizing/analysis-rho5.txt。枠・ρ を作り直すかはユーザ判断待ち。
