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
- **★ベースライン(2026-08-29 に原典PDFで確認)= Docker Swarm の Spread 戦略 = 「1サービス = 1ホスト」。**
  原文: *"Spread strategy deployment of Docker Swarm is considered as the baseline to this study. ...
  we consider the deployment of service instance per host as the baseline since there are not any
  optimizations present in that strategy."* / *"initial monitoring was done deploying each
  service/container in a separate VM."* 定式化でも *"according to Spread strategy (one service per host)"*。
- 3段階が減らすもの(Table I): 初期 n サービス/n コンテナ/**N ホスト** → colocation 後 n/n/**M ホスト(M<N)**
  → merging 後 n サービス/**m コンテナ(m<n)**/M ホスト。
  つまり **Colocated = ホストを減らす**(コンテナ数は不変, bridge 経由)、
  **Merged = コンテナ自体を統合**(1コンテナ内の2プロセス, loopback 経由。同一ベースイメージが必須で、
  Dockerfile を結合し ENTRYPOINT をシェルスクリプトにして2サービスを起動する実装)。
- 配置問題を **Binary Knapsack** として定式化し最適配置を求める。**制約は CPU 使用量のみ**
  (*"consider only the CPU usage as a constraint that limits the colocation"*)。
- 実験環境: Docker Swarm + Sock-Shop と Page-Rank の2ベンチ。
  ホストは Sock-Shop 用が 4/5/5/4 コアの4台、Page-Rank 用が 3/6/9/10 コアの4台。

**★本研究との位置関係(重要):**
| | ICTer | 本研究(単一ノード時点) |
|---|---|---|
| ベースライン | 1サービス=1ホスト(全部別VM, overlay越し) | 1 Pod 1サービス, **全部同じノード** |
| 比較対象 | Colocated(同ホスト別コンテナ)/ Merged(1コンテナ2プロセス) | 同一Pod(別コンテナ, localhost) |
⇒ **本研究の「分離(normal)」は ICTer の Colocated に相当し、ベースライン(Spreaded)ではない。**
  ICTer が測った大きい効果(52-57% = overlay の有無)は最初から手に入っており、
  測れているのは残りの K_b→K_l 部分だけ。マルチノード化して初めて同じ土俵に立てる。
⇒ ICTer の Merged は**コンテナ分離を捨てている**(1コンテナ2プロセス)。
  K8s の Pod 同居は**分離を保ったまま loopback を得る** = Colocated と Merged の中間 = 差別化点(原典で裏付け済)。
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

---

## 6. 需要の向き ρ（リクエスト型配合への応答）による相手選びの先行研究調査 (2026-10-09)

背景: 本研究の新しい切り口 ρ = ν/β。サービス別 CPU 需要を D = c + β·buy + ν·view と回帰し、ρ が揃うサービスどうしを
同居させると、配合が変わっても HPA の必要台数が揃い損が出にくい。分離構成の測定から同居時の台数・損を事前登録で予測し 30/30 的中。
調べた観点: (1) リクエスト型配合→CPU 需要の回帰、(2) マイクロサービス同居で通信量以外の相手選び基準、
(3) VM/コンテナ統合の負荷相関、(4) マルチコンテナ Pod × HPA、(5) リクエスト型を使うオートスケール。

**結論: 「ρ による同居相手選び」そのものの既出は、下記の検索範囲では見つからなかった（衝突なし）。**
ただし部品ごとには強い先行がある: (1) 配合→需要の線形回帰 = 2005–2007 年の古典、(3) 相関で詰める = 2009–2013 年の古典。
新規性は「部品の組合せ」を「Pod 単位 HPA の整数台数が揃うか」という判定に接続した点にある。主張は
「ρ は新しい統計量」ではなく「古典の需要モデルを HPA の台数ずれ予測に使った」と書くのが安全。

> 注意（検索の限界）: Google Scholar / IEEE Xplore / ACM DL は直接引けず（ACM・Springer・ScienceDirect は 403 または認証リダイレクト）、
> WebSearch と arXiv/USENIX の直取得のみ。「無かった」は WebSearch の範囲での話。IEEE/ACM DL 横断は未実施のまま（§5 の残タスク継続）。

### 6.1 観点(1) 配合 → 需要の回帰（背景＋手法の祖。衝突ではない）【B/背景】

#### 6.1.1 Stewart & Shen (2005) ★原典PDFで確認 (2026-10-09, 本文を pdftotext で抽出し節単位で確認)
"Performance Modeling and System Management for Multi-component Online Services",
*NSDI 2005* (2nd Symposium on Networked Systems Design & Implementation), pp.71–84。
URL: https://www.usenix.org/legacy/event/nsdi05/tech/full_papers/stewart/stewart.pdf
- 要点: 多コンポーネント Web サービス（RUBiS 11 コンポーネント、StockOnline 7 コンポーネント、J2EE/EJB）で、
  **コンポーネントごとの CPU 使用率を入力リクエスト率 λ の線形式で当てる**（Table 1 例: Bid = 0.172·λ+0.509 [%]）。
  入力は (λ, δ) で δ に「リクエスト型の構成 (request mix)」を含める定式。モデルは「同一サーバ同居なら remote invocation
  オーバーヘッドが消える (fast-path)」を区別し、コンポーネント配置・複製戦略を焼きなまし法で最適化（all-replication 比 +7%、low-replication 比 +31% スループット）。
- ベースライン: 常識的配置 (all replication = JBoss 推奨、low replication) とランダムサンプリング最適化。
- 測定環境: 12 ノードの異種 Linux クラスタ、1 Gbps Ethernet、オーケストレータなし（J2EE ミドルウェア）。単一ノードではない。
- 指標: LTT（Linux Trace Toolkit）による OS 計装で CPU/メモリ/ディスク/ネットワーク帯域/ブロッキング通信頻度。
- 主張の範囲: プロファイルは「各コンポーネントを専用サーバに置いて」取る（本研究が分離構成で測るのと同型）。負荷は定常（オートスケールなし）。静的配置。
- **本研究との関係: 相補的（手法の祖）。** 「分離でプロファイル→同居の性能を予測」「型配合をパラメータに入れる」は既出。
  ただし (a) 配合ごとの係数 β/ν に分けて「向き」ρ を相手選びの基準にしてはいない、(b) HPA/整数台数/予約枠の損は対象外、
  (c) 目的は最大スループット・応答時間で、予約枠の損ではない。**ρ の「回帰の部品」を引くなら第一候補。** 群: 背景（B/C に準ずる新設「E群: 需要モデル」）。
  ※「ρ ごとに揃えるべきだ」という Stewart & Shen の記述は無い（原文に該当語なし、grep で request mix/co-located を確認）。

#### 6.1.2 Zhang, Cherkasova ほか (2007/2008) — 検索スニペットのみ（原典未読）
"A regression-based analytic model for capacity planning of multi-tier applications",
*Cluster Computing* (2008); 初出は ICAC 2007 (4th Int. Conf. on Autonomic Computing)。
URL: https://link.springer.com/article/10.1007/s10586-008-0052-0 （DOI 10.1007/s10586-008-0052-0, URL 由来）。
Semantic Scholar: https://www.semanticscholar.org/paper/A-regression-based-analytic-model-for-capacity-Zhang-Cherkasova/60f82982348e2121073fada21ace099b6fa1cd4e
- 確認できた範囲（WebSearch の要約）: クライアントトランザクションの CPU 需要を**回帰で近似**し、待ち行列網（各層=1 キュー）に入れる。
  **トランザクション配合が時間で変わる負荷**でも有効だと示す。オンラインプロファイラ（処理トランザクション数と DB 呼出数）を使う。
- 著者全員・正確な頁・ベースライン・測定環境は**未確認**（Springer は認証リダイレクト、Semantic Scholar は 403）。
- **本研究との関係: 背景（手法の祖）。** 「配合→層別 CPU 需要を回帰」の系譜の代表。ユーザ依頼文の想定どおりの論文が実在することは確認。
  ただし相手選び・HPA・Pod 同居は扱っていない（要約範囲では）。引用前に原典 PDF を要確認。

#### 6.1.3 Spinner, Casale, Brosig, Kounev (2015) — abstract のみ（検索スニペット）
"Evaluating approaches to resource demand estimation", *Performance Evaluation* 92, pp.51–71.
URL: https://www.sciencedirect.com/science/article/abs/pii/S0166531615000711 （403 で本文未取得）
- 要点: 資源需要推定法の調査・分類と、7 手法の実験比較（監視窓、ワークロードクラス数、負荷水準、**共線性 collinearity**、モデル不一致の影響）。
- **本研究との関係: 背景。** β/ν の推定の妥当性（buy と view の比が共線のとき回帰が不安定）を論じる際の方法論の引用元。
  「ρ の推定誤差」を議論する節で使える。

#### 6.1.4 Bauer, Grohmann, Herbst, Kounev (2018) — abstract のみ
"On the Value of Service Demand Estimation for Auto-scaling", *MMB 2018* (Measurement, Modelling and Evaluation of Computing Systems), Springer。
URL: https://link.springer.com/chapter/10.1007/978-3-319-74947-1_10
- 要点（題と著者のみ確認。内容は未読）: サービス需要推定をオートスケーラに使う価値の評価。
- **本研究との関係: 背景（未読のため判定保留）。** 「需要推定を使うオートスケール」の系譜。同居は扱わないと推測されるが未確認。

### 6.2 観点(3) 負荷相関を使った統合（ρ の祖先。衝突ではない）【背景】

#### 6.2.1 Verma, Dasgupta, Nayak, De, Kothari (2009) ★原典PDFで確認 (2026-10-09, 抜粋)
"Server Workload Analysis for Power Minimization using Consolidation", *USENIX ATC 2009*, San Diego.
URL: https://www.usenix.org/legacy/event/usenix09/tech/full_papers/verma/verma.pdf
- 要点: 企業サーバ負荷の実トレース解析。アプリ間の**ピーク同時性（相関）**を考えない統合はリスクが高い、と指摘し、
  **Correlation Based Placement (CBP)** と **Peak Clustering based Placement (PCP)** を提案。
  本文に "not aware of any prior study that utilizes correlation between applications" とある（自称の先駆性）。
- ベースライン: ピーク/オフピーク値ベースの従来統合。測定環境: 企業データセンターの実トレース（VM 統合、K8s ではない）。
  指標: サーバ数・電力・性能リスク。静的/半静的統合。
- **本研究との関係: 相補的（概念の祖）。** 「時間に関して相関する→ピークが重なる」を統合に使う点は ρ と同じ発想。
  違い: (a) 相関は**時系列（時間）**上のもの、本研究の ρ は**リクエスト型の配合**に対する応答の向き（時間に依らず配合が変わるとき効く）、
  (b) 目的は台数削減・電力であり、**Pod 単位 HPA の整数台数が揃うか**ではない、(c) 同居で通信 CPU が減る便益とのトレードオフではない。
  「ρ は相関統合の“配合版”と言えるか」→ 言える部分と言えない部分がある（§6.5 参照）。

#### 6.2.2 Meng, Isci, Kephart, Zhang, Bouillet, Pendarakis (2010) — abstract のみ（検索スニペット）
"Efficient resource provisioning in compute clouds via VM multiplexing", *ICAC 2010* (7th Int. Conf. on Autonomic Computing)。
DOI: 10.1145/1809049.1809052 （oadoi 経由 URL 由来。ACM は 403 で本文未取得）
- 要点: ピーク/谷が時間的にずれた（無相関）VM を一緒に確保すると合計必要容量が劇的に減る。約 16,000 VM の商用 DC 計測で資源利用 45% 超の改善。
- **本研究との関係: 背景。** 「揃わない相手と束ねると“得”（統計的多重化）、揃う相手と束ねると“損”なし」の向きに注意:
  VM 統合は**ずれた相手ほど得**、本研究（Pod 単位 HPA）は**揃った相手ほど損が出ない**。**向きが逆**なので混同しないこと
  （詰め込み＝容量を共有して多重化する世界 vs 台数を一緒に刻む世界）。

#### 6.2.3 Kim, Ruggiero, Atienza, Lederberger (2013) — abstract のみ（検索スニペット）
"Correlation-aware virtual machine allocation for energy-efficient datacenters", *DATE 2013*, pp.1345–1350。
URL: https://ieeexplore.ieee.org/document/6513723
- 要点: VM 間の**コア利用率の相関**を統合に使い、サーバのピーク利用率を下げる。既存の相関考慮法比で電力最大 13.7% 減、QoS 15.6% 改善。
- **本研究との関係: 背景。** 6.2.1 と同じ分類（時間相関で VM を詰める）。

