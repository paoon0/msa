# 関連研究 (related_work)

> 注記: 本ファイルは git 未追跡のまま誤って削除され、Claude のメモ
> ([[related-work-coloc]] / [[coloc-resource-efficiency-study]]) から
> **2026-06-16 に再構成**したものです。元ファイルにあった細部の文言は失われている可能性があります。
> 以後は必ず `git add` してコミットすること。

本研究のテーマ: **Kubernetes の Pod に複数のアプリコンテナを部分的に同居(co-location, localhost 通信)
させると、1 Pod 1 サービスの細分化構成より計算資源の利用効率が高くなる**ことを実機で定量化する。

---

## 1. 直接の先行研究(同居・統合そのもの)

### 1.1 Wickramanayaka, Keppitiyagama, Thilakarathna (2022)
"Communication-Affinity Aware Colocation and Merging of Containers",
*International Journal of Advances in ICT for Emerging Regions (ICTer)* 15(3).
DOI: 10.4038/icter.v15i3.7251 (オープンアクセス)

- ほぼ同一テーマの最重要先行研究。
- コンテナ配置を3段階で比較:
  - **Spreaded** — 別ホストにまたがり overlay ネットワーク経由(通信コスト係数 K_o)
  - **Colocated** — 同一ホスト上で bridge 経由(K_b)
  - **Merged** — 同一ネットワーク名前空間で loopback 経由(K_l)
  - 不等式 **K_l < K_b < K_o**(loopback が最安、overlay が最も高い)。
- 配置問題を **Binary Knapsack** として定式化し最適配置を求める。
- 実験環境: Docker Swarm + Sock-Shop(マイクロサービスベンチ)。
- 計測指標: `tcpdump` による**通信バイト量(communication affinity)**。
- 結果: colocation で通信 **52〜57% 減**、さらに merging で **+13%**、合計 **58.5% 減**・
  実行時間 **13.4% 短縮**。

### 1.2 Alvaro et al. (2024) — NotNets
"NotNets: Accelerating Microservices by Bypassing the Network", arXiv:2404.06581

- マイクロサービスでは CPU サイクルの **25〜40% しか業務ロジックに使われない**。
  残りは通信処理(シリアライズ / HTTP / gRPC コア / カーネル)に費やされる。
- CXL 共有メモリで RPC をネットワークバイパスし、echo レイテンシを**約1桁削減**。
- 「通信オーバーヘッドを物理的に消すと大きく効く」ことの定量的裏付けとして引用。

---

## 2. 最重要の示唆 — なぜ単一ノードでは差が出にくいか

- 大きな差は **overlay の有無**(K_o → K_b、約 52〜57%)で生まれる。
  bridge → loopback(K_b → K_l、約 13%)は相対的に小さい。
- Suo et al. (2018, INFOCOM) の実測: overlay ネットワークは host 比でスループット **82.8% 減**。
- **本研究の現環境(単一ノード・Envoy 未注入)には overlay が無い**ため、
  測れるのは一番小さい K_b → K_l の差だけ。
  → CPU/req の差がノイズ床に埋もれるのは**文献的に当然**。
- 有意差を出すには:
  1. マルチノード + CNI overlay を導入するか、
  2. 高負荷・多反復で小さな差を精密計測する。

---

## 3. 本研究の差別化(空白)

- **K8s Pod 同居 = コンテナの分離(独立イメージ・独立プロセス)を保ったまま loopback を得る**
  状態。これは ICTer の colocate と merge の中間に位置する。
- これを **CPU/req = 資源効率** の軸で定量化する点が、既存研究の空白。

### 3.1 同居がもたらしうるメリットの軸

直接通信するサービスを 1 Pod にまとめると、次の経路で資源低減・性能向上が期待できる:

- **通信経路の短縮**: ClusterIP(veth + bridge + conntrack/iptables)→ localhost(loopback)で、
  1 パケットあたりのカーネル処理が軽くなる(§1・§2)。
- **サービスメッシュのサイドカー税削減**: Envoy は 1 Pod に 1 個注入され
  (~0.35〜0.6 vCPU + 40〜72MB / 1000RPS、アイドルでも ~10m + 50MB/Pod)、
  2 サービスを 1 Pod に集約すると Envoy が 2→1 になる。さらに同一 Pod 内 localhost は
  Istio の iptables 捕捉から除外され両側 Envoy をバイパスする(2 proxy ホップ消滅)。
  ※ メッシュ overhead 削減そのものはアンビエントメッシュ / ztunnel / eBPF Cilium /
  Canal Mesh [SIGCOMM 2024] でも扱われており、本研究は「アプリ層の Pod 集約」での寄与を切り分ける。

---

## 4. 引用すべき先行研究の分類

### B群 — マイクロサービス粒度の問題(本研究が埋める空白)
- **Hassan et al. (2020, SPE / arXiv:1903.11665)** systematic mapping。
  空白「**粒度適応のコスト・利益の動的評価**」を明記(精読相当完了 2026-06-16)。本研究が埋める対象。
- **Hassan et al. (2022, SPE)** DOI:10.1002/spe.3069 "Systematic Scalability Analysis"。
  定性フレームワーク止まり = 空白未充填。
- "Microservices Granularity vs Performance" (2017)。

  → いずれも**定性的のみで未定量** = 空白確定。

### C群 — オートスケーリング(背景。競合ではない)
- Autoscaling Survey, arXiv:2507.17128
- Smart HPA, arXiv:2403.07909
- **COLA, arXiv:2112.14845**(別 Pod 前提。同一 Pod 結合問題は対象外と確認済み)

### D — HPA ContainerResource (v1.30)
- コンテナ単位のリソースで HPA を駆動できる新機能。同居しても各コンテナ個別にスケール判断できる、
  という同居の負担を緩和する仕組みとして背景に置く
  (ただし Pod は最小スケール単位のままなので、同居によるレプリカ刻みの粗さは残る)。

### 計測手法の引用
- **MeshInsight** "Dissecting Service Mesh Overheads", arXiv:2207.00592
  (サイドカー overhead の分解計測手法)。

---

## 5. 空白の最終確認(2026-06-16)

「**Kubernetes の Pod 同居が資源効率・性能に与える影響を、コンテナ分離を保ったまま CPU/req で
定量化する**」研究はヒットなし = **空白実在**。粒度問題(B群)は定性的に語られるだけで未定量。

**残タスク:**
- IEEE Xplore / ACM Digital Library の横断検索。
