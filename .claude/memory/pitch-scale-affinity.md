---
name: pitch-scale-affinity
description: 研究の売り (ユーザ確定 2026-11-05) = オートスケールを考慮した同居。通信の親和性 (affinity) だけでなくスケールの親和性でまとめないと HPA で無駄が出る
metadata:
  node_type: memory
  type: project
  originSessionId: 32ae1817-99cb-4f9e-916c-7bf4147c442c
  modified: 2026-11-04T18:06:34.413Z
---

ユーザが 2026-11-05 に確定した研究の位置づけ (FOSE 発表・修論の訴求)。
- 先行研究は、通信量 (affinity) の大きいサービスを同居させると大きな効果が出ることを示した (Wickramanayaka 2022: ホスト間→ホスト内で affinity −58.5%、Buzato 2025: 1 コンテナにまとめる)。
- 本研究の新しさは**オートスケールを考慮している点**。K8s の HPA は Deployment 単位なので、同居させると一緒にしか増やせない。affinity だけで相手を選ぶと、必要台数の伸び方が違う相手で粒度損が出る。
- 結論: **通信の親和性に加えて「スケールの親和性」(必要台数の伸び方が揃うか) でまとめる必要がある**。証拠は FOSE 表 1 (frontend+catalog は affinity 38.8% で入れ替わらない、frontend+email は 0% で入れ替わる)。

**Why:** 単一ノードでは同居の得がノード CPU の数% と小さく (results-fixed4.csv)、「同居で安くなる」は言えない (予約枠は最良でも分離と同等)。得の大きさではなく「選び方」が貢献。
**How to apply:** 発表・論文の訴求はこの軸で組む。「同居で安くなる」とは書かない。金額は GKE Autopilot での「損」としてだけ使う ([[fose2026-live-paper]]、related_work.md §9.11)。「スケールの親和性」は論文本文の用語ではない (本文は「必要台数の大小が入れ替わる/伸び方が揃う」) ので、使うなら定義を 1 行添える。