### 6.3 観点(2)(4)(5) マイクロサービス／Pod／オートスケール

#### 6.3.1 AdaScale — Chen, Islam, Read, Buyya (2026) — abstract＋HTML版の要約のみ（全文は未精読）
"ADASCALE: An Adaptive Scaling and Placement Framework for Microservices Under Dynamics", arXiv:2607.15681 (2026-07-17)。
URL: https://arxiv.org/abs/2607.15681
- 要点: 呼び出しグラフ（分散トレース）から**サービスごと・エッジごとの需要**を作り、**リクエスト型（ルート操作）の配合 π(t) が変わる**状況で
  SLO を満たすレプリカ数を決めるオートスケール＋配置。DeathStarBench Social Network、16 VM のクラウド-エッジ K8s、遅延注入。
  ベースライン: K8s HPA と NetMARKS_Scale。
- 需要推定は回帰ではなくエッジ統計の集計（CPU_demand_s ≈ R_in·W_in/1000）。**Pod 同居は扱わない**（HTML 版要約で確認、限界節も多アプリ未検証）。
- **本研究との関係: 相補的／観点(5)の最近接。** 「リクエスト型の配合が変わる」を明示的に扱う点が近いが、
  目的は**個々のサービスの台数決定と配置**であり、**どのサービスを同居させるか**の選択ではない。HPA の整数台数ずれによる予約枠の損も扱わない。
  引用して差分（同居の相手選び vs 台数・配置決定）を明示するとよい。全文未読のため引用前に精読を。

#### 6.3.2 Ghemawat, Grandl, Petrovic, Whittaker, Patel, Posva, Vahdat (2023) — abstract／検索要約のみ
"Towards Modern Development of Cloud Applications", *HotOS 2023*. URL: https://sigops.org/s/conferences/hotos/2023/papers/ghemawat.pdf
- 要点: アプリを論理的モノリス（コンポーネント集合）として書き、**分割・同居・複製の決定を実行時が自動で行う**。最大 15× 低遅延、9× 低コスト（自己評価）。
- **本研究との関係: 相補的（観点(2)）。** 同居の決定を自動化する主張だが、同居の基準は通信コスト削減が中心（要約範囲）で、
  HPA の整数台数や需要の向きは扱わない（未精読のため断定は避ける）。Service Weaver の祖。「モノリス化の動機」の引用先。

#### 6.3.3 Fusionize / Fusionize++ / Konflux（FaaS の関数融合）— abstract のみ
- Schirmer, Scheuner, Pfandzelter, Bermbach, "Fusionize++: Improving Serverless Application Performance Using Dynamic Task Inlining and
  Infrastructure Optimization", *IEEE Trans. Cloud Computing* (DOI 10.1109/TCC.2024.3451108), arXiv:2311.04875。
  細粒度関数の融合で遅延・コスト 35% 超削減。実行時監視で融合構成を動的に調整。
- Kowallik, Schirmer, Bermbach, "Konflux: Optimized Function Fusion for Serverless Applications", arXiv:2601.11156 (2026-01)。
  融合構成を局所エミュレートして評価。最適構成は課金モデルに強く依存。
- **本研究との関係: 相補的／類比。** 「細かい単位を同じ実行単位にまとめると通信オーバーヘッドが減る」点は同じ主題の別基盤（FaaS）。
  FaaS は課金が実行時間比例でスケールが関数単位自動のため、**HPA の整数台数・予約枠の損**という本研究の損の機構は無い。
  相手選びの基準は呼び出しパターン（通信）で、需要の向きではない（abstract 範囲）。

#### 6.3.4 Erms — ASPLOS 2023 — abstract（検索要約）のみ
"Erms: Efficient Resource Management for Shared Microservices with SLA Guarantees", *ASPLOS 2023*. DOI: 10.1145/3567955.3567964（ACM 検索ヒット URL 由来、本文未取得）
- 要点: 複数オンラインサービスが**共有するマイクロサービス**を、遅延を負荷・資源・干渉の区分線形関数で表し、優先度スケジューリングで SLA を守りつつ資源を 1.6× 削減。
- **本研究との関係: 背景。** 「サービス（リクエスト型）ごとに異なる負荷パターンが 1 つのマイクロサービスに乗る」点は ρ の問題意識に近いが、
  同居の相手選びではなくマイクロサービス単位のスケールと優先度制御。

#### 6.3.5 その他（背景。全文未精読）
- PEMA — Hossen, Islam, Sunny, Ahmed, "Practical Efficient Microservice Autoscaling with QoS Assurance", arXiv:2202.00057。
  CPU 利用率とスロットリングだけで動き、**負荷レンジごとに**資源配分する。検索スニペット範囲。背景（C 群）。
- DeepScaler — Meng, Song, Tong, Pan, Yu, arXiv:2309.00859 (ASE 2023)。依存関係を学習して関連サービスを同時スケール。
  評価で**リクエスト型の重みを変える**。abstract のみ。背景（C 群）。
- Sinan — arXiv:2105.13424。リクエスト型（Compose-Post 等）で重さが違うことに触れる。書誌詳細は未確認。背景。
- Dashtbani & Tahvildari, "Key Considerations for Auto-Scaling: Lessons from Benchmark Microservices", arXiv:2510.02585 (2025-10)。
  Sock-Shop で各種スケーラを比較。abstract のみ。背景（C 群）。

#### 6.3.6 観点(4) マルチコンテナ Pod × HPA
- 公式資料のみ: Kubernetes KEP-1610「Container resource autoscaling」
  https://github.com/kubernetes/enhancements/blob/master/keps/sig-autoscaling/1610-container-resource-autoscaling/README.md
  Resource 型メトリクスは Pod 内全コンテナの使用量合計÷要求量合計の平均で、サイドカーとアプリの使用が連動しないと不適切、という
  動機が書かれている（検索要約）。これは §4 D 群（ContainerResource）の一次資料。**KEP 本文は未精読。**
- 査読論文で「同居によりスケール粒度が粗くなる」ことを扱うものは、WebSearch 3 クエリ（下記）では**ヒットなし**。
  "Addressing QoS in Kubernetes Pods Autoscaling" (Olana ほか, QualITA 2025, CEUR Vol-4080 paper1) は原典を取得して確認したが、
  HPA/KPA の一般的な限界（予測型スケールへの展望）の立場論文で、サイドカー・マルチコンテナ Pod の語は本文に出ない（grep で 0 件）= **無関係**。

### 6.4 検索の記録 (2026-10-09, WebSearch のみ)
- "regression-based approximation of CPU demand transaction mix multi-tier web application Zhang Cherkasova" → Zhang/Cherkasova 2007-08 が上位、Stewart & Shen NSDI05 も出る。
- "workload-aware request-type aware autoscaling microservices request mix CPU demand" → PEMA, GRAF, Sinan, AWARE。**同居との結合は 0 件**。
- "correlation-aware VM consolidation workload correlation peak co-placement" → Verma 2009, Meng 2010, Kim 2013, ScalCCon。
- "microservice merging consolidation co-location demand correlation Kubernetes pod HPA sidecar scaling granularity" → サーベイ・ブログのみ。
- "microservice placement container co-location load correlation aware scheduling Kubernetes ..." → ノード配置（Pod をどのノードへ）の研究ばかり = 本研究の「Pod 内同居」とは別軸。
- "multi-container pod Horizontal Pod Autoscaler sidecar ..." → 公式ドキュメント・ブログ・KEP のみ。査読論文なし。
- "which microservices to co-locate in the same container pod ..." → ブログのみ。
- "microservices co-location same pod scaling together replica coupling ..." → 特許・ブログのみ。
- 出なかったもの（空白の根拠）: 「同居する相手を、サービス別のリクエスト型応答係数の一致で選ぶ」「同居による HPA 台数ずれ（replica coupling）を定量」。
  ※いずれも WebSearch の範囲。Google Scholar / IEEE / ACM DL の横断は未実施。

### 6.5 観点別の判定と引用候補
| 観点 | 判定 | 近い論文 | 違い |
|---|---|---|---|
| (1) 配合→需要の回帰 | 手法は既出（背景） | Zhang/Cherkasova 2007-08、Stewart&Shen 2005 | 相手選びや HPA に使っていない |
| (2) 通信量以外の同居基準 | 空白（未発見） | ICTer 2022、Ghemawat 2023、Fusionize | 基準は通信/呼出パターンのみ |
| (3) 相関で詰める | 概念は既出（背景） | Verma 2009、Meng 2010、Kim 2013 | 時間相関 vs 配合への応答。向きが逆（ずれた相手ほど得 vs 揃った相手ほど損なし） |
| (4) マルチコンテナ Pod × HPA | 空白（査読論文未発見） | KEP-1610（公式） | 論文として扱うものなし |
| (5) リクエスト型を使うオートスケール | 近接あり（相補） | AdaScale 2026、PEMA、DeepScaler | 台数・配置の決定。同居の相手選びではない |

**引用上位（優先順）:**
1. Stewart & Shen, NSDI 2005（原典確認済。「分離でプロファイル→線形回帰→配置を予測」の祖）
2. Zhang, Cherkasova ほか, ICAC 2007 / Cluster Computing 2008（配合→CPU 需要回帰の代表。※引用前に原典 PDF 確認）
3. Verma ほか, USENIX ATC 2009（相関を統合に使う先駆。原典確認済）
4. Chen ほか, AdaScale 2026（配合変動×マイクロサービスの最近接。差分明示のため。全文精読が必要）
5. Meng ほか, ICAC 2010 または Spinner ほか 2015（多重化の向きの対比／推定の共線性の議論のどちらかを選択）

**新設分類**: 「E群 = 需要モデル／相関統合（背景）」を A〜D に追加（上記 6.1, 6.2）。
**残タスク**: Zhang/Cherkasova の原典PDF精読、AdaScale 全文精読、IEEE/ACM DL 横断検索、Google Scholar で
"transaction mix" × "microservices" × "co-location" の前向き引用（Cited by）追跡。

---

## 7. Sock Shop を使う論文の負荷シナリオ調査 (2026-10-19)

**目的**: 2 つ目のアプリ Sock Shop (Weaveworks microservices-demo) の自作 k6 シナリオ (`sockshop/k6/sockshop.js`: 購入型 = login → POST /cart → POST /orders → DELETE /cart、
閲覧型 = GET /catalogue?size=6&page=n → GET /catalogue/{id}、開ループ constant-arrival-rate で配合を振る) が査読で「恣意的」と言われないための根拠、
あるいは合わせるべき標準があるかを判断する材料。
**方法**: 上流 `microservices-demo/load-test` の原典 (GitHub raw) を取得し、arXiv/著者サイト/EuropePMC の本文を `pdftotext` で抽出して実験節を grep・精読した。
下表の「確認度」は **★本文確認 (2026-10-19)** = 原典本文の該当節を読んだ / **abstract・検索要約のみ** = 本文未確認。**記述なし** = 本文を読んだ上で書かれていなかったもの (推測で埋めていない)。

### 7.1 上流の負荷生成 (microservices-demo/load-test) ★原典確認 (2026-10-19)
- 出所: https://github.com/microservices-demo/load-test (`locustfile.py`, `runLocust.sh`, `Dockerfile`)。最終コミット 2023-12-05 "Add deprecation notice"、内容の実質更新は 2017 年。**DEPRECATED**。
  本リポジトリの `sockshop/upstream/manifests-loadtest/loadtest-dep.yaml` は、このイメージ (`weaveworksdemos/load-test:0.1.1`) を `replicas: 2` で常時回す Deployment。
- **シナリオは 1 本だけ** (`@task` が 1 つ、重み付けなし、閲覧型/購入型の区別なし)。1 周 = **9 リクエスト**を毎回この順で叩く:
  1. `GET /catalogue` (JSON を取り、ランダムに 1 商品の id を選ぶ) → 2. `GET /` → 3. `GET /login` (Basic 認証、**固定ユーザ user:password**) → 4. `GET /category.html` →
  5. `GET /detail.html?id={id}` → 6. `DELETE /cart` → 7. `POST /cart` ({id, quantity:1}) → 8. `GET /basket.html` → 9. `POST /orders`。
  (`/`, `/category.html`, `/detail.html`, `/basket.html` は front-end の静的ページ。バックエンドを使うのは catalogue / user / carts / orders(→payment, shipping)。)
