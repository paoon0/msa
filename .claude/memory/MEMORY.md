# Memory Index

- [Bundling merit question](bundling-merit-question.md) — 【研究の核】Pod集約は通信短縮だけでなく何のメリットを生むか(多軸)+束数スイープ設計
- [Megapod latency experiment](megapod-latency-experiment.md) — 全部入りPod vs 分離の1リクエスト遅延=低負荷では正味差なし。CPU/reqへ転換中。km2/all/ 資産と実装の罠
- [Softirq CPU metric](softirq-cpu-metric.md) — 【現行・主指標】通信コストはnode softirqモードCPUで測る(userノイズ回避)。9アーム用量反応: normal1.18/paymail1.22/outmail1.18・outpy1.15(軽→効かず)/frontcart1.12/frontreco1.07/frontcatalog1.00/front4 0.826(reco+catalog+cart束ね,−30%)/mega0.56(全,−52%)。【発見1】softirq削減はパケットでなく"バイト"寄り(frontreco判別, ICTerバイトaffin支持)。【発見2=加算的】各単独束ねの削減和0.357≒front4削減0.355=多サービス束ねは各エッジ削減の和で予測可。各サービス通信量はsoftirq-cpu-metric参照
- [HPA scaling angle](hpa-scaling-angle.md) — 【新案・novel性の主軸 2026-07-06】softirqはcgroup外=HPAに見えない「盲点」、co-locが盲点を約半分に(normal7-9%→mega4%, option A済/図hpa-blindspot.svg)。次はB=HPA実有効化でノードあたり容量/レプリカ数を比較。Envoyはやらない

- [echo comm-time](planA-echo-comm-time.md) — 【現行】エコー法で localhost vs ClusterIP の通信差を確認(p99 −16%, 3/3)
- [Co-location resource-efficiency study](coloc-resource-efficiency-study.md) — なぜ通信時間に差が出ないか & 資源効率指標への転換
- [Monitoring stack](monitoring-stack.md) — Prometheus/Grafana への到達方法
- [Exact-window measurement](exact-window-measurement.md) — 13分負荷の最後10分だけを事後に厳密計測する方法
- [Related work (colocation)](related-work-coloc.md) — 先行研究(ICTer 2022 / NotNets)と単一ノードで差が出ない文献的理由
- 【廃止】案B(需要相関ρ・トレードオフτ)は 2026-06-29 にユーザ指示で完全停止・削除。サイドカー同居をメリット前提で精緻化する方向は不採用
