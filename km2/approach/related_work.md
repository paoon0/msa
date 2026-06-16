# 関連研究 (related_work)

> 注記: 本ファイルは git 未追跡のまま誤って削除され、Claude のメモ
> ([[related-work-coloc]] / [[coloc-tradeoff-model]] / [[coloc-resource-efficiency-study]]) から
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

### 3.1 検討した方針

- **案A(不採用): サービスメッシュのサイドカー税削減。**
  Envoy は 1 Pod に 1 個注入され(~0.35〜0.6 vCPU + 40〜72MB / 1000RPS、
  アイドルでも ~10m + 50MB/Pod)、2 サービスを 1 Pod に集約すると Envoy が 2→1 になり、
  さらに同一 Pod 内 localhost は Istio の iptables 捕捉から除外され両側 Envoy をバイパスする
  (2 proxy ホップ消滅)。
  → ただし**ありふれている**(アンビエントメッシュ / ztunnel / eBPF Cilium /
  Canal Mesh [SIGCOMM 2024] が同じ overhead を別解で解決済み)ため不採用。

- **★案B(採用): Pod 集約と独立スケールのトレードオフ。**
  2 サービスを 1 Pod に集約すると、**Pod 単位(部屋ごと)でしかレプリカを増やせない**ため、
  混雑タイミングがズレた相手と同居すると片方の増殖が無駄になる(**レプリカ結合の無駄**)。
  無駄は**負荷の非相関度に比例**する。
  静的メリット(固定コスト減)と釣り合う相関しきい値 τ を実測し、集約判断のルールにする。
  - **新規性**: VM 統合の常識「**反相関**を同居させてピークを均す」が、
    Pod 集約(独立スケール不可)では「**相関**を同居させる」に**反転**することを実機で定量化。
    加えて、v1.30 の ContainerResource HPA でも消えない無駄の実証と、
    静的×動的を束ねる判断モデルの提示。
  - **実験**: 2 サービス(例 checkout 系バースト ↔ productcatalog 定常)を
    分離(独立 HPA) vs 同居(結合 HPA)で比較。需要相関 ρ を振った diurnal 負荷で
    「同一 SLO 達成に要した総 CPU·時間」を測る。信号が大きいのでノイズ問題を回避できる。

---

## 4. 案B のコストモデル(τ が存在しない条件まで)

2 サービス A, B の必要レプリカを a(t), b(t) とし、1 レプリカの仕事予約を r、
Pod 1 個あたり固定オーバーヘッドを分離時 f / 同居時 g(g < 2f が静的メリットの源)とする。

- 分離: `C_sep  = ∫ [ a(r+f) + b(r+f) ] dt`
- 同居: レプリカ結合で `n = max(a,b)` しか刻めず `C_colo = ∫ max(a,b)·(2r+g) dt`

差を静的・動的に分解すると:

```
ΔC = C_sep − C_colo = (f·S − g·M)  −  r·∫|a−b| dt
                       静的メリット≥0      動的デメリット≥0
     S = ∫(a+b),  M = ∫max(a,b)
```

- 動的デメリットがちょうど **∫|a−b|**(= 2 サービスの需要のズレ)になる。「無駄∝非相関度」の式的根拠。
- 相関 ρ と接続すると `∫|a−b| ∝ σ√(1−ρ)`。ΔC=0 を解くと
  **しきい値 τ = ρ\* = 1 − ( √π(fS−gM) / (2rTσ) )²**。

### 4.1 「境目(τ)が存在しない」3レジーム

ρ\* が区間 [−1, 1] の内側に落ちる保証はない:

1. **内点に τ あり**(静的メリット ≈ 最大動的無駄) … 「ρ>τ なら同居」が意味を持つ唯一の領域。
2. **静的が支配 (ρ\*<−1)**(f−g 大 / σ 小) … 相関に関係なく**常に同居が得**。
3. **動的が支配・静的≈0 (ρ\*>1)**(g≈f / σ 大 / r 大) … **常に分離が得**。

**現環境(単一ノード・Envoy 未注入)は g≈f → 静的メリット≈0 → 第3レジーム**。
これまで差が出なかった理由と一致する。
∴ **τ を内点に押し込む**(Istio 注入で f−g を上げる、資源を絞り負荷を振って σ, r を操作する)
こと自体が実験設計の主タスクになる。

---

## 5. 引用すべき先行研究の分類

### A群 — 相関考慮の VM 統合(本研究が"逆転"させる相手)
- **Shen et al. (2014, INFOCOM)** "Consolidating Complementary VMs with Spatial/Temporal-awareness"
- **Kim et al. (2018)** 反相関 VM 配置
- UCD "Scalable Correlation-aware" 系
- **Roytman et al. / Microsoft Tetris** の pairing 手法

  → いずれも「**反相関**な負荷を同居させてピークを均す」前提。
     本研究は独立スケール不可の Pod 集約で**この前提が相関選好に反転する**ことを示す。

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
- コンテナ単位のリソースで HPA を駆動できる新機能。
  「コンテナ別に見れば無駄は消える」という**反論への先回り**として言及
  (それでも Pod 単位のレプリカ結合による無駄は残る)。

### 計測手法の引用
- **MeshInsight** "Dissecting Service Mesh Overheads", arXiv:2207.00592
  (サイドカー overhead の分解計測手法)。

---

## 6. 空白の最終確認(2026-06-16)

「**Pod 同居 + 需要相関 ρ + HPA レプリカ結合の定量化**」を扱う研究はヒットなし = **空白実在**。

**残タスク:**
- Shen (2014) / Kim (2018) の精読。
- IEEE Xplore / ACM Digital Library の横断検索。