- **閉ループ**: Locust の `HttpLocust` で `min_wait = 0, max_wait = 0` (待ち時間なし)。前の周が終わったら即次の周。到着率は応答時間で決まる (開ループではない)。
- **規模**: `runLocust.sh` の既定は clients=2, requests=10、`--hatch-rate=5 --no-web`。`loadtest-dep.yaml` では `--clients 5 --hatch-rate 5 --num-request 100` を `while true` で回し、Pod 2 個 (= 同時 10 クライアント程度)。
  ユーザ数・req/s の「標準値」は上流には無い。
- **注意 (本研究への含意)**: ①全クライアントが同一ユーザなのでカートを共有する (そのため毎周 DELETE /cart を先頭付近で入れている)。②買い物 1 周に閲覧が混ざっている (閲覧/購入の分離・配合の概念がない)。
  ③`/orders` はカートが空だと失敗しうる等、上流自身が「負荷試験」より「結合テスト」を意図している (README の題が "Load / Integration Tests")。

### 7.2 論文ごとの表 (Sock Shop を使うもの 17 本 + 周辺 2 本)
凡例: 開/閉 = 開ループ/閉ループ。「—」= 記述なし。

| # | 論文 (略称) | 年 | 会議/誌 | 負荷ツール | 開/閉 | シナリオと配合 | 負荷パターン | 規模 | 対象サービス | 出典の節 | 確認度 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Avritzer et al. "Scalability Assessment of Microservice Architecture Deployment Configurations" | 2020 | J. Syst. Softw. 165 (110564) | Faban + BenchFlow (PPTAM の前身) | 閉 (ユーザ数 + 指数分布の think time) | **3 種のユーザ型を配合: visitor 40% / buyer 30% / order visitor 30%** (許容偏差 5%)。Table 5 に 19 種のリクエスト (home, login, getCatalogue, cataloguePage, getItem, addToCart, createOrder, getOrders ...) と型別の発生数 | 運用プロファイル (動画配信 / Wikipedia) の頻度に合わせた「ユーザ数の段階」。ramp-up 1 分 + 定常 30 分 | 最大 300 ユーザ (運用プロファイルを最大 300 ユーザにスケール) | cart のレプリカ・RAM・CPU シェアを振る (「ほとんどのリクエストが cart に向かう」) | §4.5「Design of Synthetic User Behavior」, §4.6, Table 5 | ★本文確認 (著者プレプリント PDF) |
| 2 | Camilli & Russo "Modeling Performance of Microservices Systems with Growth Theory" | 2022 | Empir. Softw. Eng. 27 | PPTAM (+ Faban 部) | 閉 (think time あり) | **上と同じ 40/30/30** (Visitor / Buyer / Order visitor)。think time は指数分布、平均 1〜5 秒 | 60 秒 ramp-up + 30 分定常。Mirai bot で乱数的にユーザ数を揺らす追加負荷 | 基準 2 ユーザ → 目標 100 同時ユーザ (+ bot 256 スレッド 20 分) | 最も叩かれる getCart を複製 | 「In-vitro experiment」節 (EuropePMC 本文) | ★本文確認 (EuropePMC XML) |
| 3 | Rahman & Lama "Predicting the End-to-End Tail Latency of Containerized Microservices in the Cloud" | 2019 | IEEE IC2E 2019 | Locust | 閉 (同時クライアント数) | **2 つのワークフロー (orders / cart) を別々に評価**。配合なし | 一定。クライアント 5〜50 を掃引、総リクエスト 50000 固定。予測評価は 30 クライアント・SLO p95 240 ms | 5〜50 クライアント | frontend / orders / carts の Pod 数と CPU 利用率、CPI | §III-B Workloads, §V-A | ★本文確認 (著者 PDF) |
| 4 | Buzato "The Impacts of Microservice Grouping into Containers" (**同居系**, 7.3 参照) | 2025 | 修士論文 (USP IME) | Locust (上流スクリプト流用) | 閉 | 上流型の 8 ステップ 1 本 (home → login → category → detail → addToCart → cart → order → delete cart)。配合なし | 10 分: 前半 5 分で新規ユーザを追加 (spawn)、後半 5 分は最大人数を維持 | **300 / 2400 / 4500 ユーザ** (spawn 1 / 8 / 15 人/s)。Amazon / Mercado Livre の利用者数 (Similarweb) から換算 | アプリ全体 (8 マイクロサービスを束ねる) | §4.1.2, §4.2.2, Table 4.4 | ★本文確認 (PDF 全 120 頁) |
| 5 | Sachidananda & Sivaraman "COLA: Collective Autoscaling for Cloud Microservices" | 2021 (arXiv v3 2022) | arXiv:2112.14845 (掲載先は arXiv 本文に記載なし) | Locust (クラスタ外 VM から) | 閉に近い (コネクションごとに **2 秒ごとに操作を 1 つ無作為抽出**。接続数 ∝ req/s。2 秒でクライアント側タイムアウト) | 「固定分布から操作を抽出」。Sock Shop は 5 操作と記載 (Table 2) だが**配合の中身は記述なし** | 4 種: 定数 / 日周 / 未知の配合 / 交互の定数。各レート 10〜15 分 | Sock Shop は 200〜500 req/s で学習、300/400 users の評価行あり (Appendix Table 17) | Sock Shop は 14 サービス中 9 を自動スケール | §5.1 Workloads, App. 8.2, 8.16 | ★本文確認 (arXiv PDF) |
| 6 | Hossen, Islam, Ahmed "PEMA: Practical Efficient Microservice Autoscaling with QoS Assurance" | 2022 | HPDC '22 (DOI 10.1145/3502181.3531460) | **記述なし** | — | **記述なし** (SLO 250 ms のみ) | 一定 (225, 700 req/s 等) と、Wikipedia のパターンを 200〜1100 req/s に写した 36 時間 | 200〜1100 req/s | 全サービスの CPU 配分 | §5 Evaluation「Extended execution」 | ★本文確認 (arXiv)。ツール名は本文に出ない |
| 7 | Nunes et al. "Self-adaptive, Requirements-driven Autoscaling of Microservices" (MS-RA) | 2024 | SEAMS 2024 | Apache JMeter | 閉 (ユーザ数指定) | **記述なし** (login 等と思われるが本文に明記なし) | 30 分を 5 分刻みの段階: 10 → 20 → 30 → 10 → 30 → 20 ユーザ | 10〜30 ユーザ (ネットワーク飽和を避ける旨) | front-end を複製し、業務ロジック側のスケールを見る | §3「Study subject / Analysis procedure」 | ★本文確認 (arXiv) |
| 8 | Dashtbani & Tahvildari "Key Considerations for Auto-Scaling: Lessons from Benchmark Microservices" | 2025 | arXiv:2510.02585 | Locust | 記述なし (トレース駆動) | **/login サービスのみ** (front-end → user → carts の連鎖) | **WorldCup98** トレース、10 時間 | 記述なし (トレース形状のみ) | front-end / user / carts | §V「Evaluation Setup」(Workload Generation) | ★本文確認 (arXiv) |
| 9 | Dashtbani & Tahvildari "STaleX" | 2025 | arXiv:2501.18734 | Locust | 記述なし | /login のみ (上と同じ連鎖: front-end, user, user-db, carts, carts-db) | WorldCup98 | 記述なし | 同上 | §II (motivating exp.), §IV-A | ★本文確認 (arXiv) |
| 10 | Xie et al. "ScalerEval" | 2025 | arXiv:2504.08308 (4 頁) | Locust (+ Istio Gateway) | 記述なし (CSV でユーザ数の形を指定) | **記述なし** | **Wiki-Pageviews (2015-03-16)** の 20 分 | 最大同時ユーザ 740 | Online Boutique と Sock Shop の両方 | §IV-A「Benchmarks and Workloads」 | ★本文確認 (arXiv) |
| 11 | Hu et al. "LSRAM" | 2024 | Software: Practice and Experience (arXiv:2411.11493 の journal_ref) | Locust | 記述なし | **記述なし** | **Alibaba 2022 トレース**を req 数に換算。急変動版は最大振れ幅 700 req/s | 〜数百 req/s | 重要連鎖 (LLP グラフ) | §5.1 Experimental Setup | ★本文確認 (arXiv) |
| 12 | Wen et al. "StatuScale" | 2024 | ACM TAAS 2024 (arXiv:2407.10173 の journal_ref) | Locust | 記述なし | **記述なし** | **Alibaba cluster-trace-v2018** の CPU を QPS に写す | 記述なし | Sock Shop (8 サービスと記述) と HotelReservation | §4.1 | ★本文確認 (arXiv) |
| 13 | Hu et al. "MSARS" | 2024 | IEEE ISPA 2024 (arXiv:2409.14953) | 「load generators」(ツール名なし) | 記述なし | 記述なし | Alibaba 2022 データ | 記述なし | 5 本のチェーン、10 版 | §5.1 | ★本文確認 (arXiv)。ツール名なし |
| 14 | Song et al. "ChainsFormer" | 2023 | ICSOC 2023 (arXiv:2309.12592) | Locust | 記述なし | 観測された負荷の**サービス別割合**: front-end 45.5% / orders 22.7% / carts 22.7% / catalogue 5.7% / random item 3.4% (※生成側の配合ではなく観察。出所不明) | Alibaba trace を 10 段階の CPU 水準に離散化。動機実験は 0→110 req/s を毎分 +10 | 〜110 req/s (動機実験) | チェーン単位 (front-end → catalogue → payment 等) | §3 (Workload Generator)、§5 Performance Evaluations | ★本文確認 (arXiv) |
| 15 | Bai, Islam, Xu, Buyya "ORACL" | 2026 | arXiv:2602.05292 (メタデータの DOI 10.1109/TSC.2026.3707982、到達未確認) | Locust (分散構成) | 記述なし | 記述なし | Alibaba trace 由来 | 記述なし | Sock Shop + Train Ticket | 実験設定の節 | ★本文確認 (arXiv) |
| 16 | Pham, Ha, Zhang "BARO" | 2024 | FSE 2024 (arXiv:2405.09330) | 「各システム付属の負荷生成器を、全サービスを叩くよう調整」 | 記述なし | **記述なし** (全サービスを叩く) | 記述なし | 100〜200 同時ユーザ、40〜50 req/s (同一論文内で 2 通りの記述) | RCA: carts, catalogue, orders, payment, user に故障注入 | §4.1 | ★本文確認 (arXiv) |
| 17 | Pham, Ha, Zhang "RCA ... How Far Are We?" | 2024 | ASE 2024 (arXiv:2408.13729) | 同上 (付属の生成器を調整) | 記述なし | 記述なし | 一定 | 100〜200 同時ユーザ | RCA | §3.1.2 | ★本文確認 (arXiv) |
| 18 | Pham et al. "RCAEval" | 2024 | arXiv:2412.17015 (掲載先は arXiv メタデータになく未確認) | 記述なし | 記述なし | 記述なし | 乱数負荷 | **10〜200 req/s** | RCA | "Telemetry Data Collection Process" | ★本文確認 (arXiv) |
| 19 | Xin, Chen, Zhao "CausalRCA" | 2022/2023 | J. Syst. Softw. (arXiv 側メタデータ DOI 10.1016/j.jss.2023.111724) | Locust | 記述なし | 記述なし | 記述なし | 記述なし | RCA (13 サービス) | §5.1 Testbed | ★本文確認 (arXiv) |
| — | Zafar, Adriano, Giese "Interference-Aware Cross-Application Placement" (**配置系**) | 2026 | arXiv:2606.25922 | **k6** (Istio Gateway 経由、Sock Shop / TeaStore / Bookinfo を同時に) | 記述なし | 記述なし (「急増シナリオ」を k6 で) | 負荷スパイク。4 回 × 乱数種 | 記述なし | Pod の**ノード**間配置 (Pod 内同居ではない) | §IV | ★本文確認 (arXiv)。k6 の VU 数・配合は本文になし |
| — | Grambow, Meusel, Wittern, Bermbach "Benchmarking Microservice Performance: A Pattern-based Approach" (方法論) | 2020 | ACM SAC '20 (DOI 10.1145/3341105.3373875) | 自作の Workload Generator (OpenAPI から生成) | — | Sock Shop は **user サービスの /customers と /register のみ**。CRE/LST/DEL パターン | 小さな負荷 (結果の絶対値は無関係と明記) | AWS EC2 に Worker 2 台 × 5 スレッド | user のみ | §4.2, §4.3 Step 2/6 | ★本文確認 (著者 PDF)。アプリ全体の負荷ではない |

