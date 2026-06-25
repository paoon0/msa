# Memory Index

- [案① echo comm-time](planA-echo-comm-time.md) — 【現行】エコー法で localhost vs ClusterIP の通信差を確認(p99 −16%, 3/3)。案Bは保留
- [Co-location resource-efficiency study](coloc-resource-efficiency-study.md) — なぜ通信時間に差が出ないか & 資源効率指標への転換
- [Monitoring stack](monitoring-stack.md) — Prometheus/Grafana への到達方法
- [Exact-window measurement](exact-window-measurement.md) — 13分負荷の最後10分だけを事後に厳密計測する方法
- [Related work (colocation)](related-work-coloc.md) — 先行研究(ICTer 2022 / NotNets)と単一ノードで差が出ない文献的理由
- [Coloc trade-off model](coloc-tradeoff-model.md) — 静的メリット vs ∫|a−b| としきい値 τ が存在しない3レジーム
- [Coloc experiment design](coloc-experiment-design.md) — 遠いペア選定(ρ独立制御)と2点較正→未試行ペアΔC予測の枠組み
