---
name: hpa-scaling-angle
description: 【新案・novel性の主軸候補 2026-07-06】co-locationのメリットをHPAに絡める。softirqはcgroup外=HPAに見えない「盲点」で、束ねると盲点が縮む。
metadata:
  node_type: memory
  type: project
---

2026-07-06、ユーザ指示で **novel性の主軸を Envoy税から HPA へ転換**(「envoyはしない。HPAに話を絡めたい」)。「重い通信ペアを束ねよ」は先行 ICTer と共通で差にならず([[related-work-coloc]])、バイトvsパケットの反証も frontreco でバイト寄りと出て不成立([[softirq-cpu-metric]])。→ HPA が新しい独自角度。

**核心の主張:** HPA は CPU でスケールするが、その CPU は **metrics-server が読む cgroup CPU(=各Podのapp計算)**。ところが **通信コストの softirq は cgroup 外**(ksoftirqd/割り込み文脈, どのPodにも計上されない=[[softirq-cpu-metric]]で確立)→ **HPA に見えない=「HPA盲点」**。しかも co-location は softirq を削るので **盲点を縮める**。ICTer/NotNetsに無い、softirq指標に固有の切り口。

**含意3点:** ①HPAは実ノード負荷を過小評価(分離ほど盲点大→"余裕がある"と誤認しノード飽和し得る)。②app CPU/reqはco-locで不変(対照群)=**HPAは分離でも束ねでも同じ台数にスケール**→softirq節約は"HPAが奪い返さない純粋な余力"。③代償:HPAはPod単位でスケール→束ねると中の複数サービスが一緒にしかスケールできない=**粒度損**(softirq節約がこれを上回るかがトレードオフ)。

**option A 完了(既存 results-sweep.csv だけで算出):** 盲点=softirq/app。負荷スイープ rps239/476/595/677 で normal 8.7→7.8→6.9→6.9% / mega 4.6→4.2→4.1→3.9%。**co-locが盲点を毎レベル約半分(1.7-1.9倍)に、飽和近く677rpsまで持続**(低負荷限定でない)。softirq/nodeでも normal6.3→5.4%/mega3.2→3.1%。図=`km2/all/hpa-blindspot.svg`(matplotlib/pip無い環境ゆえ手書きSVG生成)。

**次の実験:**
- **B(本命・次にやる):** HPA(metrics-server)を実際に有効化し、負荷を飽和まで上げ、分離 vs 束ね で「SLOを保てる最大rps / 必要総レプリカ数 / ノード実CPU余力」を比較。予想=束ねはsoftirqを空けた分、同ノードで**高い最大スループット/少ないレプリカ**。前提: MicroK8sで metrics.k8s.io が要る(`microk8s enable metrics-server`)。単一ノードなので「ノード数削減」でなく「ノードあたり容量」で示す。
- **C(裏面):** 片側だけ負荷が偏るワークロードで束ねPodの粒度損を測る=トレードオフ定量(廃止した案B需要相関ρとは別。メリット前提でなくコスト測定なので可)。

計測の型は softirq 実験と同じ(exp ns, Istio無し, resources=all値, USERS/RATE, promq経由Prometheus)。実験資産は `km2/all/`。

関連: [[softirq-cpu-metric]] [[bundling-merit-question]] [[coloc-resource-efficiency-study]] [[related-work-coloc]]