補足: 同分野の IJACSA 2024 "Towards a Framework for Optimized Microservices Placement in Cloud Native Environments" (Driss ら, Vol.15 No.7) も Sock Shop + Locust と書くが、
負荷の中身は「シェルスクリプトで作った負荷」としか書かれず**記述なし**。★本文確認 (著者 PDF) だが負荷の参考にはならない。

### 7.3 同居・グルーピングに直接関係する 1 本 — Buzato (2025) の位置づけ【相補。最優先で読んだ】
**Buzato, F. H. L.** "The Impacts of Microservice Grouping into Containers: An Experimental Analysis of the Benefits and Limits of this Approach."
Master's thesis, Institute of Mathematics and Statistics, University of São Paulo, 2025 (defense 2025-02-14; CC BY 4.0)。
URL: https://teses.usp.br/teses/disponiveis/45/45134/tde-26062025-090557/publico/Dissertacao_FernandoHenriqueLaureanoBuzato_corrigida.pdf
**★原典PDFで確認 (2026-10-19、全 120 頁を pdftotext し第 4〜7 章を精読)**。コード: https://github.com/fernandohlb/microservices-container-grouping (論文中の記載、未アクセス)。
- **何を比べたか (ベースライン)**: 「Benchmark」= Sock Shop 既定の **1 マイクロサービス = 1 コンテナ** (14 コンテナ = 8 サービス + 6 インフラ)。
  対して 4 シナリオ: Benchmark / **All-in-one** (8 サービスを **1 つのコンテナイメージ** に詰める) / **By-dependencies** (orders+payment+shipping を 1 コンテナ) / **By-stack** (Java / Go / Node.js の言語別に 1 コンテナ)。
  → ベースラインは本研究 (分離 Pod) と**同種**。ICTer 2022 のような「1 サービス 1 ホスト」ではない。
- **重要な違い (衝突しない理由)**: 論文自身が **「Kubernetes の Pod 内グルーピングは評価しない」と明記** (§4.2.2 末尾、§7.4.1 Limitations)。同居の単位は
  「**1 コンテナ内に複数サービスのプロセスを詰める**」(サービスを再コンパイル・再設定して localhost 通信化)。本研究の「Pod 内の別コンテナ + localhost」とは別物。また**インフラ (DB, MQ) は束ねない**。
- **測定環境**: AWS EKS (K8s 1.22, Docker 20.10)、t3.xlarge (4 vCPU / 16 GB)。**シナリオごとにノード 1 台** (HPA 無しでは 1 ノード = ノードをまたぐ通信なし。HPA 有りは各シナリオ 2 ノード)。Istio / overlay / CNI の語は本文に出ない (grep 0 件) = **記述なし**。localhost の語も本文に出ず、コンテナ内通信の実装詳細は未確認。
- **指標**: requests/s、応答時間、failures/s、CPU (cores)、メモリ、ネットワーク (Mb/s)、ディスク、月額コスト、可用性、スケール率。
  **CPU は「ノード/全体の絶対量 (コア)」で、リクエストあたりではない。softirq は測っていない。** 結果は「束ねるほど CPU は**増える**」(= スループットが増えるため、と著者は解釈、§5.2)。
- **HPA 実験**: 1〜4 Pod、**CPU/メモリ 150% (requests 比)** をしきい値 (通常の 50〜70% ではなく 150%)。ここで All-in-one のスループット +66%、By-stack +33% (中負荷 2400 ユーザ)。HPA 無しでは +18% / +10%。
- **標本**: 各条件 6 サイクル、箱ひげ図と中央値のみ (統計検定は行わず、正規性が無いため)。
- **主張の範囲 / 限界 (著者の記述)**: E コマース 1 種だけ。Pod 内同居は対象外。All-in-one は「リソース競合・保守性・独立スケール不可」が欠点で、**ハイブリッド (束ね + 独立スケール) を推奨**。
- **静的/動的**: 束ねる単位は静的に決める (4 シナリオ固定)。選択基準は「同期通信の依存関係」「言語スタック」という定性的な基準。
- **位置関係: 相補 (B 群 + 同居の定量化)**。「束ねると通信オーバーヘッドが減りスループットが上がる、HPA と組むと効果が大きい、但し粒度が粗くなり独立スケールを失う」という**定性的な主張は本研究と同方向**で、査読者が「既に言われている」と言う余地がある。
  本研究が埋めるのは: ①Pod 内コンテナ同居 (K8s の単位) の話、②softirq/リクエストという通信コストの直接指標 (Buzato は絶対 CPU でスループット増に混ざる)、
  ③予約枠 (requests) の粒度損を HPA 台数で測ること、④「どの相手と束ねるか」を ρ・需要の高さで選ぶ条件 (Buzato の基準は依存関係・言語の定性的分類のみ)、⑤開ループで負荷を決める (Buzato は Locust 閉ループで、スループット差が混ざる)。
  **引用して差分を明示するのが安全** (Related Work に必須級)。
- 同著者の先行 2 本 (thesis 参考文献から。**本文未確認**、書誌は thesis の記載のみ): Buzato, Goldman, Batista, "Efficient resources utilization by different microservices deployment models," IEEE NCA 2018, pp.1–4 (マイクロサービスの「層」を 1 コンテナに束ねるとネットワーク消費 99% 減);
  Buzato & Goldman, "Optimizing microservices performance and resource utilization through containerized grouping: an experimental study," SBAC-PADW 2023 (IEEE), pp.115–122 (上記 §4.2.3 の HPA 無し実験の論文版)。

### 7.4 傾向のまとめ
**(a) 標準シナリオはあるか → 「論文が合わせている標準」は無い。ただし 2 系統の慣習がある。**
1. **性能工学系 (PPTAM / BenchFlow / Faban)**: Avritzer 2020, Camilli & Russo 2022 が **visitor 40% / buyer 30% / order visitor 30%** の「behavior mix」を使う。出典は Vögele ら (WESSBAS, SoSyM 2018, DOI 10.1007/s10270-016-0566-5; 検索要約で書誌のみ確認、**本文未読**)。
   これが「Sock Shop の配合を明示した」ほぼ唯一の定番。ただし閉ループ + think time で、配合は固定 (振らない)。
2. **オートスケール・RCA 系 (Locust)**: 負荷「形」(トレース) が主役で、**リクエストの中身はほとんど書かれない**。トレースは WorldCup98 (Dashtbani 2 本)、Wikipedia (PEMA, ScalerEval)、Alibaba (LSRAM, StatuScale, MSARS, ChainsFormer, ORACL) の 3 種。
   RCA 系は「Sock Shop 付属の負荷生成器を、全サービスを叩くように調整」(BARO, RCA how far) = 上流 locustfile の流用。
   → **上流 locustfile (7.1) が事実上のデフォルト**だが、論文は中身を書かないので、標準とは言えない。
**(b) 購入/閲覧の配合を変える論文はあるか → Sock Shop では見つからなかった。** 配合を扱うのは Avritzer/Camilli (固定 40/30/30)、Rahman & Lama (orders と cart を別ワークフローとして別々に評価) のみ。
   配合を**振った**例は COLA の **Online Boutique** (購入頻度を低/3 倍で学習し 2 倍で評価。Sock Shop では交互定数のみ。COLA §5.3 付近、App. 8.2)。つまり「購入頻度を変えて評価」は OB では前例があるが Sock Shop では見つからない。
**(c) 開ループ使用例は → 明示的な開ループは 0 本。** Locust 既定は閉ループ。「req/s を指定」と書く論文 (PEMA, LSRAM, StatuScale, ChainsFormer, ScalerEval) でも、閉ループか開ループかは本文に書かれていない。
   COLA は 2 秒ごとの無作為抽出 (接続数 ∝ req/s) で、閉ループではなく固定周期に近いが、これも開ループ (到着過程が応答と独立) と明記はしていない。
   k6 を使うのは Zafar 2026 (配置、詳細記述なし) だけ。JMeter は MS-RA のみ。wrk / Gatling / Vegeta は見つからなかった (wrk2 は DeathStarBench 側で使われる。Buzato §4.2.1 の記述)。
**(d) 負荷の大きさ**: 数十ユーザ (MS-RA 10〜30、Rahman 5〜50)、100〜300 ユーザ (Avritzer、Camilli、RCA 系 100〜200)、数百 req/s (COLA 200〜500、PEMA 200〜1100、LSRAM 振れ幅 700)、
   数千ユーザ (Buzato 4500、ScalerEval 740)。単一ノード 1 台の本研究の規模 (購入 5〜40 周/s、閲覧 25〜200 周/s) は、PEMA/COLA の req/s 規模より小さく、Avritzer/Camilli の規模には近い。
**(e) どのサービスを観測するか**: front-end / user / carts / catalogue / orders が主役。/login 経路 (front-end → user → carts) を使う Dashtbani 2 本、cart を複製する Avritzer/Camilli、orders/carts/front-end の Pod 数を振る Rahman がある。
   → 購入型に login・cart・orders を含める自作シナリオは慣習と整合する。**閲覧型を catalogue 中心にするのも、上流 locustfile の getCatalogue/getItem と同じ経路**。

### 7.5 本研究の自作シナリオとの差と、査読への備え
- **近いもの**: 購入型 (login → POST /cart → POST /orders → DELETE /cart) は上流 locustfile の 6〜9 番 (DELETE /cart, POST /cart, POST /orders) と login に対応し、Avritzer の buyer (home → login → catalogue → detail → addToCart → cart → createOrder) の骨格と同じ。
  閲覧型 (catalogue 一覧 → 商品詳細) は Avritzer の visitor (home → catalogue → details) から home を除いたもの。
- **差**: ①開ループ (constant-arrival-rate) — 先行研究は全て閉ループまたは記述なし。②購入型/閲覧型を**別シナリオとして到着率を独立に振る** (配合を連続的に振る) — Sock Shop では前例なし。
  ③静的ページ (/, /category.html, /basket.html 等) を叩かない — 上流・Avritzer は叩く (front-end の静的配信コストが入る)。本研究は API のみ。④ユーザごとにセッションを分ける (上流は固定 1 ユーザでカート共有)。
  ⑤Avritzer の order visitor (GET /orders で注文履歴) に相当する型を持たない。
- **査読の突きどころ候補と、手元でできる備え (推測を含む。判断は依頼者)**:
  1. 「標準でない」 → 上流が単一シナリオで配合の概念自体を持たないこと (7.1)、先行研究がシナリオの中身をほぼ書かない事実 (7.4a)、配合を明示した唯一の定番 (PPTAM 40/30/30) との対応表を Appendix に置けば足りる。
  2. 「配合 40/30/30 に合わせるべき」 → 合わせる場合は、visitor=閲覧型、buyer=購入型、order visitor=新規 (login → GET /orders) と対応づけ、既存の閲覧/購入比を 1 点だけ PPTAM の比に置く (ただし PPTAM は think time 付き閉ループで、req/s に直す際は「周/s」の換算が必要)。
  3. 「/index.html など静的ページを叩いていない」 → 静的配信は front-end の CPU に効くので、前面サービスの ρ に影響しうる。省略を明記し、必要なら感度確認 (静的ページ込み版を 1 点) が防御になる。
  4. 開ループの正当化は Sock Shop 先行研究からは得られない。本研究が Online Boutique で既に説明している理由 (閉ループの双安定) を再掲するのが筋。

