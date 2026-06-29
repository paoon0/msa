---
name: bundling-merit-question
description: 研究の核となる問いの定義 — Pod 集約は「通信時間短縮」だけでなく何らかのメリットを生むか(多軸)
metadata:
  node_type: memory
  type: project
---

**研究の核(2026-06-29 にユーザが2度明確化):** 「**Kubernetes の 1 つの Pod に複数のコンテナ
(とくに直接通信するサービス)をまとめることが、何かしらのメリットを生むか否か**」。
通信時間の短縮は**目的そのものではなく、メリットを生む数あるメカニズムの一つ**にすぎない。
見出し指標は通信時間ではなく **資源効率(同一SLO達成に要する総CPU)と性能(飽和スループット, p99)**。

**まとめることのメリット地図(どれが効くかを実機で切り分けるのが貢献):**
- A 資源: A1 サイドカー税削減(Envoy N→1, 同一Pod内は Envoy 素通り=**最大級**) / A2 Pod固定費(pause/kubelet/IP/cgroup) / A3 予約requests床の共有 / A4 通信処理CPU(NotNets: CPUの25-40%しか業務ロジック, 残りは通信) / A5 メモリ・接続/conntrack削減。
- B 性能: B1 p99低下(echo法で −16% 確認済) / B2 飽和スループット向上(業務ロジックにCPUが回る) / B3 ジッタ低減。
- C 運用: C1 共配置保証 / C2 共有メモリ・emptyDir IPC(通信自体を消せる) / C3 DNS/kube-proxy 依存が1つ減る / C4 mTLS暗号CPU節約。
- D 副次: 省エネ(req あたり消費電力)。

**実験の骨子:** `km2/` の `outmail → paymail → outpaymail → outpy → productshipping` は
**同居サービス数を1個ずつ増やした階段**。Istio注入の有無 × 束数 でスイープし、
横軸=同居数 / 縦軸=総CPU(予約主・実使用副)・p99・飽和スループットを描く。直接1:1で呼び合う連鎖は
需要が自然連動するため、スケール粒度の代償(束ねると軽い方も一緒に増殖)は小さく抑えられる。

**廃止済みの旧方針(復活させない):** 需要相関ρを主役にした「案B(トレードオフτモデル, ∫|a−b|,
反相関の逆転)」は 2026-06-29 にユーザ指示で完全停止・関連ファイル削除。サイドカー同居を
メリット前提で精緻にモデル化する方向は採らない。

関連: [[coloc-resource-efficiency-study]] [[plana-echo-comm-time]] [[related-work-coloc]] [[exact-window-measurement]]
