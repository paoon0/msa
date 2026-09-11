---
name: icter-affinity-replication
description: 【2026-09-10】ICTer2022と同じ指標(カプセル化込みバイト量)でco-locationを測ったら通信量は減らなかった(+2〜4%)。同じ移動でsoftirqは−47%。K8s同一ノードではバイト量は指標として機能しない
metadata:
  type: project
---

**資産: `km2/experiments/icter-affinity.sh` + `icter_affinity.py` + `results-icter-affinity.csv`。**

## 何をしたか
先行研究 ICTer 2022 の指標 **communication affinity = サービス間のオンザワイヤ総バイト量(カプセル化込み)** を、Kubernetes の Pod 同居で再現測定した。目的は批判ではなく「**K8s環境でも削減が効くか**」の確認。

**測り方**: tcpdump の代わりに **Pod netns の `/proc/net/dev`** をエフェメラルコンテナから読む(デバイス層=ヘッダ込み、`eth0`=bridge経由 / `lo`=loopback経由 が自動的に分かれる)。**cAdvisor は `lo` を出さない**ので netns 直読みが必須。クライアント辺(k6↔frontend)は k6 Pod の cAdvisor カウンタで差し引く。
**★推定量の選び方**: 「Σ eth0受信 − k6送信(1.6kB/周)」の方が「Σ eth0送信 − k6受信(32kB/周)」より誤差に強い(大きい値を引くと窓ずれが増幅される。送信側だと front3 が +11% に化けた)。
条件: 全サービス1台固定・HPA無し・枠はマニフェストのまま・購入型100周/s・ウォーム30/計測180秒・2サイクル。

## ★結果(購入1周あたり)
| 構成 | bridge経由 | loopback経由 | 合計(=affinity) | パケット |
|---|---|---|---|---|
| 分離 | 31,173B | 0 | **31,173B** | 231.7 |
| front3 | 12,188B | 19,610B | **31,797B (+2.0%)** | 226.7 |
| mega | 48B | 32,431B | **32,478B (+4.2%)** | 227.3 |

**経路は完全に移動した(mega の bridge 経由は 31,173→48B)が、総量もパケット数も減らない。**

**検算**: 分離の合計 31,173B は 9/8 の `ss -tin` 推定 30,674B と **1.6%一致**。front3 の loopback 19,610B は内部化3エッジのヘッダ込み推定 19,033B と **3.0%一致**。別手法で一致 = 測定は信頼できる。

## ★解釈(ICTer と矛盾しない)
原典が明言: *"Application-level data volume does not change if the network type is changed. However, the encapsulation overhead depends on the container network type."*
- ICTer の 52〜57% は **overlay(VXLAN 等、外側ヘッダ50B前後)を外した分**
- **bridge → loopback で減るカプセル化はイーサネットヘッダ14Bだけ**(平均パケット長134Bの10%)。loopback 側の増分と相殺され、正味で消える
⇒ ICTer が Merged で報告した +13% も大半は「別ホスト→同一ホスト」の移動由来。**K8s のように最初から全部同一ノードにある環境では、バイト量ベースの効果はゼロ**。

## ★本研究の結論
同じ移動を **CPU で測ると −47.1%(softirq)/ −7.2%(通信処理の総CPU)**。
**減ったのは「運ぶ量」ではなく「運ぶ手間」**(veth の受け渡し・ブリッジの転送判断・iptables/conntrack の照合が1パケットごとに消える)。
⇒ **ICTer の指標をそのまま K8s に持ち込むと効果ゼロと判定されてしまう。** バイト量は overlay の有無を測るには良い代理変数だが、同一ノード内の bridge→loopback には使えない。批判ではなく**適用範囲の違い**。これが softirq を使う積極的な理由になる。

関連: [[fixed-replica-k6]] [[edge-traffic-measurement]] [[softirq-cpu-metric]] [[related-work-coloc]] [[fose2026-live-paper]]