### 7.6 検索の記録 (2026-10-19、WebSearch + arXiv/EuropePMC/著者 PDF 取得)
- 使った検索語 (すべて英語): "Sock Shop microservices autoscaling evaluation workload locust arXiv" / "Sock Shop benchmark Kubernetes HPA resource allocation workload JMeter" /
  "Sock Shop root cause analysis microservices fault injection locust load generator dataset" / "Sock Shop performance model microservices queueing workload mix browse buy" /
  "Sock Shop microservices Kubernetes container placement co-location evaluation load" / "Sock Shop layered queueing network model ... Locust catalogue cart orders" /
  "Sock Shop JMeter load test ... thread group users ramp-up" / "Sock Shop benchmark workload generator request mix OR browse OR buy scalability study" /
  "Grambow Benchmarking microservice performance pattern-based approach Sock Shop workload" / "Avritzer PPTAM Sock Shop ... behavior mix" / "Sock Shop Poisson arrivals OR open workload ..." /
  "Sock Shop Gatling OR k6 ... requests per second" / "merge microservices same pod OR container Sock Shop granularity consolidation latency evaluation locust" / "Sock Shop HPA CPU requests right-sizing ... wrk OR locust OR vegeta"。
- ヒット感触: 1 回の検索で 8〜10 件。Sock Shop 利用論文は多く (Locust が最多)、**負荷の中身を書く論文は少ない**。
  **出なかったもの (空白の根拠)**: ①Sock Shop + 開ループ/到着率指定 (Poisson, constant-arrival-rate) ②Sock Shop + wrk/Gatling/Vegeta ③Sock Shop + 購入/閲覧の配合を連続的に振る ④Sock Shop + Pod 内マルチコンテナ同居 + HPA。
  ※いずれも WebSearch の範囲で、Google Scholar / IEEE Xplore / ACM DL の横断は未実施。ACM DL 上の論文 (SAC'20, HPDC'22 等) は著者サイトか arXiv の PDF で読んだ。
- 未確認: 「Sock Shop を使った論文」の網羅性 (目安 10〜20 本は満たしたが、被引用側からの前向き追跡は未実施)。

### 7.7 次に読むべきもの (Sock Shop 負荷の観点)
1. Vögele ほか WESSBAS (SoSyM 2018, DOI 10.1007/s10270-016-0566-5) — 40/30/30 の配合の出所。本当に Sock Shop 用に導かれた値か、PPTAM 側で決めた値かを確認する。
2. Avritzer ほか PPTAM 系の他 2 本 (Avritzer 2019/2021、Camilli ほか JSS 2022 "Automated test-based learning and verification of performance models for microservices systems") — 配合を振っていないか確認。
3. Buzato & Goldman, SBAC-PADW 2023 — 本文を取得して、Pod 内でないこと・CPU 指標の扱いを原典で確認 (thesis 経由の孫引きのため)。
4. Aderaldo ほか "Benchmark requirements for microservices architecture research" (ECASE 2017) — Sock Shop が「代表的」とされる根拠。査読で標準性を問われたときの引用元 (書誌は検索要約のみ、本文未読)。

---

## 8. CPU 周波数の変動 (DVFS / ターボ / ガバナ) を実験でどう扱うか (2026-10-19)

**目的**: 本研究の測定 (単一ノード、i7-1260P = P4+E8 混在、ターボ最大 4.7 GHz、intel_pstate / powersave / EPP balance_performance) で、
負荷を足すとノード平均周波数が 1.4→2.8 GHz に上がり、閲覧を処理しないサービスの cgroup CPU 時間が −12〜−34% 減って見える (仕事量は同じ)、高負荷で周波数が頭打ちになると +2〜+12% 増える、
という現象が見つかった。HPA の利用率は「CPU 時間 ÷ requests」なので台数にも効きうる。対策候補は (a) 周波数固定 (performance + min=max)、(b) 固定せず記録して冷却待ち。
先行研究が (a)(b) のどちらをどう正当化しているかを集めた。
**方法**: 原典 PDF (USENIX / arXiv / 著者サイト / ACM 著者公開版) を取得して `pdftotext` で本文を抽出し、`turbo|DVFS|frequency|governor|C-state|hyper-thread|SMT|GHz` で grep、該当節を読んだ。
下表の確認度: **★本文確認 (2026-10-19)** = 原典本文の該当箇所を読んだ / **abstract・検索要約のみ** = 本文未確認 / **記述なし** = 本文を読んだ上で周波数の設定について書かれていなかった (推測で埋めていない)。
**群の位置づけ**: 全て **C 群 (背景)** または計測手法の引用。同居 × 周波数の衝突論文は無い (§8.7)。

### 8.1 論文ごとの表 (1) 方法節で周波数をどう扱っているか ★本文確認

| # | 論文 | 掲載 | 周波数の扱い (原文の趣旨) | 箇所 | 環境 | 型 |
|---|---|---|---|---|---|---|
| 1 | Gan et al. **DeathStarBench** | ASPLOS '19, DOI 10.1145/3297858.3304013 | "unless otherwise noted power management and turbo boosting are turned off" | §4 Architectural Implications 冒頭 Methodology (PDF 7 頁) | 20 台 2 ソケット Xeon (E5-2699v4 / E5-2660v3)、Ubuntu 16.04 | **無効化** (既定)。ただし周波数を RAPL で下げる感度実験 (Fig.12) も別に行い、QoS 違反が周波数低下で増えると報告 |
| 2 | Chen, Delimitrou, Martínez **PARTIES** | ASPLOS '19, DOI 10.1145/3297858.3304005 | "we enable hyperthreading and Turbo boosting"。Table 1 に "Default Frequency Driver: ACPI with the performance governor"。周波数を操作する実験では userspace ガバナで 1.2–2.2 GHz を固定 | §2 Table 1 (PDF 2 頁)、本文 "we enable hyperthreading and Turbo boosting" (PDF 3 頁) | Xeon E5-2699 v4 2 ソケット、LXC、kernel 4.14 | **ターボ有効 + performance ガバナを明記** (有効側の例) |
| 3 | Lo et al. **Heracles** | ISCA '15, DOI 10.1145/2749469.2749475 | 周波数を「干渉資源」として扱う。LC が単独・全負荷で出す周波数を「保証周波数」とし、TDP 近傍で LC コアの周波数が落ちたら BE コアを per-core DVFS で下げる。ターボは自然に起こる前提 | §2 / §4 Power subcontroller (PDF 2・7 頁) | Google 本番サーバ | **動的に保証** (固定ではない) |
| 4 | Maricq et al. **Taming Performance Variability** | OSDI '18, https://www.usenix.org/conference/osdi18/presentation/maricq | Intel では「標準の周波数スケーリング」と「ターボ無効 + performance ガバナ」の**両方**で測定し、構成の 1 軸として扱う。835 台・10,400 回 | §3 Methodology (PDF 4 頁) | CloudLab 実機 | **両方測って比較** (固定を推奨とは書いていない。分散を測る研究。grep ベースで確認、全文精読はしていない) |
| 5 | Fried et al. **Caladan** | OSDI '20, https://www.usenix.org/conference/osdi20/presentation/fried | "disabling TurboBoost, CPU idle states, CPU frequency scaling, and transparent hugepages" (低遅延の推奨設定に従う) | §7 Evaluation 冒頭 (PDF 10 頁) | Xeon サーバ | **無効化** (理由: 低遅延チューニングの慣行) |
| 6 | Ousterhout et al. **Shenango** | NSDI '19, https://www.usenix.org/conference/nsdi19/presentation/ousterhout | "To reduce jitter, we disabled TurboBoost, C-states, and CPU frequency scaling" | §7 Experimental setup (PDF 9 頁) | Xeon E5-2650v4 2.2 GHz | **無効化** (理由: ジッタ低減を明記) |
| 7 | Zhu et al. **Dissecting Service Mesh Overheads (MeshInsight)** | arXiv:2207.00592 (2022)。正式掲載先は未確認 | "We disable TurboBoost, CPU C-states and dynamic CPU frequency scaling to reduce measurement variance." | §5 冒頭 (PDF 7 頁) | CloudLab Xeon Gold 6142、Istio 1.13、Kubernetes。サイドカー有り | **無効化** (理由: 測定分散の低減)。**K8s + マイクロサービスの数少ない明示例** |
| 8 | Savasci et al. **PADS** | IGSC 2024, DOI 10.1109/IGSC64514.2024.00012 | "We disable hyperthreading and turbo boost because they affect the comparisons, regardless of the approach used. Moreover, we enable the performance governor of CPUFreq" | §V-A Testbed Setup (PDF 5 頁) | Xeon Silver 2×8 コア 2.1 GHz、LXC | **無効化 + performance ガバナ** (理由: 比較に影響) |
| 9 | Savasci et al. **SLO-Power** | CCGrid 2024, DOI 10.1109/CCGrid59990.2024.00025 | 電力研究なので powersave ガバナで最低周波数に落とす実験を**意図的に**行う。本文で「CPU 周波数・電圧の動的調整が CPU コアの性能を変えるため、弾力的スケーリングが必要コア数を正確に見積もれず過少/過剰割当になる」と課題に明記 | §II Challenges 2) "uncertain CPU performance"、§II (PDF 3 頁) | UMass サーバ、K8s 拡張 | **問題の存在を文章で指摘** (測定・補正はしていない)。【最も近い定性的記述】 |
| 10 | Hossen et al. **PEMA** (既出 §7、bib: hossen2022) | HPDC '22 | 周波数を固定するとは書かない。**評価で 1.8 GHz→1.6 / 2.0 GHz にクロックを変えると、SLO を満たす最小 CPU 割当が変わる**ことを Fig.19 で示し「周波数の変化は SLO を満たすのに必要な資源量を本質的に変える」と書く (適応性の実証として) | 評価の "Adaptability / Operating environment" (arXiv 版 11 頁) | 2×10 コア Xeon 4 ワーカ、K8s、Sock Shop | **周波数が必要資源量を変えることを逆手に取った実験**。【本研究の現象の裏付けに使える】 |
| 11 | Papadopoulos et al. **Methodological Principles for Reproducible Performance Evaluation in Cloud Computing** | IEEE TSE 47(8), 2021, DOI 10.1109/TSE.2019.2927908 | 自身の実験記述で "We deactivate hyper-threading … Dynamic frequency scaling is enabled as default and also further CPU-oriented features are not changed." 原則 P3 = 非既定設定を含む環境を**記述**せよ | §4 (PDF 8 頁)、§2 P3 | Xen / CloudStack、E5-2630v3 | **既定のまま + 記述** (有効側の例。方法論そのものは「固定の是非」でなく「記述と反復」を要求) |
| 12 | Hoefler & Belli **Scientific Benchmarking of Parallel Computing Systems** | SC '15, DOI 10.1145/2807591.2807644 | §4.1.1: 変動要因は可能なら固定、**固定できないなら乱択 (randomization)**。Rule 9 = 全ての変動要因とその水準・実験設定を文書化 | §4.1.1–4.1.2、Rule 9 (PDF 7 頁) | (HPC 一般) | **「固定できなければ乱択 + 文書化」の方法論的根拠** |

### 8.2 論文ごとの表 (2) 周波数の設定について**記述なし** (CPU 型番のみ) ★本文を grep したが該当語なし
- Zhang et al. **Sinan** (ASPLOS '21, DOI 10.1145/3445814.3446693): 付録 A.3.2 に Xeon E5-2660 v3 @2.60GHz のみ。ターボ・ガバナの記述なし。
- Qiu et al. **FIRM** (OSDI '20, https://www.usenix.org/conference/osdi20/presentation/qiu): §4 System Setup は 15 ノード (Xeon E5/E7 と IBM Power8/9)、Ubuntu 18.04 / kernel 4.15 まで。**§Limitations で「ハードウェア要因 (例: 省電力管理) は FIRM の範囲外」と明記**。周波数が SLO 違反の一因になりうることは認めて範囲外とした例。
- Gan et al. **Seer** (ASPLOS '19, DOI 10.1145/3297858.3304004): 周波数に関する記述なし (ヒットは「トレースの頻度」のみ)。
- Wang et al. **Autothrottle** (NSDI '24): EPYC 7763 / Xeon Silver 4216 とあるのみ (Azure VM を含むのでそもそも制御不能)。
- Smart HPA (arXiv:2403.07909)、Dashtbani (arXiv:2510.02585、bib: dashtbani2025)、Nunes SEAMS'24 (bib: nunes2024)、COLA (arXiv:2112.14845、GKE)、NotNets (arXiv:2404.06581): いずれも該当語なし。
- **傾向**: オートスケーリング / 資源管理 ML 系は**ほぼ何も書かない**。ターボ・ガバナを書くのは「遅延・オーバーヘッド・干渉を精密に測る」系 (Caladan / Shenango / MeshInsight / PADS / PARTIES / DSB)。
  今回確認した 12+7 本のうち**明示的に無効化 = 5 本 (DSB, Caladan, Shenango, MeshInsight, PADS)、明示的に有効 = 2 本 (PARTIES, Papadopoulos)、両方測定 = 1 本 (Taming)、記述なし = 10 本程度**。※母集団は私が選んだ論文なので割合は代表性を持たない (標本の偏りに注意)。

### 8.3 (論点2) 「CPU 時間ベースの利用率は周波数で変わる」ことの一次資料

| 資料 | 内容 (確認した原文) | 確認度 |
|---|---|---|
| Linux kernel doc **cgroup-v2** (https://docs.kernel.org/admin-guide/cgroup-v2.html, CPU の節) | "In all the above models, cycles distribution is defined only on a temporal base and it does not account for the frequency at which tasks are executed." `cpu.stat` は `usage_usec` 等 (時間)。→ **cAdvisor / HPA が使う CPU 使用量は周波数非考慮の「時間」であることの公式根拠** | ★原典(公式 doc の HTML)確認 2026-10-19 |
| Linux kernel doc **schedutil** (https://docs.kernel.org/scheduler/schedutil.html) | "consuming the CPU for 50% at 1GHz is not the same as consuming the CPU for 50% at 2GHz, nor is running 50% on a LITTLE CPU the same as running 50% on a big CPU." スケジューラの PELT 利用率は r_tot = r_dvfs × r_cpu で**周波数・コア種に不変化**される。x86 Intel は APERF/MPERF×P0 を f_cur に使う。**注意 (私の推論)**: この不変化はスケジューラ内部の util_avg の話で、cgroup の `usage_usec` や HPA の入力には適用されない | ★公式 doc を WebFetch の引用で確認 (本文全体は未読) |
| Gherdovich, LWN 記事 **Frequency-invariant utilization tracking for x86** (https://lwn.net/Articles/816388/) | Linux 5.7 で x86 の周波数不変利用率追跡。APERF/MPERF から operating_freq = max_freq×ΔAPERF/ΔMPERF。schedutil が intel_pstate powersave に並ぶ | WebFetch 要約のみ (記事全文は未精読) |
| **Zhang & Li, DVFS-aware CPU service time estimation method**, 浙江大学学報 46(4):725–733, 2012 (https://www.zjujournals.com/eng/EN/10.3785/j.issn.1008-973X.2012.04.022) | CPU サービス時間の回帰で、従属変数を CPU 利用率でなく **「平均周波数 × CPU 利用率」** にして DVFS の影響を補正。従来法は短いサービス時間で約 100% 偏る、既存の周波数測定ツールに 40% 超の誤差、と報告 | **abstract / ページ要約のみ (本文未読)**。マイクロベンチのみで検証。**本研究の「周波数で割り戻した仕事量」の最も近い先行例** |
| Gouicem et al. **Fewer Cores, More Hertz** | Intel の powersave ガバナはハードウェアが周波数を決める (既定)。コアが最低→最高周波数に上がるのに **29 ms (1.25→3.0 GHz)**、下がるのも数十 ms (周波数遷移遅延 FTL)。短い仕事は低周波数のコアで走る | ★本文確認 (§2 case study, §3, §4 前半) |
| Schöne et al. **Energy Efficiency Features of the Intel Alder Lake Architecture** | 本研究と同世代の Alder Lake (i9-12900K) で、周波数切替の遅延が P コアでは直前の切替からの経過時間に依存して 38.7 µs〜272 µs、E コアは依存しない。低消費電力状態では RAPL 電力測定が不正確 | ★本文確認 (§3.1 周波数遷移、PDF 3 頁) |
| Google **Borg (Tirmazi et al. 2020)** | Borg は CPU を物理コアでなく GCU (Google Compute Unit) で要求・計測。「1 GCU は艦隊のどのマシンでもほぼ同じ計算量を提供するべき」。クラウド事業者側の**CPU 正規化**の実例 | ★本文確認 (§Normalized CPU units, PDF 3 頁)。※GCU の換算が周波数変動まで含むかは書かれていない |
| Gregg, "CPU utilization is wrong" (opensource.com ブログ) | 利用率は「アイドルでない時間」で、メモリストールを含む。周波数にも触れるが主題は IPC | 検索スニペットのみ (ブログ。査読論文ではない) |

**ヒットしなかったもの (空白の根拠)**: 「K8s HPA の利用率 (CPU 時間 ÷ requests) が周波数変動で歪む」を**測定または補正した査読論文**は、下記 §8.8 の検索語で WebSearch の範囲では出なかった。
SLO-Power (定性的な指摘のみ) と PEMA (周波数を変えると必要割当が変わる実験) が最も近い。

### 8.4 (論点3) 異種コア (P/E, big.LITTLE) と CPU 時間・K8s

| 資料 | 内容 | 確認度 |
|---|---|---|
| Saez & Prieto-Matias, **Evaluation of the Intel Thread Director technology on an Alder Lake processor**, APSys '22, DOI 10.1145/3546591.3547532 | Alder Lake の 16 コアで SPEC CPU 16 本を同時実行すると、**Linux CFS では同一ワークロードの各アプリの完了時間が実行ごとに最大 2.3 倍ばらつく** (10 回、Linux 5.17 でも同様)。CFS は非対称を「ほぼ認識しない」。→ 「同じ仕事でも P/E のどこに載ったかで CPU 時間が変わる」ことの査読済み根拠 | ★本文確認 (§1, Fig.1a) |
| Schöne et al. ICPE '24 (上掲) | Golden Cove (P) と Gracemont (E) の周波数切替挙動が別。Thread Director の限界にも触れる | ★本文確認 (抜粋) |
| Linux kernel doc **intel_pstate** | hybrid プロセッサ (最大ターボ P-state、性能/電力特性等が異なる 2 種以上のコア) では HWP 必須。`performance` ガバナ (HWP 有効時) は EPP を 0 にするだけ (= 周波数固定ではない)。`no_turbo`、`min_perf_pct` / `max_perf_pct` で範囲を制限できる | ★公式 doc を WebFetch の引用で確認。→ **「performance + min=max」で固定する手順の根拠** |
| Linux kernel / LWN 985293 "intel_pstate: Set asymmetric CPU capacity on hybrid systems" | hybrid で CPU 容量を非対称に設定し、利用率をコア間で整合的に計算できるようにするパッチ | 検索スニペットのみ (未読) |
| Noor et al., Kubernetes application performance benchmarking on heterogeneous CPU architecture, High-Confidence Computing 5(1):100276, 2025 | x86 vs ARM の**ノード間**比較。P/E 混在の単一ノードは扱わない。周波数・ガバナ設定の記述は本文 grep で該当なし | 本文 PDF を grep (周波数語なし)。精読はしていない |
| Dib & Metsch, Intent-Driven CPU Heterogeneity Management in Kubernetes, TechRxiv 2025-11-21 | Kubernetes の CPU 要求は性能でなく時間という問題意識、異種 CPU プロファイル選択の ML (LLM 推論、4 ノード)。 | **abstract のみ** (本文は 403 で取得不可) |
| Ou et al., Exploiting Hardware Heterogeneity within the Same Instance Type of Amazon EC2, HotCloud '12 / Leitner & Cito, Patterns in the Chaos, ACM TOIT 2016 (arXiv:1411.2429) | クラウドで同一インスタンス型でも CPU 型が違い性能が最大 60% / 20–30% 違う、という**ノード間**の異種性。P/E の**ノード内**異種性とは別 | 検索要約のみ (未読) |

**結論 (論点3)**: 「K8s の CPU 時間 / requests が P/E 混在ノードでどう歪むか」を扱った査読論文は見つからなかった。ノード内の異種性の効果を示す根拠は
Saez (CFS の実行間ばらつき 2.3 倍)、Schöne (P/E で周波数遷移が違う)、kernel doc (50% LITTLE ≠ 50% big) に分かれる。→ 本研究では P/E のどちらに載ったか自体が交絡になりうる、と書ける (**推測**: 本研究でそれがどの程度効くかは未測定)。

### 8.5 (論点4) 標準的な作法と、各選択の正当化

**確認できた事実**
1. 周波数・ターボ・C-state の**無効化**は、遅延 / ジッタ / オーバーヘッドを精密に測る系の論文で明示的に使われる (Caladan, Shenango, MeshInsight, PADS, DSB)。理由は「ジッタ低減」「測定分散の低減」「比較に影響」と**実務的**に書かれ、無効化自体の妥当性の検証はない。
2. **有効のまま報告**する論文もある (PARTIES: ターボ+HT 有効、performance ガバナ。Papadopoulos らの実験: DFS 既定のまま)。
3. 方法論の文献は「固定せよ」と一律には言わない。Hoefler & Belli は「固定、できなければ乱択、いずれも文書化 (Rule 9)」、Papadopoulos らは「非既定の設定を含め環境を記述せよ (P3)」と**記述**を要求する。
4. Taming Performance Variability は周波数設定を構成の 1 軸として両方測る。固定が分散を減らすか否かの一般結論は、grep した範囲では見つからなかった (周波数設定の優劣を述べた文が無い。全文精読はしていない)。
5. 資源管理 / オートスケール系 (Sinan, FIRM, Seer, Smart HPA, Autothrottle) は**書かない**。FIRM は Limitations で「省電力管理などハードウェア要因は範囲外」と書く。
6. 周波数が必要資源量を変えることは**示されている** (PEMA Fig.19、SLO-Power の課題記述、DSB Fig.12 の周波数感度)。ただし「利用率ベースの判定がそれで歪む」ことを定量的に扱った論文は見つかっていない。

**推測 (文献からの推論であり、原典に書かれているわけではない)**
- 本研究の (a) 固定 = DSB / Caladan / Shenango / MeshInsight / PADS と同じ作法。引用は「ジッタ・分散の低減」の理由づけで足りる。**ただし**、固定すると `intel_pstate` の `performance` では EPP=0 にしかならず周波数は固定されない (kernel doc)。`no_turbo=1` かつ `min_perf_pct = max_perf_pct` が要る。さらに本機の i7-1260P はノート PC なので固定周波数でも熱・電力制限で下がる可能性がある (**未検証**。Heracles が TDP 近傍で周波数が落ちると述べているのと同種)。
  固定の副作用は、**実運用の周波数変動 (現実の HPA が見る世界) を測らなくなる**こと。PARTIES は有効のまま測っているが、その理由づけの文は grep した範囲では見つからなかった (有効のまま測る動機は私の推測)。
- 本研究の (b) 固定せず記録 = Papadopoulos P3 / Hoefler Rule 9 の「記述」と整合し、PARTIES の作法にも近い。**周波数を共変量として記録し、周波数で割り戻した仕事量 (Zhang & Li 2012 の「平均周波数 × 利用率」と同じ発想) を併記**する形なら、文献的には一番守りやすい。
- 両方 (固定で本実験 + 非固定で現象の大きさを報告) は Taming Performance Variability の「両方測る」に倣える。

**本研究がどちらを選ぶべきかの文献的な結論**: 文献は**どちらも許容する**。決め手になるのは「何を主張するか」であって、文献が決めてはくれない。
- 「同居による softirq / CPU 時間の削減」という**機構の主張**なら (a) 固定が標準的 (遅延系の論文の作法)。
- 「HPA 下での損得」という**実運用の主張**なら、周波数変動そのものが交絡要因であり、(b) 記録 + 周波数補正の併記、または (a)+(b) 両方 (Taming 方式) が防御しやすい。
- どちらを選んでも、**kernel doc (cgroup-v2) の「CPU 配分は時間基準で周波数を考慮しない」** を根拠に「HPA の利用率は周波数不変ではない」と書いてよい (これは確認済みの事実)。
- 「P/E 混在 + ノート PC」は、引用できる先行測定が Saez / Schöne 程度しかない。査読で突かれやすいので、**P コアのみ (taskset / cpuset) に固定した追試を 1 点**入れると強い (**提案**)。

### 8.6 査読への備え (想定される指摘と答え)
1. 「ターボを切っていないのでは」→ 5 本 (DSB 他) が切る、PARTIES は有効のまま、と両論がある。どちらを選んだか + 理由 + 周波数の記録を方法節に書けば足りる (Papadopoulos P3)。
2. 「周波数が上がって CPU 時間が減って見えるのは当然では」→ その通りで、cgroup doc が「時間基準で周波数を考慮しない」と明記する。だから周波数で割り戻した仕事量を併記した、と書く。
3. 「E コアに載った分は?」→ Saez が CFS の実行間ばらつきを 2.3 倍と報告。対策 (P コア固定の追試 or ばらつきの報告) を書く。
4. 「他の K8s 論文は気にしていない」→ その通り (§8.2)。MeshInsight は K8s で明示的に無効化している数少ない例。

### 8.7 位置関係の判定
- **背景**: Caladan / Shenango / MeshInsight / PADS / DSB / PARTIES / Heracles / Taming / Papadopoulos / Hoefler / Gouicem / Schöne / Saez / Borg。
- **相補 (最も近い)**: SLO-Power (CCGrid '24) =「周波数変動でオートスケーラの必要コア数の見積もりが狂う」を課題として文章で指摘するが、利用率の歪みを測っていない。PEMA (HPDC '22) = クロック変更で必要割当が変わる実験。Zhang & Li (2012) = 「平均周波数 × 利用率」補正 (K8s ではない / abstract のみ)。
  いずれも**同居 (co-location) も HPA の台数への影響も扱わない**ので衝突しない。
- **衝突**: なし。

### 8.8 検索の記録 (2026-10-19、WebSearch + 原典 PDF 取得)
- 使った検索語 (すべて英語): "DeathStarBench open-source benchmark suite … pdf" / "Sinan ML-based QoS-aware … pdf" / "frequency-invariant utilization tracking Linux scheduler x86 APERF MPERF schedutil" /
  "CPU utilization misleading frequency scaling turbo boost autoscaler container CPU time inaccurate measurement paper" / "Kubernetes HPA evaluation experiment disable turbo boost performance governor fixed CPU frequency reproducibility microservices" /
  "Fewer cores, more hertz …" / "OS scheduling with Nest …" / "CPU utilization frequency-dependent utilization overestimates load DVFS cloud workload demand estimation normalized CPU time cycles" /
  "Intel hybrid P-core E-core Alder Lake performance measurement variability CPU time benchmark Thread Director evaluation" / "Kubernetes heterogeneous cores big.LITTLE CPU requests millicores …" /
  "cloud heterogeneous hardware same instance type performance variation …" / "interaction between DVFS and horizontal autoscaling Kubernetes CPU utilization threshold frequency governor microservices energy" /
  "\"CPU utilization\" \"frequency\" \"autoscaling\" microservices DVFS-aware scaling utilization metric changes with clock frequency" / "Brendan Gregg CPU utilization is wrong …" / "Linux scheduler asymmetric CPU capacity hybrid Intel Thread Director ITMT …" /
  "Papadopoulos Methodological Principles …" / "Hoefler Belli Scientific Benchmarking …" / "Google Compute Unit GCU normalize CPU across machine types Borg" / "CPU usage accounting hardware frequency scaling error container CPU time vs cycles …"。
- ヒット感触: 論点1 (方法節の設定) は原典 PDF を直接 grep できたので確実。論点2 (HPA 利用率 × 周波数) は **Kubernetes / HPA / DVFS の組合せで査読論文が出ず、ブログ・特許・公式 doc ばかり**。論点3 (K8s × P/E 混在) も同様。
- **出なかったもの (空白の根拠)**: ①「HPA (または利用率ベースのオートスケーラ) の利用率が CPU 周波数で歪む」の測定・補正論文 ②「Kubernetes × Intel 12 世代以降 P/E 混在ノード」の CPU 時間測定 ③マイクロサービスの同居 × 周波数。
  ※いずれも WebSearch の範囲。Google Scholar / IEEE Xplore / ACM DL の横断、および被引用側 (SLO-Power / PEMA の "Cited by") の追跡は**未実施**。「空白がある」と断定するには足りない。
- 取れなかった / 未確認: ACM DL・ScienceDirect・TechRxiv は 403 (WebFetch)。MeshInsight の正式掲載先、Dib & Metsch の本文、LWN 985293 の本文、Zhang & Li 2012 の本文、Gregg ブログ本文は未確認。
- 取得の実務: USENIX の `…/system/files/<会議><年>-<著者>.pdf`、Cornell 著者サイト `www.csl.cornell.edu/~delimitrou/papers/…`、Google 静的 `static.googleusercontent.com/media/research.google.com/en//pubs/archive/43792.pdf` (Heracles) が curl で直接取れた。
  Linux kernel の doc は `docs.kernel.org` の HTML を curl で取って grep すると、WebFetch の要約より安全 (cgroup-v2 の一文は curl で原文確認した)。

### 8.9 次に読むべきもの (周波数の観点)
1. SLO-Power (CCGrid '24) の §II-III と評価 — 「周波数変動でスケーラの見積もりが狂う」をどこまで定量化しているか (K8s 拡張を使うので最も近い)。
2. SLO-Power / PEMA の被引用側 (Google Scholar "Cited by") — 利用率ベースのスケーラ × 周波数を測った後続があるか。
3. Zhang & Li (2012) の本文 — 「平均周波数 × 利用率」補正の式と、周波数の測り方 (cpufreq_stats 改造) の詳細。本研究の補正の引用元候補。
4. Maricq et al. (OSDI '18) の結果節 — ターボ無効 + performance と標準設定とで分散がどう違うか (grep では結論文が見つからなかった。表の列 "frequency-scaling" 周辺)。固定の正当化に直結する。
5. Gouicem et al. (ATC '20) の schedutil 評価節 — powersave と schedutil で結果が変わる = ガバナ選択が結論を動かす例。

---

## 9. 論文執筆メモ: 書かなければいけないこと・引用するべきもの (2026-10-19 作成)

§7 (Sock Shop の負荷) と §8 (CPU 周波数) の調査、および 2026-10-19 のユーザ決定を、**本文のどこに何を書くか**の形でまとめたもの。
書くときはこの節を上から確認する。bib の key は `FOSE2026-TeX-UTF8/fose2026.bib` にある (2026-10-19 時点で全て**未引用**)。
「確認度」が ★ でないものは、引用する前に原典を読むこと。本研究の数値は**出所 (ファイルと計算方法) を provenance に書いてから**本文に出すこと。

### 9.1 CPU 周波数を固定しなかったこと (方法節 + 限界)

**決定 (ユーザ, 2026-10-19)**: 周波数は固定しない。理由 = 本研究は性能 (速さの絶対値) を知る研究ではなく、**相性の良い組み合わせの傾向**を知る研究であり、
HPA は実運用でも周波数で変わる CPU 時間を見て台数を決めるので、周波数の変動も HPA が置かれる条件の一部である。Online Boutique も固定せずに測っており、2 つのアプリで条件が揃う。

**方法節に必ず書くこと** (Papadopoulos ら P3 / Hoefler & Belli Rule 9 が「環境の記述」を要求する):
- [ ] CPU の型番と構成: Intel Core i7-1260P (P コア 4 [HT で 8 スレッド] + E コア 8、計 16 スレッド)、最大ターボ P 4.7 GHz / E 3.4 GHz、ベース P 2.1 GHz / E 1.5 GHz。
- [ ] 周波数の設定: ドライバ intel_pstate、ガバナ powersave、EPP balance_performance、ターボ有効 (= OS 既定のまま。**固定していない**と明記)。SMT (HT) 有効。
- [ ] 周波数と温度を各測定点で記録したこと (Prometheus の `node_cpu_scaling_frequency_hertz` のノード平均、`node_hwmon_temp_celsius` の最大)。HPA 実験でも記録すること (2026-10-19 時点で HPA ドライバは未作成)。
- [ ] 固定しなかった理由 (上の決定の文言)。文献上どちらも許容されることの引用:
  - 固定する側の例: `gan2019dsb` (DeathStarBench §4)、`fried2020caladan`、`ousterhout2019shenango`、`zhu2022meshinsight`、`savasci2024pads` — いずれも遅延・ジッタ・オーバーヘッドの精密測定が目的 (§8.1 ★)。
  - 有効のまま明記する例: `chen2019parties` (ターボ + HT 有効、performance ガバナ)、`papadopoulos2021principles` (DFS 既定のまま) (§8.1 ★)。
  - 両方測る例: `maricq2018taming` (★ grep ベース。結論文は未確認 — 引用前に結果節を読む)。
  - オートスケール系の多くは記述なし (Sinan, FIRM, Seer, Autothrottle, Smart HPA — §8.2)。これは「本研究だけが手を抜いた」わけではない根拠として使える (書き方は控えめに)。
  - 方法論: `hoefler2015benchmarking` (固定、できなければ乱択、いずれも文書化)、`papadopoulos2021principles` (P3 環境の記述)。

**限界節に必ず書くこと**:
- [ ] **HPA の入力 (CPU 時間) は周波数を考慮しない**。根拠 = Linux kernel 公式文書 cgroup-v2 (`linuxcgroupv2`, ★原文を 2026-10-19 に 2 回確認):
  > "In all the above models, cycles distribution is defined only on a temporal base and it does not account for the frequency at which tasks are executed."
  補足に schedutil doc の "consuming the CPU for 50% at 1GHz is not the same as consuming the CPU for 50% at 2GHz" (bib 未登録。必要なら追加)。
  **注意**: schedutil の周波数不変化はスケジューラ内部の util_avg の話で、cgroup の `usage_usec` / HPA には適用されない (§8.3 の推論)。混同して書かない。
- [ ] **本研究で観測した現象** (周りの負荷が増えて周波数が上がると、無関係なサービスの CPU 時間が小さく出る):
  - Sock Shop (`sockshop/experiments/results-mix-cpu.csv`、1 台・HPA なし、4 サイクル平均): 購入を固定して閲覧 0→120 周/s にすると、閲覧を処理しない購入側の CPU 時間が −12〜−34% (例: user 購入 16 で 98→67m)。ノード平均周波数は 1.9→2.5 GHz (測定全体で 1.44〜2.83 GHz)。同じ点のサイクル間ばらつきは carts/user で約 1.8% なので偶然ではない。
  - Online Boutique (`km2/experiments/rightsizing/results-mix-cpu2.csv`、1 台、6 サイクル平均): 購入 25 で閲覧 0→300 にすると checkout/payment/shipping/email が −26〜−32% (周波数 2.30→3.08 GHz)。購入 75/100 (閲覧 0→150) では周波数が約 3.1 GHz で頭打ちになり、ほぼ 0 か逆に増える: 1 台で −3〜+7% (payment b75 の −3% を除けば +2〜+7%)、2 台で +6〜+12%。
  - **TODO (provenance)**: 上の 2 組の数値は 2026-10-19 に会話中のアドホックな Python で出したもの。本文に出す前に再計算スクリプトを作り、`FOSE2026-TeX-UTF8/fose2026-data-provenance.md` (または修論用の provenance) に出所を書く。
- [ ] **影響の範囲**: Sock Shop では、この偏りが購入側サービスどうしの ρ の差より大きいので、購入側は「ρ ≈ 0 の塊」として扱い、細かい比較をしない。ρ の大きな区別 (購入側 ≈0 / front-end ≈0.26 / catalogue = 閲覧専用) は、CPU 時間でも周波数で割り戻した仕事量でも変わらない (`sockshop/experiments/analysis-rho.txt` §1 と §4)。
- [ ] **周波数で割り戻した仕事量 (CPU 時間 × 周波数) を感度として併記**した場合の引用: 同じ発想の先行例 `zhang2012dvfs` (「平均周波数 × CPU 利用率」で補正)。**abstract のみ確認 — 本文を読んでから引用**。
  ただし本研究の補正はノード全コアの平均周波数で近似しており、アヌビス点検 (2026-10-19) で「carts の CPU×周波数が 322→367 と揃わない = 代わりの指標として不十分」と指摘された。補正値は主結果にせず参考に留める。
- [ ] **P/E コア混在**: 同じ仕事でも P/E のどちらに載ったかで CPU 時間が変わりうる。根拠 = `saez2022thread` (Alder Lake で Linux CFS の完了時間が実行ごとに最大 2.3 倍ばらつく ★)、`schone2024alderlake` (P/E で周波数切替の挙動が違う ★)。本研究ではこの効果は**未測定**と書く。
- [ ] 周波数変動がオートスケールに効くことを指摘した近い研究 (Related Work か考察で触れる):
  - `savasci2024slopower` (SLO-Power, CCGrid '24): 周波数変動でスケーラの必要コア数の見積もりが狂う、と課題として文章で指摘 (★一部。§II–III と評価は未精読 — 引用前に読む)。
  - `hossen2022` (PEMA, HPDC '22, Sock Shop 使用): クロック 1.8→1.6/2.0 GHz で SLO を満たす最小 CPU 割当が変わる (Fig.19 ★)。
  - 「HPA の利用率が周波数で歪むことを測定・補正した査読論文」は WebSearch の範囲で見つからなかった。**「誰もやっていない」とは書かない** (Scholar / IEEE / ACM の横断と被引用追跡が未実施。§8.9)。

**想定問答** (§8.6 を参照): 「ターボを切っていないのでは」「周波数で CPU 時間が減るのは当然では」「E コアに載った分は?」「他の K8s 論文は気にしていない」。

### 9.2 2 つ目のアプリとして Sock Shop を使うこと (実験環境の節)

- [ ] 出典と版: microservices-demo (Weaveworks)、commit `9dff06f` (2023-12-05)、**DEPRECATED** (Weaveworks の事業終了後、更新なし)。Apache-2.0。**bib 未登録** — `onlineboutique` と同じ形で `@misc{sockshop, ...}` を追加すること。
- [ ] 上流から変えた点を全部書く (`sockshop/README.md`、`sockshop/normal/*.yaml` 先頭コメント): mongo を 3.4 に固定 (上流はタグ無し)、session-db に書き込める `/data` (emptyDir、上流のままだと RDB 保存失敗でログイン不能になった)、Istio 注入なし、CPU requests/limits を明示 (上流は limits 200〜500m / requests 約 100m、DB は未設定)。HPA 実験で使う枠と readiness probe はまだ決まっていない (2026-10-19)。
- [ ] Sock Shop が「代表的なベンチマーク」である根拠の引用: 候補 Aderaldo ら ECASE 2017 (**書誌は検索要約のみ、本文未読** — §7.7)。PEMA・COLA・Buzato など多数の論文が使っていること (§7.2) も根拠になる。
- [ ] DEPRECATED であることへの備え: 2025〜2026 年の論文でも使われ続けている (§7.2: Buzato 2025, Dashtbani 2025, ScalerEval 2025, ORACL 2026 など)。

### 9.3 負荷シナリオ (実験環境の節 + 付録)

- [ ] **「Sock Shop に論文が揃えている標準負荷は無い」**ことを書く。上流 locustfile は 1 種類の流れ (9 リクエスト、閉ループ、全員同じユーザ) で、閲覧/購入の配合の概念を持たない (§7.1 ★)。先行研究の多くは負荷の中身を書かない (§7.4)。
- [ ] 配合を明示した唯一の定番 = PPTAM 系の visitor 40 / buyer 30 / order visitor 30 (`avritzer2020` ★、`camilli2022` ★)。本研究の閲覧型 = visitor、購入型 = buyer の対応表を付録に置く。出典の WESSBAS (Vögele ら SoSyM 2018) は**本文未読** — 40/30/30 の由来を書くなら先に読む。
- [ ] 本研究の差を明記: ①開ループ (constant-arrival-rate) — Sock Shop 先行研究で明示的な開ループは 0 本 (§7.4c)、②購入型と閲覧型を独立の到着率で振る、③静的ページ (/, /category.html, /basket.html 等) とブラウザの JS が呼ぶ API (/cart, /customers, /tags) を叩かない (ユーザ判断 2026-10-19 で今のまま)、④利用者ごとにセッションを分ける、⑤注文履歴を見る型 (order visitor) を持たない。
- [ ] ③の影響を書く: 静的ページは front-end だけの CPU (express.static がセッション処理より前にあり、他サービスに届かない。`server.js` を Pod 内で確認 2026-10-19)。ブラウザの JS を実行すれば、ページごとにナビバーが `GET /cart` (carts) を、ログイン中はトップバーが `GET /customers/{id}` (user) を呼ぶので、閲覧が carts・user にも波及し ρ が変わりうる。本研究の ρ は「API だけの閲覧」での値と書く。
- [ ] 開ループの正当化は Sock Shop の先行研究からは得られない。Online Boutique で示した閉ループの双安定 (本研究の FOSE 論文・`openloop-k6-capacity` の記録) を再掲する。

### 9.4 Related Work に必須の差分: Buzato (2025)

- [ ] `buzato2025` (USP 修士論文、★全 120 頁中 第 4〜7 章を精読) は Sock Shop でサービスを束ねて HPA と組み合わせ、「束ねると通信が減りスループットが上がり、HPA と組むと効果が大きい、ただし独立スケールを失う」と結論。**定性的な主張は本研究と同方向なので、引用して差分を書かないと「既出」と言われる**。
- [ ] 差分 (本研究が埋めるもの): ①束ねる単位 — Buzato は 1 コンテナにプロセスを詰めて再コンパイル (Pod 内同居は対象外と本人が明記 §4.2.2, §7.4.1)、本研究は Pod 内の別コンテナ + localhost、②指標 — Buzato は絶対 CPU とスループット (softirq なし、リクエストあたりでない)、本研究は softirq/req と予約枠、③予約枠 (requests) の粒度損を HPA の台数で測る、④相手の選び方 — Buzato は依存関係・言語の定性的分類、本研究は ρ (需要の向き)、⑤負荷 — Buzato は Locust 閉ループ、本研究は開ループ。
- [ ] Buzato の HPA しきい値は requests 比 150% (通常の 50〜70% ではない)、各条件 6 サイクル・検定なし。比較するときに書き添える。
- [ ] 同著者の先行 2 本 (NCA 2018、SBAC-PADW 2023) は**本文未確認**。引用するなら先に読む (§7.3)。

### 9.5 ρ が Sock Shop ではほぼ 3 値になること (結果 + 考察)

- [ ] Sock Shop の ρ (`sockshop/experiments/analysis-rho.txt`、1 台・HPA なし・15 点 × 4 サイクル、2026-10-19): 購入側 6 サービス ≈ 0 (CPU 時間で −0.03〜−0.05)、front-end 0.262 [0.254, 0.267]、catalogue は購入 1 周の CPU がほぼ 0 で ρ が定まらない (閲覧専用)。
- [ ] Online Boutique では ρ が 0〜0.36 に連続的に並び、front と catalog が近かった (差 0.01)。Sock Shop では front-end と catalogue が遠い。**同じ「フロント + カタログ」でもアプリによって近い・遠いが入れ替わる**ことは、ρ が通信グラフの形ではなく需要の向きで決まることの材料になる。
- [ ] アヌビス点検 (2026-10-19) の指摘: catalogue は CPU 時間で ρ = −2.45、周波数で割り戻すと +1.44 と符号が逆になる。ν/β は β≈0 で発散するので、Sock Shop では発散しない指標 (例: 基準配合で CPU のうち閲覧が占める割合 ν·v/(β·b+ν·v)) を併記するか、「購入系と閲覧系がサービスごとにほぼ分かれている」こと自体をアプリの特徴として書く。**どちらにするかは未決**。

### 9.6 まだ決まっていない・確認が要るもの (書く前に片付ける)

- [ ] Sock Shop の HPA 実験の枠 (基準配合、極端に小さい枠になる payment / shipping / queue-master の扱い)、readiness probe の統一 (上流は catalogue/payment/user が 180 s、front-end 30 s、Java 4 つは無し)、Java の慣らし時間 — いずれもアヌビス点検 (2026-10-19) の必須項目。決めたら方法節に書く。
- [ ] 引用前に原典を読むもの: `zhang2012dvfs` 本文、`savasci2024slopower` の §II–III と評価、`maricq2018taming` の結果節、WESSBAS、Aderaldo ECASE 2017、Buzato の先行 2 本。
- [ ] 「空白」の主張 (HPA × 周波数、Sock Shop × 開ループ、Sock Shop × 配合を振る) は WebSearch の範囲のみ。書くなら「我々の調べた範囲では」と限定する。
- [ ] bib のコンパイル確認 (§8 で追加した key は bibtex を通していない。`\r{u}` 等の特殊文字、DeathStarBench の著者省略 "and others")。

### 9.7 Sock Shop の readiness probe と、台数を増やしたときの負荷の偏り (2026-10-19 追加)

- [ ] **方法節**: readinessProbe を 8 つのアプリで統一した (initialDelaySeconds 10、他は既定 = period 10 s / timeout 1 s / failure 3。OB の `km2/normal` と同じ)。上流は catalogue/payment/user 180 s、front-end 30 s (period 3 s)、Java 4 つ (carts/orders/shipping/queue-master) は無し。livenessProbe は上流のまま。
  理由 = HPA は Ready 前の Pod の CPU を数えないので、待ち時間の差がそのまま台数の差になり、同居 Pod の Ready は全コンテナの AND なので相手にも波及する (アヌビス点検 2026-10-19)。
  確認試験: `sockshop/experiments/probe10.log`, `probe10-ready.csv` (b24v120 を 20 分、12 分目に 2 台へ) で Ready 落ち 0・再起動 0・プローブ失敗イベント 0。起動→Ready は Go/Node 11〜13 s、Java 21〜42 s。
- [ ] **方法節 / 限界**: Java の慣らし。立て直し直後、負荷開始から 60 秒の CPU が定常の 2〜3 倍 (carts 389 vs 141m、orders 326 vs 119m)、約 2〜3 分で落ち着く。HPA が足した新しい Java Pod は起動直後の約 60 秒、上限 2000m 近くまで使う (carts 10 秒最大 1998m、shipping 1997m)。数値の出所 = `sockshop/experiments/analysis-probe10.txt` (`analyze_probe10.py`)。
  OB で起きた「起動直後の跳ね上がりで余分に台数が増える」(km2/approach/rightsizing-procedure.md) が Sock Shop では Java 4 サービスで起こりうる。HPA の cpu-initialization-period (既定 5 分) との関係を書く (K8s 公式 doc を引用。bib 未登録)。
- [ ] **要対処 (未解決 2026-10-19)**: 2 台にしても **front-end と payment の新しい Pod にほぼ負荷が来ない** (t 900〜1200 s で front-end 旧 647m / 新 1m、payment 旧 7m / 新 0m)。HTTP keep-alive で接続が古い Pod に張り付いたまま (k6 → front-end、orders → payment と推測)。catalogue・carts・orders・user などは分かれた。
  OB の gRPC 接続の固定 ([[grpc-pinning-imbalance]]、GRPC_LB=1 で対処) と同じ形の問題。HPA 実験の前に直すこと (k6 側は接続の再利用を止める設定で直せる見込み、orders → payment は未定)。直した方法は方法節に書く。
  **→ 2026-10-19 に対処 (ユーザ決定 B′)**: k6 に `noVUConnectionReuse: true` (1 周ごとに接続を張り直す)、orders の JAVA_OPTS に `-Dhttp.keepAlive=false` (Java 標準 HttpURLConnection の接続の使い回しを止める)。
  再試験 `probe10b.log` / `analysis-probe10b.txt`: 2 台目の分担 front-end 旧 406 / 新 394m、payment 5 / 5m、user 52 / 50m で均等に。Ready 落ち 0・再起動 0。
  **方法節に書くこと**: OB は gRPC のクライアント側 round_robin (接続は張りっぱなし、リクエストごとに振り分け) で、Sock Shop は「接続を毎回作り直して kube-proxy に振り分けさせる」方式。仕組みが違う。
  **限界に書くこと**: 接続を作り直す分 CPU が増える。1 台・b24v120 の定常 (t 400〜700 s) で front-end 659→719m (+9%)、orders 119→132m (+11%)、user 87→100m (+15%)、payment 7→9m。carts・catalogue は不変。1 回ずつの比較なので回ごとのばらつきは未評価。softirq (通信 CPU) も増えるはずで、分離と同居の両方に乗る。
  ρ (`analysis-rho.txt`) は対処前の設定で測ったもの。対処後に測り直すかは未決 (2026-10-19)。
- [ ] **限界**: 新しく足した Java の Pod は、起動から 3〜8 分たっても古い Pod より CPU が多い (t 900〜1200 s で carts 新/旧 1.3〜1.4、shipping・queue-master 2.2 倍。両試験で同じ傾向)。慣らし (JIT) が長引くと推測。HPA で増えた Java Pod は数分間 1 リクエストあたりのコストが高い。
