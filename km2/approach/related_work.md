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
- **merging の前提条件 (原典 §III-B、2026-11-09 確認)**: ①別々の名前空間で動かす必要がないこと ("containers are merged only if there is no requirement to execute the services in separate namespaces") ②依存関係の衝突がないこと (同じ依存の別バージョン=衝突。XML の依存ファイルをチェッカーで検査) ③同じベースイメージであること (Dockerfile を結合するため)。言語も依存ファイルの形式もばらばらな Sock-Shop は merging の評価から外し、全サービス Java の Page-Rank だけで評価 (§IV-A)。著者は merging 後も "service granularity remains unchanged" (サービスの分割は保たれ、2 プロセスとして動く) と書いている。→ 本研究の Pod 内同居はコンテナを分けたままなので ①〜③ の制約がない = 差分として書ける。
- **【2026-11-09 原典 §IV を通読して訂正】** 52% と 57% は**別のアプリ** (colocation で Sock-Shop 57%・Page-Rank 52%)。merging は **Page-Rank のみ・2 組だけ** (discovery+config、twitter-rank-web+crawler。前提条件=同じベースイメージを満たしたのがこの 2 組) で、**colocated 比でさらに約 13% 減** (「+13 ポイント」ではない。0.48×0.87≈0.42 → 合計 58.5% 減と整合)。58.5% と実行時間 13.4% (1 操作=ランク更新 1490→1291 秒) は **Page-Rank のみ**。affinity は「ある期間の合計バイト量」で、観測期間の長さ・負荷の条件は本文に記載なし (§III・§IV を確認)。
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
- **金額 (月額コスト) の結果 — 【引用禁止・ユーザ決定 2026-11-05】記録として残すだけで、論文・発表には使わない (§9.4)** (2026-11-05 に原典 PDF の §5.2 Table 5.8・§5.4.3 Table 5.15・付録 C.5/C.10 を精読。PDF はユーザの `~/Downloads/Dissertacao_FernandoHenriqueLaureanoBuzato_corrigida.pdf`):
  - 算出法: "calculated based on the hourly costs of CPU, memory, and persistent volume allocation, with an estimate of monthly expenses provided in dollars" (§5.2)。専用ノードに「financial resource consumption monitoring tool」を置いた (§4.2.2) が、**ツール名は本文に無い** (grep で Kubecost/OpenCost 0 件)。"allocation" が requests か実使用かも**明記なし**。10 分の実験からの月額外挿。6 サイクルの中央値、検定なし。
  - Table 5.8 (中央値、US$/月、HPA 有り): 低負荷 (300 ユーザ) benchmark 171.01 / by-dep 186.95 / by-stack 190.54 / all-in-one 201.37、中 (2400) 216.46 / 223.45 / 200.68 / 201.46、高 (4500) 208.41 / 239.22 / 223.12 / 191.94。HPA 無しは 70.79〜129.02 で、高負荷以外は差が小さい (高負荷の差は可用性=落ちずに動いた時間の差による、と著者)。
  - 著者の解釈: HPA 有りでは低負荷で benchmark が最安 (all-in-one より約 15% 安い)、中負荷で all-in-one が benchmark より約 7% 安い。「束ねると増やす Pod 数が減るので安くなる」(§5.4.3)。CPU・メモリ使用量とコストに明確な関係は無かった (§5.2)。
  - **私の検算 (表から再計算)**: 低 15.1% ✓、中 −6.9% ✓・by-dep 比 −9.8% ✓。**食い違い 2 件**: ①§5.4.3 高負荷「by-dependencies より約 8% 安く by-stack より 15% 安い」→ 表では by-dep 比 −19.8%、by-stack 比 −14.0%、benchmark 比 −7.9% (8% は benchmark 比の値と思われる)。②§5.4.3「低負荷・HPA 無しで all-in-one は benchmark より 10% 高い」→ 表では +2.3%。スケール率の表 (Table 5.15) も本文 (by-stack 116%) と表 (133.33) が合わず、欄が欠けている。**引用するときは表の値を使い、割合は自分で計算し直す**。
  - **金額が下がる仕組みは書かれていない** (2026-11-05 確認): ノードは EC2 t3.xlarge を**シナリオごとに固定** (HPA 無し 1 台、HPA 有り 2 台。2 台目は Pod 上限 58 個/台のために追加、§4.2.2・§4.2.4)。Cluster Autoscaler / Karpenter / ノードの自動追加の記述は無い (grep 0 件)。HPA は 1〜4 Pod。よって**AWS の実請求はシナリオ間で同じはず**で、表の「月額」は Pod の割り当てにノードの時間単価を按分した**推定値**と読むのが自然 (ツール名・按分の定義は本文に無い=私の推論)。引用するときは「割り当てベースの推定コスト」と書き、実請求の削減とは書かない。
  - 本研究との関係 (私の解釈): 低負荷で all-in-one が HPA 有りだと benchmark より +17.8% 高いのは、本研究の粒度損 (束ねると冷たい側も一緒に増える) と同じ向きの現象に見えるが、Buzato は機構を説明していない。本研究は機構 (必要台数の大小の入れ替わり) と予約枠での測定を与える、と差分に書ける。
- 同著者の先行 2 本 (thesis 参考文献から。**本文未確認**、書誌は thesis の記載のみ): Buzato, Goldman, Batista, "Efficient resources utilization by different microservices deployment models," IEEE NCA 2018, pp.1–4 (マイクロサービスの「層」を 1 コンテナに束ねるとネットワーク消費 99% 減);
  Buzato & Goldman, "Optimizing microservices performance and resource utilization through containerized grouping: an experimental study," SBAC-PADW 2023 (IEEE), pp.115–122 (上記 §4.2.3 の HPA 無し実験の論文版)。

- **追記 (2026-11-10)**: 上記 thesis の HPA 実験は**査読付きジャーナル版** Buzato & Goldman, IJNC 16(1):52–75 (2026, DOI 10.15803/ijnc.16.1_52) として公刊されている (★PDF 確認、詳細と差分は §13.4。bib `buzato2026ijnc`)。**同論文は Pod 内での束ねを今後の課題に挙げている**。

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

> **2026-11-17 訂正: ユーザ決定で周波数を固定した** (ターボ無し、基本周波数 P 2.1 / E 1.5 GHz、16:56 から)。以下の「固定しない」は 2026-11-17 より前の測定 (FOSE2026 を含む) に当てはまる記述として残す。固定後の書き方は §9.30。

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
- [ ] (**2026-10-19 訂正**: 下の「唯一」は誤り。ATOM (`gias2019atom` ★) も Sock Shop で TPC-W 風の 3 配合 Home/Catalog/Carts = 63/32/5, 54/26/20, 33/17/50 を明示している。§10.2 参照。「閲覧/購入の比を連続的に振る」先行は見つからなかった、は変わらない)
- [ ] 配合を明示した唯一の定番 = PPTAM 系の visitor 40 / buyer 30 / order visitor 30 (`avritzer2020` ★、`camilli2022` ★)。本研究の閲覧型 = visitor、購入型 = buyer の対応表を付録に置く。出典の WESSBAS (Vögele ら SoSyM 2018) は**本文未読** — 40/30/30 の由来を書くなら先に読む。
- [ ] 本研究の差を明記: ①開ループ (constant-arrival-rate) — Sock Shop 先行研究で明示的な開ループは 0 本 (§7.4c)、②購入型と閲覧型を独立の到着率で振る、③静的ページ (/, /category.html, /basket.html 等) とブラウザの JS が呼ぶ API (/cart, /customers, /tags) を叩かない (ユーザ判断 2026-10-19 で今のまま)、④利用者ごとにセッションを分ける、⑤注文履歴を見る型 (order visitor) を持たない。
- [ ] ③の影響を書く: 静的ページは front-end だけの CPU (express.static がセッション処理より前にあり、他サービスに届かない。`server.js` を Pod 内で確認 2026-10-19)。ブラウザの JS を実行すれば、ページごとにナビバーが `GET /cart` (carts) を、ログイン中はトップバーが `GET /customers/{id}` (user) を呼ぶので、閲覧が carts・user にも波及し ρ が変わりうる。本研究の ρ は「API だけの閲覧」での値と書く。
- [ ] 開ループの正当化は Sock Shop の先行研究からは得られない。Online Boutique で示した閉ループの双安定 (本研究の FOSE 論文・`openloop-k6-capacity` の記録) を再掲する。

### 9.4 Related Work に必須の差分: Buzato (2025)

- [ ] `buzato2025` (USP 修士論文、★全 120 頁中 第 4〜7 章を精読) は Sock Shop でサービスを束ねて HPA と組み合わせ、「束ねると通信が減りスループットが上がり、HPA と組むと効果が大きい、ただし独立スケールを失う」と結論。**定性的な主張は本研究と同方向なので、引用して差分を書かないと「既出」と言われる**。
- [ ] 差分 (本研究が埋めるもの): ①束ねる単位 — Buzato は 1 コンテナにプロセスを詰めて再コンパイル (Pod 内同居は対象外と本人が明記 §4.2.2, §7.4.1)、本研究は Pod 内の別コンテナ + localhost、②指標 — Buzato は絶対 CPU とスループット (softirq なし、リクエストあたりでない)、本研究は softirq/req と予約枠、③予約枠 (requests) の粒度損を HPA の台数で測る、④相手の選び方 — Buzato は依存関係・言語の定性的分類、本研究は ρ (需要の向き)、⑤負荷 — Buzato は Locust 閉ループ、本研究は開ループ。
- [ ] Buzato の HPA しきい値は requests 比 150% (通常の 50〜70% ではない)、各条件 6 サイクル・検定なし。比較するときに書き添える。
- **【引用禁止・ユーザ決定 2026-11-05】Buzato の金額 (月額コスト、Table 5.8 / 5.15) は論文・発表で引用しない。** 理由: ノード (EC2) 台数が固定で実請求は変わらないはずなのに、Pod 数で月額が変わる推定値になっており、算出ツールと按分の定義が本文に無い。さらに本文の割合が表と 2 か所合わない (詳細 §7.3)。Buzato を引くのは、束ね方・HPA との組み合わせ・スループットの差分 (上の項目) に限る。
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
- [ ] **方法節 (ρ の測り直し mix-cpu2b、2026-10-19 決定)**: 1 台固定・6 サイクル・慣らし 5 分 (b20v100)・冷却待ちと休憩は OB mix-cpu2 と同じ (各点の前に CPU 温度 70℃ 以下まで待つ・最長 600 s、各点の後に 60 s 休む)。
  購入型の利用者 (200 人、住所・カード付き) は**サイクルの慣らしで 1 回だけ登録**し、各点は使い回す (ユーザ決定)。OB は購入に利用者登録が要らないので、この手順は Sock Shop だけ。
  初回の ρ (`results-mix-cpu.csv`) は点ごとに登録していた (計測窓には入らないが、ウォームアップ直前に user・user-db が登録処理をし、user-db が点ごとに大きくなる)。測り直しと初回の差には、接続設定 (B′) とこの変更の両方が乗るので、本文ではまとめて「設定を整えて測り直した」と書くか、分けて書くなら注記する。スクリプト = `sockshop/experiments/measure-mix-cpu.sh`。
- [ ] **限界**: 新しく足した Java の Pod は、起動から 3〜8 分たっても古い Pod より CPU が多い (t 900〜1200 s で carts 新/旧 1.3〜1.4、shipping・queue-master 2.2 倍。両試験で同じ傾向)。慣らし (JIT) が長引くと推測。HPA で増えた Java Pod は数分間 1 リクエストあたりのコストが高い。

### 9.8 測定点の配合 (buy × view の格子) と負荷強度の決め方 (2026-10-19 追加。詳細・根拠は §10)

- [ ] **方法節 (ρ の測定設計)**: 配合の決め方は「**規則**を両アプリで揃え、**数値**はアプリごとに決める」と書く。規則の案 (推奨 1) = 各因子の最大値を『そのアプリの単独飽和点の X%』、かつ『ボトルネック (Sock Shop は front-end) の予測 CPU が上限 u_max 以下』を満たす格子点だけを測る。
  この規則は Online Boutique の『重すぎる 2 点 (75,300)(100,300) を除いた』という判断の一般化として書ける (**OB の 20 点すべてで予測 front-end 使用率を計算し、除いた 2 点だけが上限を超えると確認してから**書くこと。私は OB の数値を見ていないので未確認)。
  X と u_max の値は文献から一意には決まらない (50–90% = Stewart & Shen、60–80% = PARTIES の knee、20/50/80% = Spinner らの試験水準)。**値は本研究で決めて理由を書く**。
- [ ] **方法節**: ρ = ν/β は『1 周あたりの CPU の比』なので、D の線形モデルが成り立つ範囲では測定点の取り方に依らない。配合はモデルの**識別 (係数を精度よく出す)** と**検証 (線形が成り立つ範囲の確認)** のために選ぶ、と位置づける。これが「OB と同じ比で縮める」より説得力のある理由。
- [ ] **方法節 / 付録**: 計画行列の診断を載せる = 購入と閲覧の相関 r(buy, view)、分散拡大係数 VIF、ρ の区間幅、点を 1 つずつ外したときの ρ の変動 (leave-one-point-out)、中間点での残差 (線形性)。共線性は『設計で避ける』のが標準 (`spinner2015demand` abstract、`kalbasi2010thesis` ★ 2.1 節)。
- [ ] **付録 (検証点)**: 格子とは別に、標準ミックス風の点 (TPC-W の browsing 95:5 / shopping 80:20 / ordering 50:50 を周の比に読み替えたもの。ATOM が Sock Shop で同じ流儀 `gias2019atom` ★) で、回帰から予測した CPU と実測の誤差を報告する。**TPC-W の比は『ウェブ操作 (interaction) の比』で、本研究の『周の比』とは単位が違う**ので、そのまま流用せず読み替えを明記する。
- [ ] **Related Work / 限界**: 『別アプリ間で配合を揃える慣行』は、読めた範囲 (§10 の約 20 本) で見つからなかった。PARTIES は**アプリごとの max load に対する割合**で揃える。『WebSearch と一部 PDF のみ、Google Scholar / IEEE / ACM 横断は未実施』と限定を付ける。
- [ ] **査読で突かれうる点と答え**:
  - 『OB と SS で格子が違う。比較は公平か』→ 比べているのは ρ (1 周あたりの比) であり、格子の数値ではない。揃えたのは規則 (容量に対する割合と利用率の上限)。PARTIES (`chen2019parties` ★) も別アプリの負荷を各自の max load の割合で揃えている。
  - 『なぜその X, u_max か』→ 感度を示す (X や u_max を変えても ρ が区間内に収まる)。示せていなければ限界に書く。
  - 『閲覧と購入の比が現実的でない』→ 現実の比を再現する目的ではなく係数を識別する目的。現実的な比は検証点 (標準ミックス風) で確認する。
  - 『Sock Shop の front-end が 1 コアで飽和するのは測定の欠陥では』→ アプリの特性 (Node.js 単一スレッド) として報告し、飽和の手前で測る理由にする (Stewart & Shen: 飽和スループットの 50–90% で測る)。
- [ ] **引用前に読むもの**: `spinner2015demand` (abstract のみ。共線性・負荷水準の試験結果を書くなら本文必須)、`pacifici2008cpu` / `zhang2008regression` / `kraft2009valuetools` / `stewart2007nonstat` (本文未読)、`kistowski2018teastore` (有料で未読)、`jain1991art` (実書籍の第 5・16–17 章で頁を確認)。`kalbasi2012dec` は論文本体が未読 (修士論文版は ★)。
- [ ] **(2026-10-20 追記) SS の耐久試験の結果で上の項目を直す**: 1 台固定・HPA 無し・3 サイクルの段階的負荷 (`sockshop/experiments/results-stress.csv`、ドライバ `measure-stress.sh`、集計 `km2/experiments/rightsizing/analyze_limit.py` + 混合は CSV の point 列から手計算 = **混合の集計スクリプトは TODO**) で、購入 100・閲覧 400・混合 b40v200 周/s まで**全 57 点で取りこぼし 1% 以下** (超えたのは 0 点、最大 0.05%)、失敗 0、絞り最大 0.1%。front-end は b100 で約 1.02 コア・v400 で約 0.9〜0.98 コアに達したが p99 は 82 ms 以下。**『front-end が 1 コアで飽和する』という上の想定問答は、この範囲では観測されていない**ので、書くなら『1 コア付近まで取りこぼし無し、それより上は未測定』とする。格子の上限を決める根拠 (方法節) として、この試験を「格子の最大点は耐えられる負荷の内側」の裏付けに使える。温度は最大 100 ℃ (cyc3 b90) に達した点があり、周波数の記録 (§9.1) とあわせて書く。
- [ ] **(2026-10-20 ユーザ指示: 必ず書く) 方法節 — 測定点 (格子) を選んだ理由**: 次の 3 点で書く。
  1. 形: 購入と閲覧の効果を分けるため、両者を独立に変えた格子 (購入だけ・閲覧だけ・混合) で測った。
  2. 上限: 1 台で取りこぼし 1% 超・CPU の絞りが出ない範囲 (OB は b75v300・b100v300 を最初から除外)。
  3. 細かい数値: 購入 25 刻み・閲覧 75 刻みに強い理論的理由はなく、実験時間と範囲の兼ね合いで決めたと正直に書く。その代わり、点の選び方を変えても結論が変わらないことを示す = 重い側・軽い側の削り、間引き、1 点除外、無作為 9 点 (300 通り)、サイクルのブートストラップ (400 回) のいずれでも、Δρ の順序で近い 4 組と遠い 6 組が重ならずに分かれた (固定の境目 0.05 では半分範囲で 2 組が越えるので、境目ではなく順序で述べる)。出所 = アヌビスの一時検算 (scratchpad chk.py / bs.py) のみ → **正式な出所スクリプトは TODO** (analyze_rho_scale.py に組み込む)。
  - **今後の課題 (§5) に書く**: 格子の刻みを細かくした測定、刻みそのものの最適化 (実験計画法による点の選び方) は今後の課題とする。
- [ ] **(2026-10-20) SS の front-end は 1 台あたり約 1 コアで頭打ちする — 方法節 (SS の格子) + 結果 (ρ の感度)**:
  観察 (`sockshop/experiments/smoke-mix2b.csv`・`smoke-mix2b-series.csv`、1 サイクル): 1 台の b48v240 で front-end の CPU が計測窓の 10 秒値で 1027〜1055m に張り付いた (他の点は揺れる)。絞り 0% (limits 2000m に未達)、Pod の中は `node server.js` 1 プロセスだけ。取りこぼしは購入 0.12%・閲覧 0.04% (除外基準 1% 未満)。同じ点の 2 台では合計 1.2〜1.5 コア使えて取りこぼし 0。耐久試験の b100 (1 台) も約 1022m で止まっていた。
  → **1 台のこの点では、front-end の CPU が必要量より少なく記録されている (頭打ち)**。取りこぼし・絞りの除外基準では検出されない。原因は Node.js が 1 プロセス 1 スレッドで処理するためと考えられる (limits を上げる試験はしていない = 推測と書く)。
  隣の b48v160・b32v240 (1 台) は平均 957・968m、揺れあり、取りこぼし 0 (`smoke-mix2b-corner*.csv`)。
  **ユーザ決定 (2026-10-20)**: b48v240 は格子に残して測り、**この点を含めた場合と除いた場合で ρ (と近い・遠いの並び) がどれだけ変わるか**を解析で示す。OB は重い 2 点 (b75v300・b100v300) を最初から外したので扱いが違う → 書くときに明記する。解析スクリプト = `sockshop/experiments/analyze_rho_ss.py` (2026-10-21 作成、結果は §9.10)。
  HPA 実験への含意: front-end の 1 台の処理能力は limits ではなく約 1 コアで決まる。枠は 1 台の利用率が 1 コアに届く前に台数が増えるように決める。
- [ ] **§8.1 の表に追記すべき 1 行**: ATOM (`gias2019atom` ★) は『高い資源競合を作るために CPU 周波数を下げた (1.2 GHz / 0.8 GHz)』と Table V に書く。周波数を**操作して**報告する例。§9.1 の『書く論文が少ない』の補強にならず、むしろ『資源管理系でも書く例がある』側。

### 9.10 SS の ρ 本測定 (1 台・2 台) と、測定中のクラスタ再起動 (2026-10-21 追加)

出所: `sockshop/experiments/results-mix-cpu2b.csv` (15 点 × 1 台/2 台 × 6 サイクル、2026-10-20 17:38〜10-21 10:42)、解析 `sockshop/experiments/analyze_rho_ss.py` → `analysis-rho-ss.txt`。

- [ ] **方法節 (除外したデータ) + 限界**: 2 サイクル目の 2 台ブロックの途中 (10-20 21:08:04 と 21:27:59) に MicroK8s が自分でクラスタを再起動した (journalctl: `apiserver-kicker` が "cert change detected" → kubelite・containerd 停止 → 全 Pod 再起動)。直前に Wi-Fi (wlo1) の IPv6 一時アドレスが入れ替わっている。再起動後は登録した利用者が消え、購入 1 周 4 リクエストのうち 2 つが失敗 (失敗率 0.5、注文は全滅)。購入を含む 7 点で CPU 合計が他サイクル比 −13〜−43%。なお再起動前の b48 (20:40) も CPU 合計 +12.9% で外れており原因不明 (アヌビス指摘) → 『再起動前 6 点残す』感度分析は前提が弱い。→ **主推定ではこの 2 台ブロック (15 点) を丸ごと除いた** (2 台は 5 サイクル)。感度として再起動前に終わった 6 点を残した版も出し、ρ はほぼ同じ (front-end 0.287 ↔ 0.286)。1 台ブロックは別に立て直し・登録し直しているので影響なし。
  **2026-10-26 ユーザ決定**: 元の cyc2 × 2 台の 15 点は使わない。2 台 × 1 サイクルを取り直して差し替える (出力 `results-mix-cpu2b-redo2.csv`、cycle=2 として記録)。`analyze_rho_ss.py` は取り直しがあれば差し替え、無ければ除外で出す。感度として「cyc2 × 2 台を除いた 5 サイクル」も残す (『再起動前 6 点残す』版は廃止)。方法節には「取り直しは 6 日後 (別の日) で、そのサイクルだけ 1 台と同じ日に測っていない」と書く。**取り直し済み (2026-10-26 15:22〜16:47)**: 15 点とも取りこぼし 0・購入失敗 0・絞り 0・再起動 0 (journal の "cert change detected" 0 件)。差し替え後の front-end ρ は 2 台 0.288 [0.283, 0.292] (5 サイクル版 0.287 [0.282, 0.291] とほぼ同じ)。`analysis-rho-ss.txt` を更新。
  - [ ] **要確認 (b48 の外れ)**: 取り直しの最初の点 b48 で、orders 388 m (他 5 サイクル 274〜281)、shipping 130 m (42〜47)、queue-master 88 m (40〜47) と購入側が高い。front-end は範囲内。元の cyc2 でも b48 (2 点目) が CPU 合計 +12.9% で外れていた (アヌビス指摘)。登録直後・慣らし直後の購入側 (Java) の立ち上がりか。これで購入側の ρ が少し動く (orders −0.015→−0.018、shipping −0.005→−0.020、queue-master −0.011→−0.020。いずれも ≈0 のまま) が、front-end の ρ には効かない。
- [ ] **(要確認・重大) OB の実験にも同じ再起動が入っている可能性**: この再起動は 10/05 以降**毎晩 2 回** (10/05 23:37 から毎日約 10 分ずつ早まり、10/20 は 21:08 と 21:28) 起きている。OB の pdist-k3 分離 (`stdout-pdistk3sep.txt`) では 10/15 21:57 の再起動が cyc12 b50v300 に当たり「summary回収失敗」で点が欠けている。**洗い出し済み (2026-10-22、`km2/experiments/restart-audit.py` → `restart-audit.md`、9/16 以降の 61 回)**: 実験に当たったのは 7 回。**アヌビス点検 (2026-10-22) で訂正**: 再起動は 8/18 から毎日起きており (9/15 以前に 28 回)、FOSE の出所 `summer2026/mix.log` の 2 点 (9/2 17:35:44 frontcart cyc1 b100v300、17:53:58 frontrecocatalog cyc1 b100v200) が回収失敗で欠けた。前者が表 1 frontend+cart の分母 19 (provenance §3.5 の欠測) の原因。値の計算に使った点と重なるものは無い → 修論では表 1 の欠測理由として書く。修論側: OB mix-cpu2 (10-09 23:17、1 点欠け。当たったブロックを除いても front/catalog/reco の ρ は不変、動くのは ad 1 台 1.19→1.17 と currency 2 台 0.26→0.25)、OB pdist-k3 分離 (10-15 21:57、1 点欠け + 同サイクル後続 2 点の一部指標が外れ。後遺症か偶然か未確認)、OB fixed4b-lb (10-07、2 点欠け + 同サイクル後続 3 点 front3@400/450・mega@450 が他サイクルの範囲外。FOSE 未使用だが memory の知見『崖位置不変・到達上限 354→295』の出所なので、使うなら除外した場合と含めた場合を示す)、SS mix-cpu2b (上記)。方法節に「クラスタの自動再起動で欠けた点・除いた区間」として書く。8/18〜9/15 は未調査 (ユーザ判断で範囲外)。
- [ ] **結果 (ρ)**: front-end 0.287 [0.280, 0.292] (1 台) / 0.287 [0.282, 0.291] (2 台)。台数で ρ は変わらない (OB の主張と同じ形)。購入側 (carts, orders, payment, shipping, user, queue-master と各 DB) は −0.03〜−0.005 でほぼ 0。catalogue は購入 1 周の CPU β ≈ 0 で ρ が定まらない (1 台 5.1、b48v240 を除くと 28.9、2 台で 9.9 や −25.7)。§9.5 の 4 サイクル版 (front-end 0.262) より少し高い (接続設定 B′ と慣らし 300 s の違いか。未検証)。
- [ ] **結果 (b48v240 を含めるか)**: front-end の ρ の差は 1 台 +1.5%、2 台 −1.3% で小さい。1 台では b48v240 の実測が、この点を除いた式の予測より 57 m 低い (頭打ち、約 5%)。2 台では逆に 69 m 高い。β ≈ 0 のサービス (catalogue, rabbitmq) と購入側の小さい ρ は、この 1 点で大きく動く (割合では数十 %、値の差は 0.01 未満)。→ 「頭打ちの点は front-end の ρ にほとんど効かない。効くのは ρ が定まらないサービスだけ」と書ける。
- [ ] **結果 / 限界 (負の ν と周波数)**: 購入側の ν (閲覧 1 周あたりの CPU) が小さな負になる (user −0.10 m)。閲覧を足すとノードの周波数が上がる (b48: 2.72 GHz → b48v240: 3.04 GHz) ので、同じ仕事の CPU 時間が減るためと考えられる。CPU 時間 × 周波数で割り戻すと負の ν はほぼ 0 になる (user −0.103 → −0.001)。ただしこの割り戻しは近似で、front-end の ρ も 0.287 → 0.224 と動く。§9.1 (周波数を固定しない) の具体例として書く。出所: その場の検算のみ → **スクリプト化は TODO**。
- [ ] **今後の実験の前に (方法の改善)**: 再起動の仕組みは確認済み (`/snap/microk8s/current/apiservice-kicker` が 5 秒ごとに IP を見て、変われば証明書を作り直し kubelite 停止・全コンテナ削除・containerd 再起動。IP が変わるのは wlo1 の IPv6 一時アドレス、`temp_prefered_lft = 86400`)。止める手段 = `sudo touch /var/snap/microk8s/current/var/lock/no-cert-reissue` (スクリプトに分岐あり、推奨)。**2026-10-27 13:07 にユーザが設置済み。効果を確認** (10/27 19:58:19 に wlo1 の IPv6 一時アドレスは入れ替わったが、apiserver-kicker の反応・kubelite 停止は 0 件。最後の再起動は 10/26 20:28:16)。方法節: 「10/27 以降の実験はこの再起動の影響を受けない」と書ける。置いたら、その晩の journal に "cert change detected" が出ないことを確かめる。
- [ ] **今後の OB の実験 (アヌビス提案 2026-10-22)**: OB のドライバ (`measure-mix-cpu.sh`、`bundle-vs-loss2.sh`) にも SS と同じく点ごとの Pod の RESTARTS を記録させる。今は OB で「Pod が実際に再起動したか」を記録から言えない。次に OB を回すときに入れる。
- [ ] **査読への備え (アヌビス 2026-10-22)**: (1)『測定中にクラスタが毎日再起動していた。汚染の範囲を全期間で示せ』→ 9/16 以降は `restart-audit.md` で全照合済み。8/18〜9/15 は FOSE の出所ログだけ照合 (アヌビス)。国際会議に出すなら 8/18 以降の全期間の一覧が要る。(2)『再起動直後は冷えた状態で測っていないか』→ SS は RESTARTS と失敗率で反論可、OB は CPU が他サイクルの範囲内という間接証拠のみ。pdistk3sep cyc12 の reco 4 台は説明できない。(3)『除外を結果を見て決めていないか』→ 除外の基準は journal の時刻 (外部基準)。ただし SS (ブロック全体) と OB (1 点 + 後続) で除外範囲が違うので、両方とも除外した場合と含めた場合を並べて示す。
  到達水準 (アヌビス): 修論・国内査読・研究会は上の修正で十分。国際会議は全期間の一覧と OB の再起動の直接記録が要る。
- [ ] **修論の方法節**: 「夜間のクラスタ自動再起動と除外の手順」の節を立てる。表 1 の欠測理由 (9/2)、OB mix-cpu2・pdistk3sep・fixed4b-lb の欠け、SS の 1 区間の除外を書く。

### 9.9 負荷の物差し (buy と view を 1 つにまとめる・2 アプリで揃える) の書き方 (2026-10-20 追加。詳細・根拠は §11)

- [ ] **方法節 (負荷の定義)**: 負荷は『強度 + 配合』の 2 成分で表す、と書く。強度 = 総提供負荷 Σ_c λ_c·D_c (コア。D_c = 型 c の 1 周がアプリ全体で使う cgroup CPU、**分離構成の基準点で測って固定した重み**)、配合 = 閲覧が総提供負荷に占める割合。
  根拠 = 利用率の法則を型ごとに足す標準手法 (`lazowska1984qsp` ★ 第 3 章、`denning1978operational` 書誌のみ=引用前に読むこと)。先行のマイクロサービス研究も強度と配合を別成分に持つ (`sachidananda2024erlang` ★・`sachidananda2022cola` ★・`qiu2020firm` ★ grep) が、強度は CPU 重みなしの素の req/s。**本研究はその強度を CPU 重みにして、1 周の重さが違う OB と SS を同じ意味で揃えた**、と書ける。
- [ ] **方法節 (重みの不確かさ)**: 重み D_c は測る範囲で動く (OB 0.25 ↔ 0.22)。『重みは基準点で固定、動く幅は不確かさとして併記』と書く。DB 等 (SS の MongoDB・MySQL、OB の redis) を入れた版と抜いた版の 2 通りの配合を出し、差を示す (**未実施。数値は私は見ていない**。出所スクリプト: TODO)。
- [ ] **方法節 (上限の制約)**: 格子の全点で『律速サービスの予測使用率 max_k U_k ≤ u_max』(U_k = (c_k + β_k b + ν_k v) / (θ r_k))。台数に依存しない (限界を実測しない)。OB の除いた 2 点だけが超えるかの確認は未実施 (§9.8 と同じ TODO)。
- [ ] **方法節 (softirq を含めない理由)**: 物差しは cgroup CPU (アプリのコンテナ合計)。softirq は同居の効果を測る**従属変数**なので、物差しに入れない。分離で重みを固定するので、全アームで強度の意味が同じ。
- [ ] **限界 / 査読への備え**: (i) 『単独の限界に対する割合の和で 1 つにまとめなかったのはなぜか』→ 台数で限界が変わり、律速も型で違う (OB は buy=email、view=frontend)。割合の和は保守側の近似で、律速が同じときだけ厳密 (§11.2、**私の導出で文献ではない**。論文に書くなら 3 行の証明を付録に)。(ii) 『単一の数に潰すと予測が外れるのでは』→ `lazowska1984qsp` ★ 第 7 章が単一平均クラスの誤りを示す。総提供負荷は座標としてのみ使い、台数の予測はサービス別の β, ν で行う。(iii) 『別アプリで配合を揃える慣行は？』→ 見つからなかった (WebSearch と一部 PDF のみ。Scholar/IEEE/ACM 横断は未実施)。PARTIES は各アプリの max load に対する割合 (`chen2019parties` ★)。
- [ ] **考察 / Related Work**: 『律速が型で違う』ことの前例として TPC-W (WIPSb はフロント律速、WIPSo は DB 律速、WIPSo は WIPS の 1/3〜1/2。`tpcw2000smith` ★ 通読。年は未確認)。『配合が固定でないと 1 型では数えられない』の対比として TPC-C の tpmC (`tpcc510` ★ 5.2.3, 5.4)。
- [ ] **Related Work**: 『型ごとの呼び数 → 資源』の推定の先行として DeepRest (`chow2022deeprest`、**abstract のみ=引用前に本文を読むこと**)。
- [ ] **任意 (脚注)**: 『購入 1 周 = 1 単位、閲覧 1 周 = ρ_app 単位』の作法は Cosmos DB の RU と同じ (`cosmosdbru` ★、公式ドキュメント=査読論文ではない)。
- [ ] **次点案 (2 次元の実行可能領域の図) を採るなら**: 閉ループの飽和セクタ (`balbo1996common`・`balbo1997multiple` abstract のみ) と律速の列挙 (`anselmi2010bottleneck` ★ 序論・2 章) を引き、**本研究は開ループなので領域は半平面の共通部分になる**と断る (導出は私の考察)。

### 9.11 切片 c の呼び方と「c が違うと台数は揃わないのでは」への答え (2026-10-29 追加)

- [ ] **方法節 (用語)**: D = c + β·buy + ν·view の c は**回帰の切片 (負荷に比例しない固定分)** と書き、「アイドル」と呼ばない。負荷 0 で測ったアイドル (OB 0〜20 m 程度、10/07 混合負荷の記録) より大きい (OB 1 台: front 248 m・catalog 137 m・reco 122 m、`km2/experiments/rightsizing/analysis-rho2.txt`) = 測定範囲内の曲がりを含む。§10 冒頭の「c は負荷が無いときの CPU (アイドル)」も直す。
- [ ] **方法節 (枠の式)**: pdist / pdist-k3 の枠は r = D1 / (θ·n0) (θ = 0.50、n0 = 1 / 3)。D1 = 基準配合 b50v150・1 台の**実測平均** (`km2/experiments/rightsizing/results-mix-cpu2.csv`、6 サイクル。1.5 で割ると `rightsize-pdist-k3.csv` と全サービス一致を 2026-10-29 に確認)。D1 は c を含むので、基準配合では c に関係なく全サービスの利用率が θ/N に揃う。pdist-k3 の表を作ったスクリプトは見当たらない → **出所スクリプト TODO**。
- [ ] **査読への備え (「ρ は D − c の向きしか見ていない。c がサービスで違えば台数は揃わない」)**: ~~「c の影響は ρ より一桁小さい (front−reco 1〜4% / front−cart 6〜25%)」~~ → **2026-10-29 アヌビス判定「要修正」(自分で analysis-rho2.txt 56〜68 行目を確認)**: 比 R = D(今)/D1 = (a+L)/(a+L0) は、配合だけを動かすと ρ が、総量を動かすと a = c/β が効くので、どちらが大きいかは**配合の動く向き次第**で一般論にならない。front−cart は a も 25 違うので「c 対 ρ」の比較として交絡 (分解すると b150v150 では a の寄与 ≈ ρ の寄与)。実測 (モデルなし、1 台) では front/reco が低負荷 b0v75 で 1.19・b25v0 で 1.15 とずれ、front/cart は b50v300 で 1.03 しかずれない。最大 |ln| は front/reco 0.17 対 front/cart 0.34 (2 倍、一桁ではない)。書くなら「ρ がほぼ等しい front と reco では、本実験の配合 (b100v0 / b50v300 / b100v200) での R の差は 2〜4% で、大部分は a の差から来る。ρ が 0.17 違う front と cart では 9〜20% (b50v300 だけはモデル 6.5%・実測 3.0%)。低負荷では ρ が等しい組でも実測で 15〜19% ずれる」+ a だけ / ρ だけの分解表。b150v150 は格子外 (外挿) なので使わない。b100v200 も格子外と明記。前提「合計 CPU は台数に依らない」は近似 (1→2 台で β は front +30%・cart +36%、D2/D1 は front 1.10〜1.16・cart 1.20〜1.27、3 台以上は未測定) → 限界に書く。実測の裏付け: pdist-k3 で front+reco 1/12 回・front+cart 6/12 回引きずり (`km2/experiments/rightsizing/analysis-pdistk3.txt` §2)。**出所スクリプト TODO** (アヌビスの一時検算は scratchpad r.py のみ。`usage_mc` が計測窓だけの平均かは未確認)。
- [ ] **注意**: 「c は打ち消されて消える」は、枠に同じ c が入り、かつアイドルが Pod ごとにかかる場合だけの話。OB では 2 台目で増えるアイドルは 0〜20 m 程度で、合計 CPU は台数にあまり依らない (`rightsizing-formula-accuracy` メモ) → 一般には消えると書かない。
- [ ] **査読への備え (「引きずりで増えるのは予約枠だけ。実害はあるのか」) (2026-10-29 追加)**: 本研究の実測では、引きずられた 1 台の実消費 CPU はほぼアイドル分 (混合負荷 2026-09-02 で全体の 2.4%、メモリ coloc-gain-replica-saving) で、損は予約枠 (枠 1 台ぶん、pdist で +234〜+1431 m、`km2/experiments/rightsizing/analysis-pdist.md` 26 行目) に出る。実害の経路として書けるのは、(i) スケジューラは requests で Pod を詰めるので、予約枠が増えると同じノードに載る Pod が減り Pending になる (本研究でも 300 周/s でノード容量不足の Pending を観測、メモリ hpa-throttling-blindspot)、(ii) Cluster Autoscaler は requests で載らない Pod を見てノードを足す、(iii) GKE Autopilot などは requests で課金する。(ii) は**公式ドキュメントを読んで bib に入れてから引用** (未読、bib key 未定)。(iii) は **2026-10-29 に公式ドキュメントで確認**: Autopilot の汎用 Pod (container-optimized compute platform、Balanced / Scale-Out) は **Pod-based billing = Pod の resource requests (CPU・メモリ・一時ストレージ) に秒単位で課金**、特定のハードウェア (マシンシリーズ・アクセラレータ) を選んだ Pod は node-based billing (ノード代 + 管理料) で requests 課金ではない (GKE Autopilot overview、最終更新 2026-10-26 UTC、https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-overview)。課金対象は Pod の「effective resource request」= アプリコンテナの requests の和 (init コンテナ最大との大きい方) → 同居 Pod の予約枠の和と同じ数え方 (Resource requests in Autopilot、最終更新 2026-10-26 UTC、https://docs.cloud.google.com/kubernetes-engine/docs/concepts/autopilot-resource-requests)。**ただし「そのまま」ではない**: 最小 CPU は bursting 対応クラスタで 50m (非対応は 250m・0.25 vCPU 刻み)、CPU:メモリ比の制約 (汎用 1:1〜1:6.5) を外れると小さい方が自動で引き上げられる → 本研究の小さい枠 (payment 24m 等) はそのままの額にならない。メモリも課金対象 (本研究は CPU のみ)。料金ページ本体 (https://cloud.google.com/kubernetes-engine/pricing) は JS 描画で本文を取得できず、「秒単位・最低時間なし」は検索結果の抜粋のみ → **引用前にブラウザで料金ページを確認**。bib key 未定 (@misc で 2 ページ)。メモリ (requests) と起動時の CPU の跳ね上がり (ad で約 580 m、plan-pdist-k3.md) も 1 台増えるごとのコストとして触れられる。
- [ ] **方法節 (softirq を指標にする理由の書き方、2026-10-29 追加)**: FOSE 本文 `FOSE2026-TeX-UTF8/fose2026.tex` 78 行目「同居で減るのは Pod 間転送のカーネル処理時間であるため，同一ノードの便益は softirq で測る」は言い過ぎ。softirq はカーネル処理の**一部** (受信側の処理・veth の受け渡し・ブリッジ転送・iptables/conntrack) で、送信側の syscall 処理は system 時間に入る。同じ移動で softirq −47.1% に対し通信処理の総 CPU は −7.2% (メモリ icter-affinity-replication、出所 `km2/experiments/edge-traffic/results-icter-affinity.csv` → 総 CPU の定義と列を要確認)。また loopback も softirq を通る (なくなるのではなく経路が短くなる)。修論では「減るのは運ぶ量ではなく 1 パケットごとのカーネル処理 (veth・ブリッジ・iptables/conntrack) で、これらは主に softirq 文脈で実行されるので softirq の CPU 時間で測る」と書き、system 時間も併記する。softirq はノード全体の値で、k6 の通信や監視の通信も含む (全構成で共通) と書く。
- [ ] **要確認 (2026-10-29、カーネル設定から推論・未実測)**: このノードのカーネルは `CONFIG_IRQ_TIME_ACCOUNTING` が無効 (`/boot/config-$(uname -r)`)。この設定では、コンテナのプロセスの文脈でその場で実行された softirq (veth/loopback の送信直後など) は /proc/stat では softirq に数えられつつ、**そのプロセスの cgroup の CPU 使用量にも入る**はず (ksoftirqd で実行された分は入らない)。メモリの「softirq はどのコンテナ cgroup にも計上されない」「HPA の盲点」(hpa-scaling-angle、softirq-cpu-metric) は一部しか正しくない可能性がある。FOSE 本文には cgroup の主張は無い (grep 確認済み)。修論で盲点の話を書くなら先に実測で確かめる。

### 9.32 予約枠 (requests) を減らすことの意味 = 動機の根拠 (2026-11-05 追加。FOSE 発表スライド用に調査)

§1 / §2 で「予約枠の余剰 (粒度損) はなぜ損なのか」を事実で支える。bib は**全て未登録** (key は仮)。
- [ ] **ノードの空きは使用量でなく予約枠で埋まる**: Kubernetes 公式 "Resource Management for Pods and Containers" §How Pods with resource requests are scheduled (仮 key `k8sresources`, ★原文 2026-11-05 確認):
  > "The scheduler ensures that, for each resource type, the sum of the resource requests of the scheduled containers is less than the capacity of the node. Note that although actual memory or CPU resource usage on nodes is very low, the scheduler still refuses to place a Pod on a node if the capacity check fails."
- [ ] **ノード台数の増減も予約枠で決まる**: kubernetes/autoscaler の Cluster Autoscaler FAQ (仮 key `caFAQ`, ★ 2026-11-05 確認、要約経由): 増設は「資源不足でどのノードにも置けない Pod があるとき」、削減候補は「Pod の requests 合計がノードの allocatable の 50% 未満」(既定値)。**引用前に FAQ の該当文を逐語で取り直すこと** (WebFetch の要約で読んだため)。
- [ ] **課金が予約枠そのものに付くサービスがある**: GKE Autopilot "Resource requests in Autopilot" (仮 key `gkeautopilotreq`, ★ 2026-11-05 確認): "you might notice charges that aren't consistent with the actual resource usage of the Pod" 等。AWS Fargate も同様とされるが**未確認**。
- [ ] **金額** (GKE pricing ページ `https://cloud.google.com/kubernetes-engine/pricing`、仮 key `gkepricing`、★ 2026-11-05 に HTML を取得して原文確認): "In the Pod-based billing model, you are charged in one-second increments for the CPU, memory, and ephemeral storage resources that your running Pods request ... with no minimum duration" / "With the Pod-based billing model, the underlying node size or quantity doesn't matter for billing" / 待機中 (未スケジュール) の Pod は課金しない。
  単価 (Iowa us-central1、汎用 Pod、取得日 2026-11-05): vCPU $0.0445/h、メモリ $0.0049225/GiB·h、Spot vCPU $0.0133/h、GKE CUD 3 年 $0.024475/h。クラスタ管理料 $0.10/h、無料枠 $74.40/月。**東京 (asia-northeast1) の単価は JS 表示で取得できず**。
  換算 (1 か月 = 730 h、私の計算): 1 vCPU = $32.5/月 (Spot $9.7/月)、100m = $3.25/月、予備実験の予約枠 6.3 コア = $205/月。**注意**: Autopilot は最小値・CPU:メモリ比に満たない requests を引き上げるため、ミリコア単位の削減がそのまま料金差にならない場合がある (同ページ)。
- [ ] **EKS / AKS の課金** (2026-11-05 取得。単価は各社の公式価格 API、文言は公式ページの HTML から):
  - **EKS on Fargate** = 予約枠に課金。AWS 公式 "Fargate Pod configuration" (仮 key `eksfargatepod` ★): "the vCPU and memory reservations within the Pod specification determine how much CPU and memory to provision for the Pod" / "Requests for all long-running containers are added up" / "Fargate rounds up to the following compute configuration" (0.25, 0.5, 1, 2, 4, 8, 16 vCPU) / "the requested CPU and memory must be equal to the limit"。料金ページ (`fargatepricing` ★): "Pricing is based on requested vCPU, memory ..."。単価 (AWS Price List API, Linux/x86 On-Demand): 東京 vCPU $0.05056/h・メモリ $0.00553/GB·h、バージニア $0.04048/h・$0.004445/GB·h。
  - **EKS (EC2 ノード・Auto Mode)** = ノード課金。クラスタ $0.10/h。Auto Mode は EC2 料金に上乗せ (`ekspricing` ★)。
  - **AKS (Standard / Automatic)** = ノード (VM) 課金: "Compute charges are based on the duration and type of virtual machines launched and managed by AKS" (`akspricing` ★)。管理料 Standard $0.10/h、Automatic の Hosted Control Plane $0.16/h、Automatic は VM に上乗せ料 (Retail Prices API の meter "Automatic General Purpose" 東日本 $0.011369/h・米東部 $0.007841/h。**単位が vCPU あたりかは未確認**)。Automatic は "creates nodes based on workload requests" (`aksautomatic` ★)=台数経由で予約枠が効く。
  - **Azure Container Instances (AKS の virtual nodes の実体)** = 割り当て (container group) に課金 (`acipricing` ★)。原文 (2026-11-05): "Container groups are co-scheduled containers that share the same network and node lifecycle" (= Pod 相当の単位) / "charged based on the vCPU request for your container group **rounded up to the nearest whole number**" / メモリは 0.1 GB 単位に切り上げ / "a minimum of 1 vCPU and 1 GB ... up to 4 vCPU to each container group"。ACI 単体は K8s ではなく HPA も無い。東日本 vCPU $0.0506/h・メモリ $0.00553/GB·h。**AKS virtual nodes で Pod の requests がそのまま container group の大きさになるかは未確認**。
  - 換算 (私の計算、730 h/月): 1 vCPU/月 = GKE AP(Iowa) $32.5、Fargate 東京 $36.9・バージニア $29.6、ACI 東日本 $36.9。
  - **考察 (私の推論・未検証)**: Fargate は Pod ごとに requests 合計を 0.25 vCPU 刻み以上に切り上げるので、小さいサービスを同居させると切り上げの無駄が減る可能性がある (例: 0.1 vCPU×3 を別 Pod = 0.25×3 = 0.75、同居 = 0.3→0.5)。メモリとの組み合わせ制約で変わるので、言うなら計算例を付けて条件を書く。
- [ ] **予約枠課金の普及度** (§1 で「予約枠課金は珍しくない」と言うなら。2026-11-05 原文確認 ★):
  - Google Cloud Blog "GKE Autopilot now available to all qualifying clusters" (2025-09-25, 仮 key `gkeautopilotblog2025`): "in 2024, 30% of active GKE clusters were created in Autopilot mode"。事業者自身の数字。2025 年以降の数字は見つからない。
  - Datadog "10 insights on real-world container use" (2023-11, 仮 key `datadog2023container`、24 億コンテナ・数万顧客): "46 percent of container organizations now run serverless containers"、Google Cloud では 68%。**ただし定義に Cloud Run・ECS Fargate・App Runner・Container Apps など K8s でないものを含む**ので「K8s の予約枠課金の普及率」としては使えない。Datadog 顧客に偏った標本。
- [ ] **便益 (softirq 削減) は利用者の請求に直接は出ない** (限界 / 査読への備え、2026-11-05): GKE pricing 原文 "You are not charged for unmodified system DaemonSet Pods, operating system overhead, unallocated space, or unscheduled Pods" (★ 2026-11-05 取得の HTML で確認)。softirq はノードのカーネル処理 (cgroup 外) なので、Autopilot では利用者に課金されない側。金額に効くのは「予約枠の増減 (粒度損・台数)」の側だけ。Fargate は 1 Pod = 1 微小 VM なので、Pod 内のカーネル処理が予約した vCPU を食う可能性がある (**私の推論、未確認**)。発表・論文では「同居で安くなる」ではなく「**相手を誤ると粒度損がそのまま請求額になる**」と書く。
- [ ] (任意・弱い) 業界統計「予約枠の多くが使われていない」(Datadog State of Cloud Costs 2024 の workload idle 29% など) は**二次情報のみ**。使うなら Datadog 原典を読んでから。
- [ ] **本研究の観測** (300 周/s でノード容量不足 → Pending、HPA 実験): 出所 = `km2/experiments/summer2026/results-prescale.csv` (2026-08-30、frontcatalog・開始 3 台・3 サイクル、索引 EXPERIMENTS.md の「実験8/30 (300)」行)。3/3 回で Pending 2〜7 個 (予約 2.0〜3.0 コア分)、稼働中の予約 14.1 コア、`node_cores` 列 11.0〜12.0。対照 `results-prescale250.csv` (250 周/s) は Pending 0/3。**`node_cores` 列の定義 (実使用か) は旧版スクリプトで未確認** — 本文に「実使用は○コアで空いていた」と書く前に確認する。
- [ ] **実運用で「増やした Pod が載らない」は起きるか** (2026-11-05 調査、§1 の動機 / 発表):
  - Buildkite 障害報告 (2026-08-25、公開 08-27、`https://www.buildkitestatus.com/incidents/tm6746k61p73`、仮 key `buildkite2026` ★原文): EKS で負荷急増 → "This surge consumed the available headroom on already-deployed Nodes" / "The headroom shortage and subsequent cluster autoscaling delayed provisioning of the compute requested by those services"。CoreDNS が溢れ全顧客の API・ジョブ配布が約 30 分停止。**ノード自動追加があっても間に合わなかった例**。
  - BasedHardware/omi Issue #7280 (2026-05-13、本番 `prod-omi-backend`、★原文): HPA が 26 台以上を要求、Pending 2 個、"0/29 nodes available: 11 Insufficient cpu ..."、"Node CPU usage: 4-21% actual, but resource requests fill the scheduler budget"。**実使用は低いのに予約枠で詰まった本番例** (OSS の Issue であって査読論文ではない)。
  - Cluster Autoscaler FAQ (★): 対策として低優先度の pause Pod による overprovisioning を公式に案内 / "The time of new node provisioning doesn't depend on CA, but rather on the cloud provider" / 登録待ちは既定 15 分 (`--max-node-provision-time`) / "cloud provider stockouts" を扱うと明記。
  - 未取得: k8s.af (Kubernetes 障害事例集) の個別事例、AWS の InsufficientInstanceCapacity 公式ページの原文。
- [ ] **想定問答「引きずりがゼロでも予約枠は分離と同じでは？」** (2026-11-05 ユーザの指摘): 予約枠では最良でも分離と同等が基本 (正しい)。分離より減るのは、同居で cgroup CPU が下がって整数台数が 1 段下がるときだけ (在庫: front+catalog 200 周/s で 2 台 vs 分離 frontend 3 台 = 約 1.08 コア、メモリ `coloc-gain-replica-saving` の記録のみ・**今回未検算**。cgroup CPU の減りは −1.7〜2.9% と小さい = `analysis-scale3.md`)。便益の本体 (softirq) は cgroup 外で予約枠にも HPA にも Autopilot の請求にも現れない。→ 書き方: 本研究は「予約枠を減らす研究」ではなく「**予約枠を増やさずに同居の便益 (ノード CPU・容量・遅延) を取れる相手の条件**」。
- [ ] **Kubernetes を対象にした理由** (§1、2026-11-09): ①普及 = CNCF 2025 年調査 (発表 2026-01-20、仮 key `cncf2025survey`、★発表の題名で確認、報告書本文は未読) "82% of container users now running Kubernetes in production" (2023 年 66%)。分母はコンテナ利用者 ②HPA が標準機能 (先行研究 Wickramanayaka は Docker Swarm で自動スケールを扱わない) ③Pod が同居の単位として標準 = 公式 "A Pod ... is a group of one or more containers, with shared storage and network resources" / 水平スケールは "use multiple Pods, one for each instance" (`k8spods` ★)。
- [ ] **「affinity では選べない」の例示の仕方** (2026-11-09 ユーザの指摘、発表・修論 §4): 「最大 38.8% は入れ替わらず 0% が入れ替わる」は弱い (0% の組は affinity 基準ならそもそも選ばれない)。問題は「affinity で選ばれうるのに入れ替わる組」。表 1 の 6 組の中では **frontend+cart (4.1%) が入れ替わり、ほぼ同じ frontend+reco (4.8%) と、より少ない checkout+email (1.7%) は入れ替わらない** = affinity の順位で選ぶと cart を checkout+email より先に選んでしまう。**限界**: 6 組の中で最大の組 (catalog) は入れ替わらないので「affinity 1 位を選ぶと損」とは言えない。全エッジ中の cart の順位は未確認 (`km2/experiments/edge-traffic/` で要確認)。→ **2026-11-09 確認**: `km2/experiments/edge-traffic/edge_pair_shares.py` (論文 §4 の affinity の出所、購入100_閲覧0・分離・全サービス 1 台) を実行すると、frontend+cart は**全 15 組中 6 位** (1 catalog 38.8 / 2 catalog+reco 18.4 / 3 currency+frontend 8.5 / 4 cart+redis 5.2 / 5 frontend+reco 4.8 / 6 cart+frontend 4.1 / … / 10 checkout+frontend 2.5 / 13 checkout+email 1.7 / frontend+email はエッジなし)。**限界**: 2 位・3 位の組 (catalog+reco、currency+frontend) は表 1 で未実験なので「affinity 順に選ぶと 6 位で初めて失敗する」とは言えない。順位は購入のみの負荷での値で、閲覧を増やすと変わりうる。
- [ ] **同居の得の大きさ (ノード全体で見ると小さい)** (2026-11-08 会話中に計算、発表の質疑への備え): `km2/experiments/summer2026/results-fixed4.csv` (4 台固定・HPA 無し・振り分け無し、各点 3 サイクル平均) の `node_cpu_sec` と `softirq_cpu_sec` から。softirq がノード CPU に占める割合 = 分離 7.3〜7.8% / front3 6.0〜6.2% / mega 4.3〜4.4%。ノード CPU 合計の分離比 = front3 −2.0% (150)・−2.6% (200)・+0.5% (250)・−0.5% (300)、mega −10.0%・−8.0%・−7.8%・−2.4%。→ 単一ノードでは front3 の得はノード全体で数%以下。`node_cpu_sec` に k6 の CPU が含まれるかは未確認。振り分けあり版 (`results-fixed4-lb.csv`) は分離側が振り分けで +9〜18% 増えるので得として数えない。**TODO: 会話中のアドホックな計算で、再計算スクリプトなし**。本文・発表に数値を出すならスクリプト化して provenance に書く。
- [ ] **損の話は GKE Autopilot に絞る** (ユーザ決定 2026-11-05、発表)。Fargate・ACI は切り上げの向きが逆になりうるので触れない。

---

### 9.12 Prometheus の生データは 10 日で消える (再現性・限界、2026-11-02 追加)

- [ ] **確認した事実** (2026-11-02 22:25、kubectl で確認): Prometheus (kube-prometheus-stack, v3.12.0) は保持期間 `retention=10d`、容量上限なし、保存先は **emptyDir** (PVC なし)。この時点で最古のデータは 2026-10-23 21:00。ブロックは約 2.0 GB。
- [ ] したがって **mix-cpu2 (10/09〜10)、pdist-k3 (10/15〜16)、fixed4-lb (10/07〜08) は Prometheus 側の生データがもう無い**。残っているのは、スクリプトが測定時に問い合わせて書き出した CSV (`results-*.csv`・`-series.csv`・`timeline-*.csv`) とログだけ。方法節か付録に「各測定点の値は測定直後に PromQL で取り出して CSV に保存した。Prometheus の時系列そのものは保存していない」と書く。
- [ ] 査読への備え: 「区間の取り方を後から変えて再計算できるか」には、**できない** (CSV の粒度でしか再解析できない) と答えることになる。2026-11-02 22:28 に保持期間 180 日・保存先 PVC (microk8s-hostpath 100Gi) へ変更済み (ユーザ指示、旧データは消去)。ユーザは ◎ 実験をやり直す方針なので、やり直し後の実験は 180 日以内なら Prometheus から再解析できる。論文用に生データ (TSDB スナップショット) を長期保存するかどうかは未決。
- [ ] 出所: このメモ自体 (確認コマンドの出力)。スクリプトは無い — TODO なし (設定値の読み取りのみ)。

### 9.13 測定スクリプトが設計どおりに測ったことの示し方 (方法節 + 限界、2026-11-03 追加)

- [ ] **書き方の範囲を限定する** (アヌビス 2026-11-03): 「スクリプトが設計どおり動いたことを確認した」とは書かない。「新しく採るデータについては、時刻と区間を独立な記録 (kubelet のコンテナ開始時刻、cAdvisor の CPU カウンタ) と照合できる仕組みを入れ、スモーク 4 点で整合を確認した。既存の mix-cpu2 は同一コード (git diff c4ce1d1..2ee602a で測定式・時刻計算が不変) による間接的根拠のみ」。出所: `km2/experiments/rightsizing/smoke/smoke-times-20261102*.csv`、索引 `km2/experiments/summer2026/EXPERIMENTS.md` smoke-times 行。照合スクリプトは TODO (今回はアヌビスと Claude が手で照合)。
- [ ] **独立 / 自己申告の区別を書く**: 自己申告 (AI が書いたコードの出力) = prom_from/prom_to・t_run・k6_start・達成率・取りこぼし。独立 = kubelet のコンテナ開始時刻、cAdvisor の CPU 生サンプル、Pod の phase/ready/再起動、ノード CPU。ただし CPU の値はどの経路も cAdvisor が出所で、別の測定器による確認ではない。
- [ ] **CSV と Prometheus の再問い合わせの一致は「再現性」であって「妥当性」ではない**と書き分ける。
- [ ] **負荷量 (周/s) は k6 の自己申告しかない**ことを限界に書く。達成率の定義は「計測窓内で開始した周回数 ÷ 秒」(完了数ではない)。k6 を通らない確認 (frontend のアクセスログの行数など) は未実施。
- [ ] **記録の細かさ**: cAdvisor の収集設定は 10 秒だが実際のサンプル間隔は約 11〜20 秒 (平均約 15 秒)。「10 秒ごと」と書かない。
- [ ] **慣らし負荷の実態**: 「慣らし 180 s」(plan-rho2.md) は実際には「180 s 負荷 + 約 120 s 待機」(k6 Job の sleep 300 で complete 待ちがタイムアウトまで続く)。方法節にはこの形で書く。
- [ ] **series (10 秒系列) は使っていない**と明記する (30 s 窓に Pod が抜けた合計が混入しているため)。
- [ ] **主データ (rate) の端の扱いによる過小評価** (2026-11-03 Claude が発見・1 行で手計算により機構を確認): Prometheus の rate() は、区間の端と最初/最後の記録の空きが「記録の平均間隔 × 1.1」以上だと、その空きを半間隔ぶんしか延長しない。それでも区間の長さ全体で割るので、値が低く出る。スモーク (区間 70 s) では 48 行中 4 行が 8〜15% 低かった (例: b100・1 台の paymentservice、CSV 60.9 m ↔ 記録の間だけの平均 69.8 m)。本番 (区間 160 s) の mix-cpu2 そのものは測れない (Prometheus のデータが無い) が、**同じ設定のスモーク smoke-prod-20261103 (2026-11-03) で実測: 72 行中 11 行で 1% 超低く、最大 7.5%、高く出た行は 0** (出所 `km2/experiments/rightsizing/smoke/smoke-prod-20261103.csv` と `-series.csv` の時間重み付き平均の比較。比較スクリプトは TODO、Claude がその場で計算)。**2026-11-03 ユーザ決定: 主データの計算は変えず、研究の限界として明記する**。書く内容 = 「区間平均は Prometheus の rate() による。区間の端と記録の空きが平均間隔の 1.1 倍以上のとき延長が半間隔に制限され、値が低く出る (区間 160 s の同設定スモークで 72 行中 11 行が 1% 超低く、最大 7.5%)。向きは常に過小で、起きるかは記録のタイミングで偶然に決まる」。なお 2026-11-03 以降の実験は生の記録 (`<CSV>-raw.csv`) を残すので、必要なら後から再計算できる。出所: `km2/experiments/rightsizing/smoke/smoke-times-20261102.csv` と同区間の生の記録 (Prometheus、2027-05 まで保持)。照合スクリプト TODO。
- [ ] **HPA 実験 (bundle-vs-loss2.sh) の Prometheus の区間は k6 の計測窓から数秒はみ出す可能性** (2026-11-04 Claude がオフライン検証で気づいた、実測は未): このドライバは WARM+MEAS 秒眠った直後に「いま」から MEAS 秒さかのぼって node_cpu_sec / softirq_cpu_sec / k6_cpu_sec を取る (内側への余裕なし)。k6 は t_run より約 1.6 s 早く始まる (mix-cpu3 実測) ので、区間の終わりが k6 の窓の終わりより約 3〜5 s 後ろにずれ、負荷が止まった後の数秒が入る見込み。pdist-k3 など過去の HPA 実験 (FOSE の softirq/CPU 時間を含む) は問い合わせ時刻を記録していないので確かめられない。2026-11-04 からドライバが `-times.csv` に実際の区間と余裕を書くので、次の実験で大きさを実測してから書き方を決める。台数の判定 (timeline) には影響しない。出所: `../experiments/summer2026/_write_extras.py`、TODO 実測値。経緯 (git と コメントから): 第 1 版 (8 月) は rate[MEAS×5/6] を「いま」で取り始め側だけ 40 s 余裕、第 2 版 (9/09) が長さを窓に揃えるため increase[MEAS] に変えて余裕が 0 になった。前提「t_run から WARM+MEAS 後 = k6 の窓の終わり」は k6 の開始時刻を記録していなかった (11/02 まで) ため確かめようがなく、mix-cpu (10/07) は逆向き (k6 が遅れる) を想定していたが両端 10 s の余裕で守られていた。6 月のメモリ exact-window-measurement の「絶対時刻で聞く」方法は k6 のドライバに引き継がれていなかった。**2026-11-04 ユーザ決定で直した**: bundle-vs-loss2.sh も mix-cpu と同じく区間を時刻で固定し、窓の両端 10 s を削った内側 (MEAS−20 s) の increase を取る。以後の node_cpu_sec / softirq_cpu_sec / k6_cpu_sec は「内側 220 s の CPU 秒」で、それ以前 (240 s、終わりが数秒はみ出す) とは比べない。方法節には「計測窓 240 s の両端 10 s を除いた 220 s の CPU 秒」と書く

### 9.14 pdist-k3 やり直しの温度・周波数と結果の関係 (2026-11-07 追加)

- [ ] **限界 (方法節 or 限界)**: pdistk3sep2 / pdistk3pair2 (2026-11-06〜07) はノードの最高温度が 74〜100℃ (100℃ は分離 3 回・同居 2 回)、平均周波数 2.69〜3.40 GHz。周波数は固定していない (§8 の方針)。
  同じセル (アーム × 配合) の中で温度と比べた相関 (セルごとに平均を引いてまとめた r): 主指標の台数合計は 分離 +0.21 / 同居 −0.08、周波数は −0.18 / +0.18、購入 p50 は +0.29 / 0.00、ノード CPU 秒は +0.41 / −0.12 (分離 n=48、同居 n=72)。
  書ける形: 「温度と台数・周波数・遅延のあいだに、分離と同居で揃って現れる関係は見られなかった」。分離のノード CPU 秒 +0.41 は単独では有意水準を超えるが同居で再現せず、約 20 通りの比較の 1 つなので主張しない。
  注意: temp_max_c は区間内の全センサーの最大値で、熱による周波数低下 (サーマルスロットリング) を直接示すものではない。出所 = `km2/experiments/summer2026/results-pdistk3sep2(-times).csv`、`results-pdistk3pair2(-times).csv`。**TODO: 計算はその場の Python で、スクリプトとして残していない**。

### 9.15 SS の ρ の定義域と、周波数 (DVFS) による ν の偏り (2026-11-10 追加、アヌビス判定)

- [ ] **方法節 (指標の定義域)**: ρ = ν/β は β≈0 のサービスで定まらない。SS の catalogue は β=0.088 で ρ=8.38 [5.26, 18.50]、b48v240 を除くと β=−0.028・ρ=−25.6 (`sockshop/experiments/analysis-rho-ss3b.txt`)。購入型 6 つ (carts, orders, payment, shipping, user, queue-master) は β が大きく ρ は定義でき区間も狭い (≈0)。
  書く形: catalogue は「ρ は定義できない (購入でほぼ動かない)」とし、取り分 s = ν/(β+ν) (= ρ/(1+ρ)、ρ>0 で順序を保つ) か角度で示す (アヌビス: catalogue の s = 0.893 [0.838, 0.949]、除外後 1.041)。主指標を s に替えるかは**ユーザ未決**。
- [ ] **限界 → 交絡として扱う (★重要)**: 購入型の ν<0 は「閲覧の仕事」でなく、閲覧を足すとノードの周波数が上がる (DVFS、固定していない) ことの影響が大きい。SS 1 台、front-end 行の freq_ghz (閲覧 0/80/160/240): b16 1.81/2.05/2.37/2.72 GHz、user の D は同じ順に 103.8/79.0/67.7/65.0 m。D×周波数で当て直すと購入型 6 つの ν はすべて正に反転し (ρ 0.001〜0.021)、front-end の ρ は 0.290→0.215 (自分で再計算して確認)。OB (mix-cpu3) も front 0.357→0.298・catalog 0.345→0.292・reco 0.366→0.310 と揃って下がる (アヌビスの計算、近い/遠いの分類はおおむね残る見込み)。§10 の縮尺感度 (周波数補正で揺れが半分以下) とも整合。
  ただし freq_ghz はノード全コア平均の要求周波数で、D×f も一定にならない → 事後補正は不十分。**書くこと**: 購入型は「ρ≈0 の 1 群」とし群内の差は解釈しない。補正前後の ρ を感度表として OB・SS 両方に載せ、近い/遠いの分類が変わらないかを示す。対策の候補 = ρ の測定だけ周波数を固定して再測定 (1 台 × 15 点 × 2〜3 サイクル)、または turbostat の APERF/MPERF でコア別の実効周波数を記録。どれをやるかは**ユーザ未決** (§8 の「固定しない」方針 2026-10-19 との関係)。
- [ ] **方法節 / 査読への備え (しきい値と切片)**: OB の「Δρ ≤ 0.02 = 近い」はアプリの「1 周」の定義で目盛りが変わるので SS に持ち込まない。単位に依存しない量としてモデルを使わない利用率比の振れ幅 max|ln(P_s/P_t)| (基準配合で正規化、運用範囲の配合で) を併記する案。SS の購入型どうしの振れ幅 (0.05〜0.21) は ρ の差と対応せず、切片の比 c/β (carts 3.0、shipping 2.9、user 7.1、payment 5.2) で説明される (アヌビス)。査読で「ρ は c を無視している」と突かれる。
  出所: アヌビスの検算はスクラッチの chk.py / p.py / b.py / ob.py で、**正式な出所スクリプトは TODO**。

### 9.16 Sock Shop の Java 起動 CPU と HPA の暴走 (2026-11-10 追加。詳細・原文引用は §12)

- [ ] **方法節**: Java 4 サービス (carts / orders / shipping / queue-master) の readinessProbe を遅らせた (または遅らせる) 理由 = HPA は Ready でない Pod の CPU を平均から除く (K8s doc の Algorithm details + 専用節 "Pod readiness and autoscaling metrics"、実装 `replica_calculator.go` の `groupPods` で確認)。bib: `k8shpa` (★原文確認 2026-11-10)、`k8sprobes` (★)。公式が *"Ensure your readinessProbe only reports Ready after the CPU spike subsides, using initialDelaySeconds"* と推奨している。遅らせた秒数・理由・OB (Go) の readiness (initialDelay 10 s) と揃っていないこと (アプリ間の非対称) を書く。同居 Pod では Ready が全コンテナの AND なので、Java コンテナの遅い readiness が相手コンテナの CPU も判断から外す点は考察に書く。
- [ ] **限界 / 実験環境**: 「起動時 CPU が除かれるのは Ready になる前と、Ready 後の測定窓 1 つ分まで」(§12.2 の 1)。既定の `cpu-initialization-period` (5 分) は『起動後 5 分無視』ではない。読み違えて書かないこと。
- [ ] **Related Work**: **Dashtbani & Tahvildari 2025 (`dashtbani2025`、★本文確認)** が同じ現象 (Sock Shop の carts が起動時に CPU を食い KHPA が暴走) と readiness での対処を既に報告している。『Sock Shop の Java で暴走』を新規発見として書かない。違い = 彼らは /login のみ・50% しきい値・同居は扱わない・対処後の定量結果は本文に無い。本研究は同居 Pod 化でこの現象が粒度の議論 (Java が相手の Ready/CPU を巻き込む) とどう絡むかを持つ。
- [ ] **査読で突かれうる点**: 「Java の暴走はアプリの癖で、同居の効果と関係ないのでは」→ 答え = 暴走を抑えた設定 (readiness 遅延) を分離・同居の両方に同じく適用した上で比べている、と書ける状態にしてから主張する。「readiness を遅らせると容量到着が遅れ、HPA の追従を人為的に悪くしていないか」→ §12.2 の 3 で答える (全アームに同じ設定、遅延の秒数と台数の時系列を付録に)。
- [ ] **TODO (実測)**: 180 s 遅延 readiness にしたとき、Ready 直後 0〜120 秒の Java Pod の CPU が HPA に入って再び跳ねないか (§12.2 の 2、私の推測)。入るなら startupProbe 併用や枠の見直しが要る。出所の実測 CSV は未取得。
- [ ] **JVM 側の対策 (CRaC / AOT / native image) は使わなかったと限界か今後の課題に一文** (公開イメージのまま比較するため。一覧は §12.3)。
- [ ] **Related Work／方法節 (2026-11-10 追加、§12.8)**: 『Sock Shop の Java の起動を扱った先行研究』は、確認した範囲では Dashtbani 2025 のみ。COLA・PEMA・ScalerEval・STaleX・MS-RA・StatuScale・Buzato 系は JVM の起動・warm-up・GC に触れていない (PEMA と Buzato は Java を言語構成として一文述べるのみ)。『先行研究は Java を無視している』と強く書かず、『確認した範囲で、扱ったのは Dashtbani のみ』と限定する。STaleX は『サービスごとの起動時間で PID の周期を変える』(arXiv:2501.18734 p.4) として一行引ける (JVM とは書いていない)。査読で『readiness 遅延は恣意的』と言われたら、Dashtbani＋K8s 公式 doc を根拠にし、分離・同居の両方に同じ設定を当てたと答える。範囲 = 上記 PDF の全文 grep ＋ WebSearch 1 本。Avritzer・Camilli・Rahman、Buzato 修士論文は Java 観点で未確認。
- [ ] **(2026-11-10 追加、アヌビス対処案の判定) 実測で分かったこと 2 つ**: (1) SS の Java 4 コンテナの JVM は `openjdk 1.8.0_111` でコンテナを認識しない (UseContainerSupport / ActiveProcessorCount 無し)。ノード 16 コアを前提に `CICompilerCount=12`・`ParallelGCThreads=13` (`java -XX:+PrintFlagsFinal -version` を buygroup の shipping で実行、主任も再確認)。限界 / 実験環境の節に書く。(2) 温まった Pod でも 15 s 単位の単発の跳ねがある。台数固定 `sockshop/experiments/results-mix-cpu3b-series.csv` で「Pod の中央値 + 0.7×枠」を超えるサンプルの割合は shipping 2.8% (58/2092、最大 235m = 枠 18m の 1300%)、queue-master 1.6%、orders 0.9%、carts 0%。readiness 遅延では消せない → HPA 側の対策 (scaleUp の様子見) が要る理由として方法節に書く。出所スクリプト: TODO (アヌビスと主任のその場の python、ファイル化していない)。
- [ ] **対処案の判定 (アヌビス 2026-11-10、未実施)**: 推奨 = readiness 180 s + scaleUp stabilizationWindow 120 s・policy Percent 100/60s + WARM 300 s + 暴走の印 (最大台数 = HPA_MAX など) を付けて全件報告 (除外しない)。不可 = controller-manager フラグ (Ready 後に効かない)、CPU limit 引き下げ (スロットリング)、ウォームアップ延長だけ (減るのを待つだけ、上から下りた台数は OB と比べられない)。要修正 = JVM スレッド数の明示 (枠と ρ の取り直しが要る)、開始台数の変更 (感度分析として)、枠の下限。書くこと: scaleUp の設定を OB と変えるなら OB で同じ設定の対照を取り「台数が変わらない」と示す / arm1 では Go の payment・user も 180 s Ready にならない非対称を限界に書く / 「arm1 の損は JVM 1 つの跳ねが Pod 全体を引きずった作りものでは」への対照 (分離と arm1 の予測超えの増加回数を並べる)。引用前に原典確認: K8s HPA doc の behavior 節、KEP-853、JDK-8146115 (8u191 のコンテナ対応)。
- bib key と確認度: `dashtbani2025` ★本文 / `k8shpa` ★原文 / `k8sprobes` ★原文 / `gkestartupboost` ★原文 (ベンダ記事) / `springcrac` ★原文 (一部) / `jep515` ★原文 (Summary) / `barrett2017warmup` abstract のみ (引用前に読む)。BlaBlaCar は本文未取得のため bib に入れていない。

### 9.17 3 つ目のアプリの選定と、HPA 論文でのベンチマークの使われ方 (2026-11-10 追加。詳細は §13)

- [ ] **実験環境 (アプリの選択理由)**: 「OB と SS は HPA／オートスケール論文で最も使われる 2 つ (標本 19 本中 OB 7・SS 8)」と一文で言える (§13.2)。ただし**標本は系統的でない** (WebSearch ＋ 既存の SS 調査からの芋づる)。本文には「確認できた範囲では」と限定を付け、母集団の割合として書かない。
  bib: `sachidananda2022cola` (★PDF)、`hossen2022` (★PDF)、`qiu2020firm` (★PDF grep)、`zhang2021sinan` (★PDF grep)、`ahmad2024smarthpa` (★PDF)、`xie2024pbscaler` (★PDF grep)、`meng2023deepscaler` (★PDF grep)、`xie2026scalereval`、`wen2025statuscale`、`dashtbani2025stalex`、`nunes2024`、`dashtbani2025` (これらの確認度は bib の note に記載)。
- [ ] **Related Work (必須級・最優先)**: **Buzato & Goldman 2026 (IJNC, bib `buzato2026ijnc`、★PDF)**。HPA 下で Sock Shop の束ね方 4 通りを比べた論文で、(i) 束ねる単位は同一コンテナ内 (Pod 内の別コンテナではない)、(ii) 指標は throughput・絶対 CPU・応答時間・費用で softirq／リクエストでも予約枠でもない、(iii) 閉ループ Locust、HPA しきい値 150%、2 ノード／シナリオ、(iv) 選び方は定性的 (決定木)。
  **同じ論文が「Pod 内での束ね」を今後の課題に挙げている** (原文: "Grouping within Kubernetes Pods: Extending the research to evaluate the impact of grouping microservices within the same Kubernetes pod rather than the same container.")。これは空白の傍証として使える。一方で**同じ著者グループが次にやる可能性**があるので、投稿時期に注意し、投稿直前に再検索すること (範囲 = WebSearch のみ)。
  査読で突かれうる点: 「束ねると HPA 下で効く、は Buzato が既に示した」→ 答え = 彼らの束ねは 1 コンテナ内で、ベースライン・指標・開ループ性・予約枠の扱いが違う (本研究は Pod 内別コンテナ、softirq／リクエスト、開ループ、requests の増減)。表にして示す (§13.4)。
- [ ] **Related Work (ρ・配合に関する一文)**: Autothrottle は本文で「リクエスト型の構成は一定のまま扱う (constant workload composition)」と明記し、先行 (Sinan・FIRM) の設定に従うと述べる (NSDI '24 の Captain の『Action』の段落、Appendix A を参照、★PDF grep、2026-11-10。節番号は未確認)。配合を**振って**反応を見る本研究の位置づけの根拠に使える (`wang2024autothrottle`)。COLA は OB で購入頻度を振った例がある (§7.4)。
- [ ] **限界**: 評価アプリが 2 つ (OB、SS) または 3 つに限られる。3 つ目を採った場合は、その選択理由 (言語構成・負荷型の分離・宛先の変更しやすさ) と、採らなかった候補 (TeaStore＝全 Java、Train-Ticket＝42/47 が Java で重い) を一行ずつ書く。
- [ ] **TODO (3 つ目を決めたら)**: Hotel Reservation を採る場合、Consul 経由の宛先の扱い (同居 Pod 内で localhost に落とす方法) を方法節に書く。出所は 3 つ目のアプリの改変 diff (まだ無い)。TeaStore を採る場合は、Tomcat 待受ポートを可変にしたイメージ作り直しを方法節に書く。
- bib key と確認度: `buzato2026ijnc` ★PDF／`wang2024autothrottle` ★PDF (grep)／`park2021graf` ★PDF 一部 (途中で切れた PDF)／`goli2021waterfall` ★PDF／`horn2022moha` abstract + 間接 (本文未読。引用前に読む)。DOI を Crossref で確認済み: ahmad2024smarthpa、xie2024pbscaler、meng2023deepscaler、wen2025statuscale、xie2026scalereval、park2021graf、goli2021waterfall、buzato2026ijnc。

### 9.18 HR を評価に使った 5 本の論文 (Related Work、2026-11-12 追加。詳細は §13.8)

- [ ] **Related Work (オートスケール／資源配分の先行例)**: 『DeathStarBench Hotel Reservation はオートスケール／資源配分の評価に広く使われる (FIRM, Sinan, PEMA, Autothrottle, StatuScale)。ただしこれらは主にサービスごとの CPU 量 (垂直) の制御で、**同居による HPA の粒度の変化を扱わない**』と書く。基準は FIRM = K8s autoscaling／AIMD、Sinan = 使用率規則 (Docker Swarm)、PEMA = 規則 (RULE) と最適 (OPTM)、Autothrottle = K8s-CPU 系と Sinan、StatuScale = GBMScaler／Showar／Hyscale (HPA 自体は含まない)。
  bib: `qiu2020firm` (★本文 §4.1)、`zhang2021sinan` (★本文 §2.2・§5)、`hossen2022` (★本文)、`wang2024autothrottle` (★本文 §5・付録)、`wen2025statuscale` (★arXiv v1 の本文。公刊版との同一性は引用前に確認)。いずれも bib の note は『未引用』のまま (引用したら直す)。
- [ ] **実験環境 (3 つ目に HR を採った場合)**: 『HR の配合の既定値は Search 60%／Recommend 39%／Reserve 0.5%／Login 0.5% (Autothrottle Appendix A)』。サービス数は論文により 15 (FIRM)・17 (Autothrottle)・18 (PEMA) と数え方が違うので、DB・cache を含めるかを本文に明記する。
- [ ] **限界・査読の備え**: 『HR は通過サービス数が少なく (Autothrottle: 平均 3)、通信コストの比率が小さい可能性。結果を OB・SS に一般化しすぎない』。「HR では Reserve の比率を上げた先例が無いのでは」への答え = 5 本の本文では見つからなかった (範囲: この 5 本のみ。DSB の wrk2 スクリプトの確認は未実施)。
- [ ] **配合を振る根拠**: Autothrottle は配合を一定にして扱うと明記 (`wang2024autothrottle`、既存の §9.17 と同じ引用)。5 本の中に HR の配合を振った論文は見つからなかった (範囲: この 5 本のみ)。
  **(2026-11-12 訂正・追記)**: 5 本の外では **Nodens (ATC '23) が HR の 5 種の問い合わせ型の比率を振っている** (§13.9、§9.19)。上の文は『この 5 本の中には』の意味でのみ正しい。

### 9.19 HR を水平スケール (HPA) の評価に使った先行例 (Related Work・限界、2026-11-12 追加。詳細は §13.9)

- [ ] **Related Work (先行例の整理)**: 『HR を評価に使う資源管理の研究は、主にサービスごとの CPU 量 (垂直) を制御する (FIRM, Sinan, PEMA, Autothrottle, Nodens, SurgeGuard, Reclaimer)。水平 (台数) も扱う StatuScale も、基準に K8s HPA を含まず、同居による粒度の変化を扱わない』。
  bib: `wen2025statuscale` (★arXiv v1 本文)、`shi2023nodens` (★本文)、`ghosh2024surgeguard` (★本文の一部)、`fettes2023reclaimer` (★本文)、`qiu2020firm`、`zhang2021sinan`、`hossen2022`、`wang2024autothrottle` (§9.18 のとおり ★)。**新規 bib の note は『未引用』**。
  限定: 範囲は WebSearch・arXiv API・PDF の grep のみ。『HR で HPA を基準にした水平スケール論文は無い』とは書かない。『確認できた範囲では見つからなかった』と書く。
- [ ] **Related Work (要確認・引用しない)**: `luo2023erms` (Erms。HR を使い、コンテナ数を決める。**本文未読**＝README と Crossref のみ) と `alghadban2026driftguard` (HR を K8s で動かす。**abstract のみ**) は、**本文を読むまで『衝突なし』を主張しない**。引用するなら先に読む。
- [ ] **配合を振る根拠 (§9.18 の続き)**: Nodens は HR の 5 種の問い合わせ型の比率を振っている (1X(2:2:2:2:2) → 1.5X(2:1:2:1:4) など、§3.3)。§9.18 の『HR の配合を振った先例は見つからなかった』は**『5 本の中には』に限定し直す**。ただし Nodens の HR は改変版で、目的は QoS 回復時間。必要台数の比を見る本研究とは目的が違う、と添える (`shi2023nodens`)。
- [ ] **実験環境 / 限界 (HR の選択理由)**: 『DeathStarBench は垂直スケールの評価に使われることが多い』(COLA が評価の節で述べる、`sachidananda2022cola` ★本文、確認 2026-11-12)。COLA が DSB を避けた理由は VM 台数の固定と起動スクリプトで、**クラスタオートスケーラ (VM 台数) の評価の話**。単一ノードで Pod 数を増減する本研究には当てはまらないので、査読で『DSB は水平に向かない』と突かれたら、COLA の理由が VM 台数にある点を答える。
- [ ] **TODO (HR を採る場合の方法節)**: HR のレプリカ増減で (i) consul の登録が Pod の増減に追随するか、(ii) 初期データが重複しないか、(iii) 宛先解決を方法節に書く。根拠候補はフォークの PR (youngmin-kaist/DeathStarBench PR #1) の記述のみで**学術引用にはならず裏取り未了**。実機で確かめてから書く。出所スクリプトはまだ無い。

### 9.20 HPA を扱った論文の評価対象と、本研究のアプリの選び方 (Related Work・実験環境・限界、2026-11-12 追加。詳細・集計表は §13.10)

- [ ] **実験環境 (アプリの選択理由の一文)**: 『確認できた HPA 論文 29 本のうち、OB を使うものが 8 本、SS が 6 本、DeathStarBench Social Network が 5 本、HR が 1 本、Train-Ticket が 3 本。実在の企業システムを評価した論文は無く、全て OSS ベンチマークか自作の合成アプリ』。**『確認できた範囲で』と限定し、母集団の割合として書かない** (標本は WebSearch と arXiv abstract 検索で集めたもので系統的でない。§13.10.7)。
  bib (全て未引用。引用したら note を直す): OB を使う `sachidananda2022cola`・`xie2024pbscaler`・`ahmad2024smarthpa`・`xie2026scalereval`・`li2026autoslo`・`santos2023gymhpa` (★PDF)、SS を使う `dashtbani2025`・`dashtbani2025stalex`・`nunes2024`・`buzato2026ijnc` (★PDF)。
- [ ] **Related Work (HPA の限界の指摘が本研究と同じ向き)**: 『HPA は Deployment ごとに独立に動き、サービス間の依存関係を知らない』(`santos2023gymhpa` の本文、★PDF。imec 公開版)。本研究の出発点 (HPA が Deployment 単位で台数を決める) の傍証。
- [ ] **Related Work／考察 (limits 据え置きの根拠)**: 『limits が尾部レイテンシを悪化させる。autoscaler は limits を外すべき』(`shetty2025cpulimits`、SoCC '25、HR と SN を EC2 で。HPA のしきい値・requests・limits を掃引)。本研究の実測『limits を requests と一緒に縮めるとスロットリングで桁違いに悪化』(scale-third 実験) と同じ向き。**★本文の一部 (§3 を grep) のみ。引用前に通読する。**
- [ ] **限界**: (i) 単一ノード・overlay なしは、確認できた HPA 論文の中で少数 (単一ノード 2 本、複数ノードが大多数)。ノード間通信・overlay (VXLAN)・サービスメッシュを含む構成には一般化できないと書く。(ii) HPA の目標値は先行研究で 60〜150% と幅があり、本研究の 70% が最適とは主張しない (§13.10.4)。
- [ ] **「空白」を書くとき (同居 × HPA)**: 『Pod 内の複数コンテナを変数にして HPA 下の資源効率を測った論文は、確認した 29 本の中に無い。最も近い Buzato & Goldman 2026 は 1 コンテナ内の束ねである』。**検索範囲 = WebSearch (標準 4・extended 3) と arXiv API の abstract 検索 13 本。IEEE Xplore・ACM DL・Google Scholar は未使用**と添える。
- [ ] **訂正**: §9.19 の『HR × HPA の先行例は無い』は、`shetty2025cpulimits` (HR + SN、HPA 土台) の発見で『1 本ある。ただし焦点は limits』に直す (§13.9 の本文にも訂正を追記した)。
- [ ] **査読で突かれうる点**: 「実システムで検証していない」→ 先行研究も全て OSS／合成 (§13.10.4 の 1)。「単一ノードは非現実的」→ 通信経路の差を切り分けるための意図的な条件 (§13.10.4 の 2)。

### 9.21 SS・SN・TT・BI を使う HPA 論文の概要と、Related Work での使い分け (Related Work、2026-11-13 追加。詳細は §13.11)

- [ ] **Related Work (一文)**: 『HPA を基準にした先行研究は、台数・配置・資源量の決め方を改良するもので (予測型・依存関係・ボトルネック特定・制御理論など)、1 Pod 内のコンテナ構成を変数にしたものは確認できた範囲で無い。配合 (リクエスト型の比) を実験の軸にするのは ADASCALE (SN) のみ』。bib: `chen2026adascale` (★本文)、`xie2024pbscaler`・`tang2026morphis`・`baarzi2021showar`・`wang2026sloscaler` (★本文)。全て未引用なので引用時に note を直す。
- [ ] **実験環境 (アプリが 2 つ以上いる理由)**: COLA は同じ手法でも費用削減がアプリで大きく違う (SS 1.34%、OB 33.11%、TT 26.25%、BI 18.01%、表 1。`sachidananda2022cola`、★本文)。結果をアプリごとに分けて書き、差の原因は断定しない。
- [ ] **限界**: 14 本の中でワーカー 1 台は ScalerEval だけ (32 コア、Istio 有り)。ノード間通信を含む構成には一般化できないと書く (§9.20 に同じ)。softirq／リクエストあたり通信 CPU を指標にした論文は 14 本中 0 本 (grep、2026-11-13)。
- [ ] **訂正**: SHOWAR は SN だけでなく TT・OB も評価に使う (結果は SN のみ報告)。§13.10 の集計は OB 9・TT 4。査読で『同居を扱う先行例は』と問われたら 『SHOWAR の affinity は同一ノードへの配置ヒントで Pod 内ではない』と答える。
- 検索の範囲は §13.10.7 のまま (WebSearch と arXiv abstract 検索。IEEE・ACM DL・Scholar は未使用)。

### 9.22 HPA の増設窓・減少窓・同期周期など、HPA の設定の書き方 (方法節・限界・Related Work、2026-11-13 追加。詳細・表は §13.12)

- [ ] **方法節 (実験環境) に必ず書く**: HPA の設定を表にする。『増設窓 (`behavior.scaleUp.stabilizationWindowSeconds`) 30 s、減少窓 (`scaleDown.stabilizationWindowSeconds`) 60 s、目標 70% (ContainerResource でコンテナ別)、台数 1〜12、K8s v1.32』。**K8s の既定は増設 0 s・減少 300 s** (公式 doc の Default behavior、API リファレンス。原文は §13.12.4、★原文確認 2026-11-13)。policies・同期周期 (15 s)・許容幅 (0.1)・metrics-server の解像度を**変えたか／既定か**を 1 行ずつ書く (HPA の policies は既定 = 増設 Percent 100／Pods 4 per 15 s、減少 Percent 100 per 15 s)。**どのマニフェストの値か**を出所に付ける (2026-11-13 主任が確認: OB = `km2/experiments/summer2026/bundle-vs-loss2.sh` 45–46 行の既定 SU_WIN=30／SD_WIN=60 を 379–380 行で `behavior.scaleUp/scaleDown.stabilizationWindowSeconds` に入れる。pdist-k3 のログ `km2/experiments/summer2026/pdistk3sep2.log` の START 行に「様子見=増30s/減60s」。SS = `sockshop/experiments/hpa-pair-ss.sh` 37 行の既定 SU_WIN=30／SD_WIN=60、153–154 行。policies は両方とも書いていない = 既定)。
- [ ] **短くした理由 (方法節)**: 『計測窓 240 s・ウォームアップ 180 s に対し既定の減少窓 300 s では計測窓中に台数が減る応答を観測できないため』 (私の整理。§13.12.3 の 2。**本研究の実験設計から書ける理由**で、先行研究の根拠ではない)。
- [ ] **Related Work／限界**: 『先行研究の大多数は HPA の窓を報告しない (確認できた 27 本中、数値を書いたのは 2 本: MS-RA `nunes2024` の減少窓 < 1〜2 分、NimbusGuard `wanigasooriya2026nimbusguard` の 30 s)。窓の値は台数の増え方に効くため、先行研究との数値比較は設定の違いで割り引く』。引用は ★本文 grep 確認 (2026-11-13)。**増設窓に触れた論文は 0 本**なので、『増設窓を設定した先行例』は書けない。
- [ ] **限界**: 『窓を既定から変えており、窓に対する結果の感度は測っていない』。測るなら窓だけ振る追加実験が要る (提案のみ、実施は未定)。
- [ ] **査読で突かれうる点と答え**: Q『既定から外れているのでは』→ 既定 (300 s) では計測窓中に減少が観測できない、設定は表で全て開示する。Q『先行研究はどうしているか』→ 大多数は窓を書かない (既定と推定)。書いた少数は 1 分前後で同程度 (3 事例)。『多数の先行例が短い窓を使う』とは書かない。
- [ ] **空白を書く場合の限定**: 『HPA の窓を詳しく論じた先行研究』は arXiv／取得済み PDF の grep の範囲の主張。IEEE Xplore・ACM DL・Scholar は直接引いていない。公開コード (yaml) での窓の設定は未確認 (§13.12.5)。
- [ ] **引用前に読むもの**: 増設窓が『過去の推奨の最小を使う』ことは公式 doc の取得版には書かれていない。**K8s のソース (horizontal.go) で確認するまで本文に断定で書かない** (§13.12.4 の注意)。Horn 2022 (`horn2022moha`) と gym-hpa (`santos2023gymhpa`) の本文は未取得 = abstract のみ。
- [ ] **書く前に読み直す (2026-11-13)**: 「窓を数値で書いたのは 27 本中 2 本」は grep 段階の数字。読み直しが要る 19 本の一覧 (bib key・題名・確かめること) は §13.12.6。片付くまで本文に本数を書かない。

### 9.23 Shetty ほか『CPU-Limits kill Performance』(`shetty2025cpulimits`) の使い方 (Related Work・方法節・考察、2026-11-14 追加。本文を通読、図の数値は未読)

- 論文の中身 (原典 arXiv:2510.10747 v1 を通読): 短い主張論文 (position paper)。『遅延に敏感なアプリでは CPU limits を外し、requests だけで管理すべき』。根拠は (i) HR で 19 Pod 中 1 つに limits (使用量の 1×・1.1×) を付けるだけで末尾遅延が 5 倍 (Fig. 3a)、(ii) limits = requests にすると余裕のぶん requests が 25〜45% 増える (SN、Fig. 2c)、(iii) limits > requests かつ HPA しきい値 > 100% だと、詰まったノードでは使用量が requests を超えられず HPA が増やさない『ハング』、(iv) CFS とスケジューラの requests 合計の制約で、requests だけで最低保証は成り立つ (§3.4)。HPA の上に YAAS を作り、HR (SLO 20 ms) で limits を外すだけで CPU −38%、YAAS で −51% (Fig. 4)。KubeCon 等での SRE への聞き取りも含む。 **アプリの分担 (2026-11-14 確認)**: HPA のしきい値を振ったのは **SN** (Fig. 2c = しきい値 (100 − 余裕)%、Fig. 3c = 60/70/90%、負荷 +25%)。**HR** は limits の害 (Fig. 3a) と YAAS の効果 (Fig. 4) で、HR の上で普通の HPA の設定を振った記述は無い。環境は『DSB の HR と SN を EC2 で』の 1 文のみで、ノード数・負荷ツール・マニフェストは書かれていない。[14] の Cilantro の YAML は表 1 で他研究の設定を示す証拠で、自分の配備ではない。
- [ ] **方法節 (枠の設定)**: 『limits は据え置き、requests だけを適正化した』理由の傍証として引用できる (requests が最低保証の仕組みであること、§3.4)。本研究の実測 (limits を requests と一緒に縮めるとスロットリングで p50 が桁で悪化、scale-third 実験) と方向が一致。
- [ ] **考察・限界 (食い違いの可能性に注意)**: 本研究では limits を ×10 に緩めると 300 周/s で取りこぼしが 34→13851 に悪化した (メモリ hpa-throttling-blindspot、`run-expB.sh`・`results-expB-limits.csv`)。Shetty の『limits は外すべき』と単純には合わない。ただし本研究の 300 周/s はノード容量の限界付近で、Shetty が想定する条件と違う可能性がある。引用するなら『requests が最低保証になる点は一致、limits を外す是非はノード容量の限界付近では本研究の実測と異なる』と条件を分けて書く (比較は未検討。書く前に expB の条件を確認)。
- [ ] **HPA の設定の根拠**: 本研究の目標 70% は requests 未満なので、Shetty の『ハング』(しきい値 > requests) の条件には当たらない、と一言書ける。
- [ ] **書誌**: arXiv 版は『Arxiv, Oct 2025』表記。SoCC '25 (pp. 125–133、DOI 10.1145/3772052.3772219) は Crossref で確認済み。公刊版と arXiv 版の同一性は未照合。

### 9.24 Cilantro (`bhardwaj2023cilantro`、OSDI '23) の使い方 (Related Work・3 つ目のアプリ HR の準備、2026-11-14 追加。原典 PDF の概要・§6 実装・§7.2 マイクロサービス実験を読んだ。他の節と図の数値は未読)

- 論文の中身: クラスタの資源を、CPU 利用率のような代わりの指標ではなく、**実際の性能 (P99 遅延など) を見ながらオンライン学習で配る**スケジューラ。事前のプロファイリングは不要で、不確かさを信頼区間で扱う。Kubernetes 用の独立したスケジューラとして Python 7600 行で実装。2 分ごとに配分を見直し、**配分は Deployment のレプリカ数を増減して実行する (水平)**。資源は 1 種類 (CPU の塊) だけ扱える、と限界に書く。
- 評価は 2 つ: (i) 1000 CPU のクラスタを 20 ユーザで共有 (公平性などの 3 つの目的で 9 基準を上回る)、(ii) **HR (19 サービス = MongoDB 6・memcached 3・nginx を含む、consul 経由) に 160 CPU (AWS m5.2xlarge × 20 台) を配り、P99 遅延を最小化**。負荷は wrk2、DeathStarBench 付属の問い合わせ。HR の P99 は均等配分の 0.18 倍、次点の基準の 0.57 倍。
- [ ] **Related Work**: HR を Kubernetes でレプリカ増減させた先例として挙げられる (§13.9 の追記)。HPA は比較相手ではない。同居・Pod 粒度は扱わない (衝突なし、背景)。
- [ ] **3 つ目のアプリを HR にする場合の参考 (論文ではなく実装)**: HR を K8s で動かす YAML と起動スクリプトが公開されている。https://github.com/romilbhardwaj/cilantro/tree/main/experiments/microservices/starters/hotel-res (`hotel-res-core/`・`launch.sh`・`delete.sh`。README は『cilantro-workloads リポジトリのコピー』)。元のリポジトリ https://github.com/romilbhardwaj/cilantro-workloads 。ライセンスは MIT (cilantro 本体の表示)。中身 (宛先の書き方・requests/limits) は未確認。Shetty ほか (§9.23) は表 1 でこの frontend の YAML を『requests を limits と一緒に変えていない』例として引用している。
- [ ] **書誌**: USENIX OSDI '23 の発表ページ https://www.usenix.org/conference/osdi23/presentation/bhardwaj (PDF・Artifacts Available/Functional のバッジあり)。bib に追加済み (未引用)。ページ番号は未確認。

### 9.25 SN に HPA をかけると入口 nginx の増台が効かない (方法節・査読への備え、2026-11-15 追加。本研究の試し 1 回)

- 試し (2026-11-14 21:35–21:53、namespace sn-test、Helm 既定の枠 100m/100m、chart の HPA から処理用 12 サービスだけ CPU 60%・1–5 台、k6 開ループ読み取りのみ 30→300 回/s)。出所: 研究リポジトリの外 `~/ダウンロード/DeathStarBench/rendered/hpa-test/` (`hpa-timeline.csv`・`k6.log`・`LAUNCH.md`)。**索引・解析スクリプトなし (TODO: SN を採用するなら `msa/socialnetwork/` に移して索引化)**。
- 結果: HPA 自体は動いた (nginx-thrift 1→2、user-timeline-service 1→2、負荷停止の約 5 分後に両方 1 へ戻る)。しかし**増えた nginx の 2 台目は CPU 0m のまま** (Prometheus のPod 別 CPU)、1 台目は上限 100m に張り付き。HPA の平均は 50% で 60% を下回り、3 台目以降へ進まない。k6 が最初に張った keep-alive 接続を使い続けるので、新しい Pod に接続が回らない (OB の gRPC 接続固定、メモリ grpc-pinning-imbalance と同じ型)。裏側の user-timeline-service は 2 台に均等に分かれた (nginx が要求ごとに接続を張り直すため、と推定・未確認)。
- 帰結: 到達 105 回/s、取りこぼし 51,936 回 (目標の約 45%)、中央値 1.5 s。
- [ ] **方法節**: SN で HPA を使うなら、負荷側の接続の張り方 (keep-alive を切る、または接続数を十分多くして台数増のあとに張り直す) を書く。公式の wrk2 も接続数 `-c` 固定なので同じ問題が起こりうる → SN+HPA の先行研究 (Shetty ほか §9.23) が入口をどう扱ったかは**原典で未確認**。 → **2026-11-16 に確認: §9.26・§13.13 を参照** (5 本とも接続数・keep-alive は記載なし)。
- [ ] **査読への備え**: 「HPA が効かない」結果が出たとき、接続の固定による見かけの飽和でないことを Pod 別 CPU で示す。
- **公式 wrk2 (mixed-workload.lua、-t 4 -c 100 -R 300、2026-11-15 17:44–17:54) でも同じ**: nginx-thrift 1→2 台、Pod 別 CPU は常に片方だけ 100m・もう片方 0m (17:52 に入れ替わる、原因未確認)、平均 50% で頭打ち。到達 38.6 回/s、p50 遅延 2.21 分。出所 `~/ダウンロード/DeathStarBench/rendered/hpa-wrk2/` (`wrk.out`・`hpa-timeline.csv`・`LAUNCH.md`)。→ 負荷ツールの問題ではなく「入口が少数の長い接続を受ける」構成の問題。**既定の枠 (nginx 100m) では入口が先に詰まり、裏のサービスは 45% 以下で増えない**。
- **案 B (k6 `noConnectionReuse: true`、公式 mixed-workload を k6 に書き写し、300 回/s 10 分、2026-11-16 17:16–17:26)**: 振り分けは直った (nginx 1→5 台 = HPA 上限、5 台全てに仕事、CPU 55–100m、最大÷平均 1.33)。しかし到達 57.1 回/s、取りこぼし 144,391。nginx は全台が絞られ (36–100%)、**HPA の上限 5 台で頭打ち**。nginx の 1 回あたり CPU は約 6.6 ms (前回 wrk2 の約 2.6 ms の約 2.5 倍、推定) = 毎回の接続作りの費用が入口に乗る。出所 `~/ダウンロード/DeathStarBench/rendered/hpa-k6b/` (`k6.log`・`hpa-timeline.csv`・`LAUNCH.md`)。
- [ ] **方法節**: 案 B を使うなら「負荷側は毎回接続を張り直す」と書き、入口の 1 回あたり CPU が増えることを限界に書く。softirq を主指標にするなら、接続作りの分が混ざる点を明記 (測っていない、TODO)。

### 9.26 SN + HPA の先行研究は、対象外・入口・HPA 設定を書いていない (方法節・Related Work・査読への備え、2026-11-16 追加。詳細・出典箇所は §13.13)

- [ ] **方法節 (SN で HPA を回すなら)**: 本研究が (a) HPA を掛けたサービス (処理用 12)、(b) 掛けなかったもの (DB・cache・jaeger・入口を含む場合は入口)、(c) 各サービスの min/max・CPU 目標・requests/limits・初期台数、(d) 負荷側の接続の張り方、を**全て本文か付録の表に書く**。理由: 先行 5 本 (ADASCALE・SHOWAR・SLO-Scaler・ARBITER・Shetty) は、(a)–(d) の大半を書いておらず、再現できない。『書いていない』ことが標準なので、書けば差別化になる。
- [ ] **Related Work**: 『SN に HPA を掛けた先行研究は、HPA の対象サービス、入口の台数、requests/limits、負荷側の接続数を明記しない。例外は ARBITER (入口 nginx-thrift のみ、CPU 50%、max 5–6、`habibi2026arbiter`) と SHOWAR (目標 65%、`baarzi2021showar`)、SLO-Scaler (CPU 60%、`wang2026sloscaler`)』。確認度: 3 本とも **★本文 (全文 grep + 該当節精読、2026-11-16)**。書く範囲は『読んだ範囲の本文では』と限定する (付録・公開コード・図中の値は未確認)。
- [ ] **査読への備え「他の論文は入口をどうした」**: 答え = 『入口にも HPA を掛けて増台した例がある (SHOWAR は K8s 基準が nginx を 16 台に設定、`baarzi2021showar` §5.5 付近 p.438。ARBITER は nginx-thrift が max の 5 台まで増えた、`habibi2026arbiter` §8.1)。しかしいずれも負荷側の接続数・keep-alive を書いていないので、本研究の「接続が 1 台に固定され増台が効かない」(§9.25) と比べられない』。**本研究の接続の固定が先行研究に無い現象だとは言えない** (誰も書いていないだけ)。
- [ ] **査読への備え「DB まで HPA を掛けないのは恣意的では」**: 答え = 先行研究も DB・cache を HPA の対象に含めるかを書いていない (5 本とも記載なし)。本研究は『ステートフルなものは台数を増やすと一貫性・データ分割の問題が出る』ので外した、と**本研究の理由として**書く (先行研究を根拠にしない)。chart 既定の HPA (`global.hpa.enabled`) は DB も含む 27 Deployment を対象にする、という事実は本研究の観察 (§9.25) として書ける。
- [ ] **引用してはいけない言い方**: (1)『先行研究も DB を HPA から除いた』— 記載なし。(2)『Autothrottle は HPA と比べた』— Autothrottle の K8s-CPU は CPU limit を決める**垂直**方式で HPA ではない (`wang2024autothrottle` §5.1・Appendix D/F)。(3) COLA は SN を使っていない (OB・SS・TT など。`sachidananda2022cola`)。
- [ ] **限界** (2026-11-16 更新): 付録・公開コードを確認した結果 (§13.13.1)、SN+HPA の 5 本は**付録なし・公式コードなし** (ARBITER は `github.com/pooyan/arbiter` を示すが 404)。したがって『記載なし』は本文だけでなく付録・コードを探しても出なかった、と書ける (範囲: PDF grep、arXiv abs、GitHub API 検索、WebSearch)。FIRM の GitLab は環境から接続できず未確認。TODO: ARBITER のリンクを後日再確認、FIRM のコードを別のネットワークで確認。
- [ ] **引用してはいけない言い方 (追加)**: Autothrottle のコード (`github.com/microsoft/autothrottle`、d237d7f) は台数固定・DB は 1 台固定配置・入口は専用ノード 1 台・requests なしで、HPA ではない。『先行研究は DB を HPA の対象外にした』の根拠にならない。SN は DSB 本家でなく Sinan のフォーク (28 サービス)。

### 9.27 計測方法が似ている HPA 研究と、方法節・Related Work の書き方 (2026-11-17 追加。詳細・表・検索の記録は §13.14)

- [ ] **方法節 (HPA 実験の手順を「〜と同様に」と書く箇所)**: 3 本まで言える。(a) 『HPA の設定や負荷水準を変え、台数と性能の時系列を比べる』= Nguyen ほか 2020 (`nguyen2020hpa`、★本文確認。同条件 10 回反復、単一物理機に 5 VM、Gatling 開ループ、K8s 1.15)。(b) 『一定レートを段階的に変えて HPA の台数を読む』= COLA (`sachidananda2022cola`、★本文 grep + 該当段落。OB、10 分の一定レート、目標 10〜90%、1 レプリカ = VM 1 台)。(c) 『負荷水準ごとに数回反復し、HPA 下の台数・性能を比べる』= Buzato & Goldman (`buzato2026ijnc`、★本文。SS、3 水準、6 回、Locust 閉ループ)。**『同じ測定窓』『同じ収束時間の定義』とは書けない** (どれも窓・settling time を定義していない)。
- [ ] **方法節 (反復の書き方)**: 本研究の 3〜12 回反復は先行例 (Nguyen 10・Buzato 6・Nilsen 3・Wijaya 5・Henning 3) と同水準と書ける。3 回の理由を書くなら Henning & Hasselbring (`henning2024theodolite`、★本文 grep。『時間と統計の妥協点』、HPA ではなく固定台数) を引ける。**ただし本研究の使い方 (落ち着いた台数が N 回中 M 回同じ、を数える) の先行例は見つからなかった**ので『先行研究は反復を平均・箱ひげ図に使う。本研究は台数の整数値の一致回数を数える』と**違いとして**書く。
- [ ] **方法節 (ウォームアップ + 計測窓)**: HPA 実験で窓を切ることは、査読ありの HPA 論文では明記例を見つけていない。Henning (HPA でない、warm-up 2 分/4 分) と Wijaya (GitHub、k6 時刻 120〜540 s、査読なし、README のみ) が近い。『窓だけで評価する』は**方法の選択**として理由 (HPA の立ち上がりを除く、増やし遅れを別に見る) を本研究側で書く。先行例を根拠にしない。
- [ ] **方法節 (台数の採取間隔)**: 先行研究は台数の採取間隔をほぼ書かない (Nguyen は metrics-server の取得周期 60 s のみ)。本研究が **15 s ごと** (HPA の同期周期 15 s と同じ) と書くことは、先行例より詳しい。**採取間隔 = 同期周期なので、窓内の台数は取りこぼさない**、と書ける (本研究の事実。`sample_hpa.py` の出所を付ける)。
- [ ] **Related Work**: 『HPA の特性評価は、取得周期・指標・目標値 (Nguyen 2020、COLA、STaleX、Shetty)、段階的な負荷 (Nilsen の 250/500/750 rps、COLA)、反復 (Nguyen 10 回、Buzato 6 回) などで行われてきた。本研究は同居の効果を HPA 下で測るために、(i) 一定レートの窓、(ii) 台数の時系列、(iii) 予約量 (requests × 台数)、(iv) 台数の一致回数、で測る』。**(iii)(iv) の先行例は §13.14.4 の範囲 (WebSearch・arXiv abs・既存 29 本) では見つかっていない**と範囲つきで書く。
- [ ] **収束時間 (落ち着くまでの時間) を測るなら**: 定義を自分で書く。近い定義は Podolskiy ほか (`podolskiy2019scalex`、★本文) の autoscaling latency (必要台数 DAI と実台数 CAI が食い違う区間の長さ)、Shetty の『SLO を満たすまでの時間』、Wijaya の time to scale。**台数が帯の内に入って留まるまでの時間 (settling time) を定義した HPA 論文は見つからなかった**。
- [ ] **査読への備え「HPA の特性評価は既にあるのでは」**: 答え = ある (Nguyen 2020 など)。ただし先行例は (1) 古い K8s (v1.15・metrics-server 60 s) か複数ノードのクラウドで、本研究 (K8s v1.32・単一ノード・overlay なし) と数値が比べられない、(2) requests を固定して設定側 (取得周期・目標値) を振る、(3) 同居 (Pod 内の複数コンテナ) を扱わない。本研究は requests と同居の構成を変数にして予約量を見る。
- [ ] **引用してはいけない言い方**: (1)『Nguyen らは一定負荷で定常台数を測った』— 2 段階 (1800→600 req/s) で窓の記載なし。(2)『Casalicchio は HPA を実測した』— **Matlab シミュレーション** (`casalicchio2019perf`)。(3)『Shetty は収束時間を測った』— 本文の記述 (『60% から 70% で SLO 達成までの時間が 4 倍』) は読んだが **Fig. 3c の数値は未読**。(4) Wijaya の GitHub を論文のように引用する (査読の有無不明、README のみ)。(5) Electronics 2024 (`pozdniakova2024slahpa`) の内容を書く (**本文未読**、要約のみ)。(6) Joyce (`joyce2024hpaml`) を特性評価の例に挙げる (査読前、パラメータを振っていない)。
- [ ] **限界**: 先行例の確認は WebSearch・arXiv API の abstract 検索・既存 §13 の PDF による。IEEE Xplore・ACM DL・Google Scholar 未使用。本文を読んだ論文でも、図の数値 (Nguyen の Fig. 3〜8、COLA の Fig. 1、Shetty の Fig. 3c) は未読。
- bib: 新規追加 = `casalicchio2019perf`、`henning2024theodolite`、`podolskiy2019scalex`、`nilsen2023gke`、`wijaya2026hpakeda`、`pozdniakova2024slahpa` (全て「未引用」注記。最後は書誌のみ確認で本文未読)。既存 = `nguyen2020hpa`、`sachidananda2022cola`、`buzato2026ijnc`、`shetty2025cpulimits`、`serracanta2025hpastability`、`dashtbani2025stalex`、`nunes2024`、`joyce2024hpaml`。

### 9.28 「負荷帯ごとの HPA 台数」の先行研究の探し方 (アヌビスの助言、査読への備え、2026-11-17。探索はまだしていない)

- 判定: 「負荷帯ごとに HPA の台数を測る実験に先行例はない」は**掲載不可** (COLA・Buzato・Nilsen が既にある、§13.14)。「一致回数で数える反復・許容幅 10% の整数閾値効果・requests × 台数を主指標」に先行例なしは、今の探索範囲 (WebSearch・arXiv abstract・PDF grep、便宜標本) では**要修正**。許容幅は Kubernetes の KEP / issue で既知の挙動かもしれない (未確認、判定保留)。
- 既存探索の穴: 「HPA」の語を必須にしていた → 同じ問いを別の名前で扱う分野が抜けている (弾力性ベンチマーク (SPEC RG・BUNGEE・Herbst 2013・Ilyushkin)、スケーラビリティ／資源需要ベンチマーク (Henning ESE 2022・Jindal ICPE 2019・Avritzer JSS 2020)、容量計画・待ち行列モデル (Urgaonkar・Gandhi AutoScale)、サーバレスの性能モデル、K8s 以前のしきい値方式、制御理論 (deadband・hysteresis)、メタ安定)。**国内文献ゼロ**、IEEE/ACM/Scholar 未使用、引用の前方追跡なし。書誌はアヌビスの記憶なので全て要確認。
- [ ] **探す手順 (優先順)**: (1) 種 6 本 (Nguyen 2020・Casalicchio 2019・Podolskiy 2019・COLA・Henning・Herbst 2013) から引用を前後 1 周 (Semantic Scholar / OpenAlex API、Wohlin 2014 の手順) (2) dblp で ICPE・SEAMS・SoCC・CCGrid・UCC・CLOUD 等を年で見る (3) IEEE Xplore・ACM DL・Google Scholar の全文検索は**ユーザが大学の認証で** (4) CiNii・J-STAGE・情報処理学会 (5) KEP・GitHub issue (先行例でなく「既知の挙動」の出典として別枠) (6) 学位論文。
- [ ] **判定基準を先に固定**: 目的 (0/1/2)・スケーラ・負荷・台数の測り方・反復の使い道・requests の扱いの 6 軸。衝突 = 目的 2 かつ負荷・台数・反復が同じ、近い = 目的 1 以上かつ 2 軸以上。採否の理由を 1 行ずつ残す (後から基準を動かすと cherry-picking と言われる)。
- [ ] **書き方**: 「先行研究は存在しない」ではなく「調べた範囲 (データベース名・期間・検索日) では〜は見当たらなかった。負荷水準ごとに HPA の台数を測る手順自体は [COLA, Buzato, Nilsen] と同様」。検索式・ヒット数・除外数を表に (PRISMA 風、修士論文なら付録)。
- [ ] **アヌビスの付記**: 主結果は同居の損得なので、**測り方に新規性を主張しない**ほうが安全。方法は先行研究と同型として引用で正当化する。

### 9.29 時間設定と反復回数の根拠 (方法節・査読への備え、アヌビスの判定 2026-11-17)

- 判定: 時間とサイクル数は**自分で決めてよい (条件付き)**。主たる根拠は自分のデータ、先行研究 (反復 3〜10 回: `nguyen2020hpa` 10・`buzato2026ijnc` 6・`henning2024theodolite` 3・`nilsen2023gke` 3) は「同じ水準」の補強として引く。「先行研究と同じ値にした」とは書けない (アプリ・K8s の版・負荷モデルが違う)。Henning の「ウォームアップ 2 分・3 回 = 時間と統計の妥協点」は HPA なしの §3.1 (4 台固定) にだけ引ける。
- 現状の根拠: 増設/削減窓 30/60 s は `km2/experiments/summer2026/bundle-vs-loss2.sh` 43–44 行のコメントに理由あり (実測なし)。ウォームアップ 180 s は `km2/approach/hpa-experiment-method.md` 86 行の「落ち着くのを待つ (3分)」のみ。**計測窓 240 s とサイクル数の根拠はどこにもない**。
- **落ち着くまでの時間** (アヌビスの再計算、`timeline-mix.csv`・`timeline-mix2.csv`、スクリプトは scratchpad の settle.py / settle2.py = 研究リポジトリ外、TODO: 採用するならリポジトリへ): 台数が最後に変わった時刻の 90 パーセンタイル 76〜91 s、95 パーセンタイル 106〜122 s。**ただし分離 (normal) の 40 点中 11 点で計測窓の中に台数が変わった** (`results-mix.csv` 4/20・`results-mix2.csv` 7/20、列 `replicas_at_window_start` と `replicas` の比較。どれかのサービスが変わった点の数で、自分でも再計算して一致。「表 1 に効くサービスに限っても 11」はアヌビスの主張、未確認)。
- [ ] **§3.1 (tex 86 行) に時間を書き足す**: 実設定は 90 s + 120 s、4 台固定 (`km2/experiments/summer2026/fixed4.log` 1 行目、provenance 56 行が「本文未記載」と認めている)。今は §3.2 の 180/240 s が §3.1 にも当てはまると誤読される。
- [ ] **感度分析 (追加実験は不要、calc-coder で)**: 表 1 の n を「窓の終わり」「窓内の最頻値」「窓の 120 s 時点」の 3 通りで出し、「反転 3 組/非反転 3 組」が変わらないか確かめる。変わるなら n の定義を改め §2 の定義も直す。
- [ ] **反復の書き方**: §3.2 の 3→5 サイクルは「3 回で catalogcheckout の判定が反転したため 5 回に統一し表 1 から外した」と正直に書く (結果を見て増やした = optional stopping の説明。結論は弱まる方向なので悪用ではない)。飽和帯 buy 350/400 の 12→6 統一は「450 と同じ走行」と理由を書く (cherry-picking 疑い対策)。「N 回中 0 回」には二項分布の信頼区間を付ける (0/5 の 95% 上限 ≈ 52%)。
- 文言案 (§3.2): 「ウォームアップ 180 秒は、予備走行で台数が最後に変わった時刻の 95 パーセンタイル (約 120 秒) を上回るように定めた。ただし分離配置の 40 点中 11 点では計測窓内でも台数が変化したため、…」(後半は感度分析の結果次第)。

### 9.30 CPU 周波数を基本周波数に固定したこと (方法節・限界・査読への備え、アヌビスの判定 2026-11-17)

- 判定: 「基本周波数に固定した」は方法節の根拠として**通る (要修正)**。ただし「メーカーが全コア持続を保証する値」は言い過ぎ。Intel の定義どおり「Processor Base Power (i7-1260P は 28 W、要確認) が定義される動作点」と書き、本機の PL1 = 40 W (27 s、sysfs の RAPL 値で確認済み) がそれを上回ること、計測窓の中で熱による低下が 0 回だったことを添える。B (全コア 1.5 GHz) は採らない (P と E はマイクロアーキテクチャが違い速さは揃わず、容量だけ落ちる)。C (ターボ範囲で固定) は固定前に全窓で熱低下があったので今の根拠では不可 (判定保留、未測定)。
- **訂正 (Claude の説明の誤り)**: 時刻の表の `freq_ghz` (`km2/experiments/rightsizing/measure-mix-cpu.sh` 191 行、`avg(avg_over_time(node_cpu_scaling_frequency_hertz))`) は 16 スレッドの単純平均で、仕事のないコアの低い読み値 (約 400 MHz) が混ざる。固定中の最大は (8×2.1+8×1.5)/16 = 1.80 GHz。スモークの 1.61→1.79 は「周波数が動いた」でも「P/E の使われ方」でもなく、**忙しいスレッドの割合が変わっただけ**。固定前の「2.1→2.8 GHz」も同じ混ざり物として読む (CPU 時間の −26〜−35% 自体は CSV で再現できる)。なお cpu0–7 は P コア 4 個 × 2 スレッド、cpu8–15 は E コア 8 個。
- 固定の証拠 (スモーク `km2/experiments/rightsizing/smoke/smoke-pinfreq-b25-20261117-times.csv` の 3 窓、Prometheus で再計算、Claude も再実行して一致): package / core の熱低下カウンタの増分 = 0、P コアの窓内最大 = 2.087〜2.101 GHz。対照: 固定前の pdistk3sep2 (`km2/experiments/summer2026/results-pdistk3sep2-times.csv`) は全 48 窓で package の熱低下 27〜1287 回 (b100v200 で 281〜1287)、温度 77〜100 ℃。検算スクリプトは scratchpad の thr.sh / avg.sh (研究リポジトリ外、TODO: 採用するならリポジトリへ)。
- [ ] **ドライバに列を足す** (今は無い): 計測窓ごとの熱低下カウンタの増分 (`increase(node_cpu_package_throttles_total)`・`node_cpu_core_throttles_total`)、P/E 別の動作周波数の窓内最大・最小、パッケージ電力 (RAPL。今の Prometheus に `node_rapl_*` は無い → node_exporter の rapl collector か turbostat の PkgWatt)。`freq_ghz` は名前を変えて参考値に下げる。
- [ ] **毎回の記録**: 実験の開始時に `bash km2/experiments/shared/cpufreq.sh status` の出力をログに残す (再起動で戻るため)。
- [ ] **重い点での確認**: スモークは b25v300 まで。最も重い点 (例 b100v200) × 複数サイクルで熱低下 0 を示してから「全窓で 0」と書く。
- [ ] **固定前後の比は一様でない**: b25v300 で payment 1.42・currency 1.62・email 1.61・frontend 1.82・catalog 1.91・checkout 1.92 倍 (mix-cpu3 の 6 サイクル平均に対するスモーク n=1)、b25 では 0.98〜1.12 倍。1 つの係数で換算できない → 枠と ρ は測り直し必須。FOSE と固定前の結果は「別条件」として切り分けて書き、持ち越せるのは傾向まで (固定後に再現した場合)。
- [ ] スモークの「4 サービスの変化 −6〜+12%」は 1 サイクル、しかも点の順が v300→v150→b25 で時間と閲覧量が重なる → 結果として書かない。3 サイクル以上・順番ランダムで取り直す。
- [ ] **P/E 混在**: 限界に書くだけでは弱い。E コア (cpu8–15) を外す感度試験を 1 点 (容量が半分になる実験条件の変更なのでユーザ判断)。cpuset (static CPU manager) は Guaranteed QoS (requests = limits) が条件で、本研究の「limits 据え置き・requests だけ縮める」と両立しない。
- [ ] **引く資料**: Intel ARK (i7-1260P)、12th Gen Datasheet Vol.1 (Processor Base Power・PL1/PL2/Tau・Turbo)、Linux `Documentation/admin-guide/pm/intel_pstate.rst` (`base_frequency`・`no_turbo`・HWP の min=max)・`cpufreq.rst`、`Documentation/ABI/testing/sysfs-devices-system-cpu` (thermal_throttle)、`turbostat(8)`。§8 から: ターボ無効の先例 `gan2019dsb`・`fried2020caladan`・`ousterhout2019shenango`・`zhu2022meshinsight`・`savasci2024pads` (「基本周波数を選んだ」とまでは書いていない可能性 → 原典で確認し「ターボと周波数変更を無効にする作法に従い、残る値として基本周波数を採った」の順で書く)、記述義務 `hoefler2015benchmarking` Rule 9・`papadopoulos2021principles` P3、`linuxcgroupv2`、P/E `saez2022thread`・`schone2024alderlake`。`maricq2018taming` は結果節未読なので「固定で分散が減る」には使わない。
- **一次資料で確認 (2026-11-17、Claude)**:
  - Intel ARK (i7-1260P の仕様ページ https://www.intel.com/content/www/us/en/products/sku/226254/intel-core-i71260p-processor-18m-cache-up-to-4-70-ghz/specifications.html): Processor Base Power **28 W**、Maximum Turbo Power 64 W、Minimum Assured Power 20 W、P コア最大 4.70 GHz・E コア最大 3.40 GHz を確認。**P/E の基本周波数はこのページに載っていなかった** (取得した本文に無い)。ページは「正式な定義は Datasheet を参照」とする。
  - 12th Generation Intel Core Processors Datasheet, Vol. 1 of 2, Doc. No. 655258, Rev. 011 (May 2025、https://cdrdv2-public.intel.com/655258/655258-011.pdf、scratchpad に取得): §4.1.1 Thermal Considerations の定義「Processor Base Power is the time-averaged power dissipation that the processor is validated to not exceed during manufacturing while executing an Intel-specified high complexity workload at Base Frequency and at the maximum junction temperature as specified in the Datasheet for the SKU segment and configuration.」= **PBP は基本周波数で動かしたときの電力として定義される** (「基本の電力が定義される動作点」は事実と合う。ただし定義に「全コア」の語は無い)。同節「Intel Turbo Boost Technology 2.0 allows processor IA cores to run faster than the base frequency. It is invoked opportunistically and automatically as long as the processor is conforming to its temperature, power, power delivery, and current control limits.」= ターボは機会的。§4.2.1 Table 12 (p.85 付近) の P-Processor Line「4+8 Core 28W」行: Processor IA Core Frequency **P-Core 1.7GHz up to 2.2GHz、E-Core 1.2GHz up to 1.6GHz**、Processor Base Power 28 W (SKU 群の範囲。i7-1260P の 2.1 / 1.5 GHz はこの範囲内)。**i7-1260P 個別の 2.1 / 1.5 GHz の一次資料はまだ無い** (sysfs の base_frequency と二次サイト (例 siliconcat.net) が一致)。
- 文言案 (アヌビス): 「CPU 周波数は、ターボを無効にし (intel_pstate, no_turbo=1)、ガバナと EPP を performance、各コアの下限と上限を基本周波数 (P コア 2.1 GHz、E コア 1.5 GHz) に設定して固定した。基本周波数は Processor Base Power (28 W) が定義される動作点であり、本機の長時間電力上限 (PL1 = 40 W) の範囲にある。固定前の測定では計測窓ごとに熱による周波数低下が 27〜1287 回生じており、cgroup の CPU 時間は周波数を考慮しない [linuxcgroupv2]。計測窓ごとに熱低下カウンタの増分、コアごとの動作周波数、パッケージ電力を記録した。P/E コアの違いは残る交絡として限界に記す。2026-11-17 より前の測定 (FOSE2026 を含む) は非固定の条件であり混ぜない。」(「全窓で 0」は本実験で確かめてから)

### 9.31 周波数固定での ρ の測り直し (mix-cpu4、2026-11-18) — 方法節・結果・査読への備え

- [ ] **方法節 (§3)**: ρ は周波数固定 (§9.30) の状態で測り直した値を使う。測定は mix-cpu3 と同じスクリプト・同じ 17 点 × 1/2 台 × 6 サイクル (出所 `km2/experiments/rightsizing/results-mix-cpu4.csv`、解析 `km2/experiments/rightsizing/analyze_rho2.py` → `km2/experiments/rightsizing/analysis-rho4.txt`、索引 `km2/experiments/summer2026/EXPERIMENTS.md` の mix-cpu4 行)。非固定の mix-cpu2/3 の ρ と混ぜない。
- [ ] **結果として書けそうな点 (アヌビス未点検)**: 固定すると front/catalog/reco の ρ が 0.32〜0.33 に揃い (非固定 0.34〜0.37)、当て直す範囲による ρ の動きが小さくなった (front 1 台: buy≤50 0.33 / buy≥50 0.32、非固定は 0.41 / 0.32)。= 10/19 に見えた「ρ は測る範囲で動く」の一部は周波数の変化によるもの、と書ける可能性。書く前にアヌビスで点検する。
- [ ] **除外の報告**: 取りこぼし 1% 超で 4 点 (1 台 b100v150 ×2、1 台 b50v300 ×2)、絞り 5% 超で 1 台 b100v150 の email ×4 (= この点の email は 6 サイクル全部欠ける)。1 台 b100v150 を全部外した感度: ρ の変化 −0.004〜+0.008 (一時スクリプトで計算、TODO: 出所スクリプトをリポジトリに置く)。
- [ ] **1 周あたり CPU が 1.6〜2.6 倍** (サービス・台数で違う。2026-11-19 アヌビスの再計算で「2.1〜2.6 倍」から訂正) になったので、枠 (requests) は mix-cpu4 から作り直す必要がある (mix-cpu3 由来の `rightsize-pdist-k3-mc3.csv` は非固定)。方法節で「枠も固定後の測定から」と書く。

- **アヌビスの判定 (2026-11-19)「mix-cpu4 の ρ は mix-cpu3 より信頼できるか」→ 条件付きで言える。** 検算スクリプトは scratchpad (thr.py / pe.py / bwf.py / prec.py / sat.py / corr.py / pecorr.py、リポジトリ外) → TODO: 出所スクリプトとしてリポジトリに置く。
  - [ ] [掲載可] 全 204 窓で周波数固定が守られていた: 熱による周波数低下 0 回、P コア最大 2.10〜2.11 / E 1.50〜1.52 GHz (mix-cpu3 は 22/204 窓で低下、P 最大 3.8〜4.56 GHz)。根拠は Prometheus の `node_cpu_package_throttles_total` と `node_cpu_scaling_frequency_hertz` (`freq_ghz` 列は証拠にならない)。測定ログの冒頭に `cpufreq.sh status` が無い → 次回から残す。
  - [ ] [要修正→文言] 範囲依存の縮小 (front 1 台 0.41/0.32 → 0.33/0.32) は「主因は周波数の変動と整合的」と書く。根拠: mix-cpu3 だけを窓ごとの仕事量加重周波数で補正すると 1 台で消える (front 0.316/0.309)・2 台で半分。cart/currency の 1 台には依存が残る (+0.035/+0.022)。飽和点を外しても縮小は残る。
  - [ ] [掲載不可] 「精度が上がった」: サイクル間 SD・ブートストラップ幅は良くなった/悪くなったが混在 (front 1 台 幅 0.006→0.010)。改善したのは直線の当てはまり (RMS 残差/平均 D 5.9〜7.6% → 1.5〜3.3%) と範囲依存。
  - [ ] [掲載不可] 切片 c の変化 (front 261→116 m) を解釈しない (外挿値。非固定では周波数上昇で上に凸 → 切片が水増しされていた)。
  - [ ] [掲載不可] 「CPU 時間の速さの違いを全部除いた」: E コアの分担が負荷とともに 73%→61% (1 台) に動く。P/E 速さ比 1.4〜2 倍の仮定で ρ は最大 −0.012。閲覧が呼ばない checkout +12%・email +11% (b25→b25v300、6 サイクル平均) が残る (原因保留、SMT/コア配置未測定)。限界に書く。
  - [ ] [要修正] 1 台の飽和点: b100v150・b50v300 は 6 サイクルとも p50 0.48〜0.96 s、frontend CPU が約 1.93 コアで頭打ち (絞り 0%)。1% の取りこぼし規則では 2 サイクルずつしか外れない → p50 の基準 (例: 基準点の 5 倍超) を足して再解析し、件数と感度を書く (両方外しても主要 ρ ±0.003、ad +0.010)。
  - [ ] [掲載不可] 「実運用を代表する ρ」と書かない。文言案: 「ρ は CPU 周波数をターボ無しの基本周波数 (P 2.1 / E 1.5 GHz) に固定した条件で測った。非固定では負荷とともに動作周波数が上がり (仕事量加重平均 2.2→3.1 GHz) cgroup の CPU 時間が負荷に対して上に凸になるため ρ が当てはめの範囲で変わった (frontend 1 台 0.41/0.32)。固定後はこの差が 0.01 以内に縮み、非固定の測定を周波数で補正した値 (0.31/0.31) とも整合した。固定は測定の再現性を上げるための条件であり、DVFS が有効な実運用で HPA が観測する CPU 時間の比を直接表すものではない。また P/E 混在の CPU では負荷に応じて E コアの分担が変わる影響が残る。」
  - [ ] 近い組の中の順位は主張しない (catalog−reco は mix-cpu3 1 台で区別でき、mix-cpu4 では区別できない)。近い組と遠い組の分離はどちらの測定でも保たれる。
  - [ ] 任意 (ユーザ判断): 同じ日に固定/非固定を交互に少数点で測る、E コアを外した感度試験。国際会議ならこの 2 つが要る。
- **ユーザ決定 (2026-11-19)**: 1 台の b100v150・b50v300 は、取りこぼし 1% 超で外れたサイクル以外をそのまま ρ の計算に入れる (待ち時間の基準による除外は足さない)。→ [ ] 方法節で「飽和に近い点を含む」ことと、外した場合の感度 (両方外して主要サービス ±0.003・ad +0.010、出所 TODO: 一時スクリプトのみ) を書き添える。
- **ユーザ決定 (2026-11-19)**: ペアを「近い/中くらい/遠い」に分類し直さない。front+currency も含め、ρ の差の値だけで扱う。
- **アヌビスの点検 (2026-11-19、枠の表 mc4)**: 表は再現可・容量スモークに進んでよい。
  - [ ] **方法節・限界 — usage_mc は Prometheus rate() の外挿で低めに出る**: 窓 160 s の端と最後の記録の間が平均間隔の 1.1 倍を超えると延長が半分になり、mix-cpu4 の 2258 行中 256 行 (11%) で 2〜13% 低い (高くなる行は無い)。b50v150・1 台の D1 では catalog −1.1%・cart −0.9%・payment −1.9%・email −2.0% (枠で最大 6m、台数は不変)。ρ の解析 (analysis-rho4) にも同じ一方向の偏りとばらつきの水増しが入る。生カウンタ (-raw.csv) の傾きで出し直す案あり。出所 TODO (一時スクリプト chk2/chk3/chk5.py のみ)。
  - [ ] 方法節: 枠の丸めは Python round() (偶数への丸め)。reco 584.5 → 584。
  - [ ] 容量: 予約見込みは外挿 H (pdistk3sep2 で ±0.15 コア検証) で b75v200 15.3 コア。スモークで Pending 0 を確かめてから本番 (plan-pdist-k3.md 追記 6 末尾)。
- **reco の台数の往復 (2026-11-19、smoke-k3cap / smoke-k3sd45、索引 EXPERIMENTS.md)**: 開始 1 台・b50v300 の分離で、reco が慣らし中 (時に計測窓の中も) 1↔4 台を往復。1 Pod の CPU が約 1.28 コアで頭打ち (limits 1.6 未満、絞り 0) → Ready が落ちる → HPA の利用率の読みが 0〜15% や空欄 → 1 台に減らす。減少窓 45 s でも 3/3 で発生。
  - [ ] 限界・査読への備え: HPA の CPU 初期化期間 (既定 5 分) の扱いとヘルスチェックの失敗が組み合わさると、台数が決まらない。Kubernetes 文書の該当箇所を原典で確かめてから書く (TODO、未読)。
  - [ ] 方法節: 結果 CSV の `replicas_changed_in_window` は窓の始めと終わりの比較だけで、窓の中の往復を見落とす → 時系列から数え直す (出所 TODO)。
  - [ ] 対策の結果 (smoke-k3probe5): reco のヘルスチェック待ち時間 1→5 s で往復 0/3・Ready 落ち 0。本番で採るなら方法節に「reco の readiness/liveness timeoutSeconds=5」と理由 (1 Pod の頭打ちでヘルスチェックが遅れる) を書く。
- **周波数固定で需要モデルの「形のずれ」が約 1/3 に (2026-11-19、ユーザの問い「形のずれは、周波数固定前と比較してどうだった？」)**: 外れを「形のずれ」(配合ごとに 6 サイクル平均した残差、直線の形が合わない分) と「サイクルの揺れ」(繰り返しのばらつき) に分けた。% は b50v150 での D に対する割合、10 サービスの平均。mix-cpu3 (非固定) と mix-cpu4 (固定) は同じコマンド・同じスクリプトで、違いは周波数だけ。
  - 形のずれ: 1 台 6.1% → 2.9% (飽和した b100v150 を抜くと 6.0% → 2.3%)、2 台 6.6% → 1.7%。mix-cpu2 (非固定) も 5.8% / 6.2% で mix-cpu3 と同程度 = 非固定の形のずれは再現する。サイクルの揺れは 3 本とも約 2% で変わらない。
  - 非固定では、合計負荷の大きさに沿った ±10% 前後の系統的なずれ (例: checkout 1 台は b25 で +22%、閲覧だけの配合で −8〜−10%) があり、固定ではほぼ ±3% 以内 (残るのは 1 台の飽和点 b100v150)。
  - 出所: `km2/experiments/rightsizing/plot_fit_mix.py` → `fig-fit-mix-cpu{2,3,4}.html`、`fit_shape_compare.py` → `km2/experiments/rightsizing/analysis-fit-shape.txt`。
  - [ ] 方法節: 周波数を固定する理由に「線形の需要モデル D = c + β·buy + ν·view の当てはまりが良くなる (形のずれ 6% → 2〜3%、揺れは不変)」を足す。図 (直線と点 / ずれの表示) は付録の候補。
  - [ ] 査読への備え: 「非固定 = 実運用の条件なのに、固定で測った ρ を使ってよいか」には、固定で直線モデルの前提が成り立つこと、非固定のずれは周波数変化 (cgroup の CPU 時間は周波数を考慮しない、§8) による系統誤差であることで答える。固定と非固定は同じ日に交互に測っていない (日が違う) ので、日の違いの影響は分けられていない。
- **ユーザ決定 (2026-11-19)**: pdist-k3 本番に frontend+catalog+reco の 3 つ同居 (既存アーム `frontrecocatalog` = FOSE の front3) を足す (`km2/experiments/rightsizing/plan-pdist-k3.md` 追記 6 末尾)。
  - [ ] 方法節: アーム一覧に 3 つ同居を足し、ペア (2 つ同居) と違って Pod 内の線が 3 本 (通信量の約 67%) であること、ρ の差は 3 組の最大で 0.012 (1 台) であることを書く。ペアの結果と同じ軸 (ρ の差) に並べるかは解析時に決める。
- **アヌビスの点検 (2026-11-20、3 回目の本番前)**: 詳細は `km2/experiments/rightsizing/plan-pdist-k3.md` 追記 6 末尾。
  - [ ] 方法節: HPA は既定値 (同期 15 s、許容幅 0.1、CPU 初期化期間 5 分。kube-controller-manager に指定なし) で動かしたと書く。
  - [ ] 方法節: 窓内の台数変化は時系列から数えた (結果 CSV の印は使わない)、得の CPU はサービス別のカウンタから帰属させたと書く。
  - [ ] 限界: 停止猶予が分離 (cart/currency/reco/catalog 5 s) と同居 Pod (30 s) で違う / 同居 Pod の Ready は全コンテナの AND / 分離と同居を別の時間帯に測った (対照を混ぜない場合) / P・E コアの混在。
- **k6 → frontend の負荷が 1 Pod に偏る (2026-11-20、smoke-k3f3、索引 EXPERIMENTS.md)**: k6 は既定で VU ごとに HTTP 接続を使い回す (checkout.js に noConnectionReuse 等の指定なし) ので、ClusterIP の振り分けが接続単位でしか効かず、慣らし初め (開始 1 台) に張った接続が最初の Pod に残る。Prometheus のコンテナ別 CPU で、分離でも同居でも frontend の負荷はほぼ 1 Pod (1.4〜2.0 コア)、残りの Pod はほぼ 0。backend は GRPC_LB で均等。
  - 同居 front3 では、その 1 Pod の reco (1 Pod の頭打ち約 1.28 コア、周波数固定で下がった) が詰まり、b50v300 で p50 1.78 s。HPA は Pod 平均 55% で満足 = **HPA の判断 (平均) と実際の負荷 (1 Pod に集中) のずれ**。台数は使用量の合計で決まるので予約枠はほぼ影響を受けない見込みだが、待ち時間・取りこぼしは影響を受ける。
  - [ ] 方法節: 負荷生成器の接続の扱い (使い回すか、繰り返しごとに張り直すか) を書く。直したなら何を変えたか。
  - [ ] 査読への備え・要調査: 過去の結果 (FOSE §3.1 の固定 4 台「分離は約 360 周/s で頭打ち・CPU が余る」、HPA 実験の frontend の台数) にも同じ偏りが入っていた可能性。k6 の版と設定、当時のコンテナ別 CPU で確かめる (未調査)。
  - 張り直し (k6 noConnectionReuse) の確認 noreuse-chk (2026-11-20): frontend の CPU が基準の配合で +11.8% (購入だけ +15.2%、閲覧だけ +6.7%)、粗い ρ 0.330 → 0.304。他のサービスはほぼ不変。[ ] 方法節: 負荷生成器が要求ごとに接続を張り直すこと、それで frontend の 1 周あたり CPU が約 1 割増えること (= ρ と枠はこの条件で測った値を使う必要があること) を書く。
  - ときどき張り直す (k6 が要求 20 回に 1 回 `Connection: close`、CLOSE_EVERY=20) の確認 (2026-11-20、`km2/experiments/summer2026/smoke/smoke-k3close20-20261120.csv`、`km2/experiments/rightsizing/smoke/close20-chk-20261120.csv`): frontend の Pod 別 CPU が均等 (最大/最小 ≤ 1.08)、frontend の CPU は基準の配合で +0.3%、粗い ρ 0.331 → 0.314。[ ] 方法節: 「ClusterIP は接続単位でしか振り分けないので、負荷生成器は N 要求ごとに接続を閉じて Pod 間に分散させた。この操作で frontend の 1 周あたり CPU は変わらない (+0.3%)」と書く (2026-11-20 ユーザが ③ CLOSE_EVERY=20 の採用を決定)。出所スクリプト: Pod 別 CPU は Prometheus の手打ちクエリ → TODO (スクリプト化)。
  - [ ] 限界/要調査: 周波数固定後、購入ありの点で p99 が 350〜840 ms (固定前の pdistk3sep2 の分離は 13 ms)。張り直しとは無関係 (mix-cpu4 のキープアライブでも出る)。p99 を指標に使うなら原因を調べてから。
  - ときどき張り直すの点検 (2026-11-20、smoke-k3close20 の Pod 別 CPU を 15 秒刻みで Prometheus から): 増えた frontend Pod は約 30 秒で他と同じ負荷になる (b50v300)。(訂正: 「1 Pod が瞬間的に平均の約 1/4 に落ちる」は rate(...[30s]) の見かけで、生カウンタの隣接差では最小/平均 ≥ 0.87 = 現象なし。Pod 別の時系列は生カウンタの差か rate[60s] 以上で見る。) 窓平均は ±4% で均等。整合性: 毎回張り直しの +11.8% ÷ 20 ≈ +0.6% と予想、生カウンタで再計算した実測 +0.3〜1.1%。[ ] 限界: 低負荷の配合での追随の速さ、複数サイクルでの再現は未確認。方式はアプリで 3 種 (OB = CLOSE_EVERY=20、Sock Shop = noVUConnectionReuse = 1 周ごと `sockshop/k6/sockshop.js:56`、SN = noConnectionReuse = 要求ごと) → アプリ間で 1 周あたり CPU・ρ の絶対値は比べず、アプリ内のアーム差だけ使うと方法節に書く。
  - [ ] **mix-cpu5 暫定 (サイクル 1・2、生カウンタ、2026-11-21 アヌビス)**: CLOSE_EVERY=20 で ρ はほぼ不変 (主要 6 サービス |Δρ| ≤ 0.003、1 台の b100v150・b50v300 を全サイクルで外した固定の点の組では front/catalog/reco −0.0006〜−0.0007)。ペア差 1 台 front−catalog +0.0075→+0.0072、front−reco −0.0053→−0.0057。frontend 2 台の Pod 間偏り 1.08→1.01。★新発見: 1 台の b100v150・b50v300 は frontend が約 1930m で頭打ちし、取りこぼし 1% のしきい値をサイクルごとにまたぐため当てはめへの出入りで ρ が揺れる (mc4 の front/catalog/reco の ρ がサイクル番号と相関 +0.85〜+0.94、点の組を固定すると sd 0.0017→0.0005)。ペア差は相殺されほぼ影響なし。★サイクル単位ブートストラップは少数サイクルで区間が狭く出る → t 区間を併記。生カウンタでは mc4 の frontend ρ 区間は ±0.0011 (rate() の値では ±0.005 と約 5 倍)。枠を生カウンタで作り直すと catalog 533→539、cart 234→236、payment 36→37、email 52→53。途中打ち切りを提案された (4 サイクル、偶数で 1 台/2 台の順番が釣り合う、停止規則をサイクル 3 完了前に書く、方法節に打ち切りと規則を決めた時点を開示)。出所: アヌビスのスクリプト (スクラッチパッド anubis5/、未保存) → TODO。
  - [ ] **mix-cpu5 完了 (6 サイクル、2026-11-21、生カウンタ)**: CLOSE_EVERY=20 で ρ はほぼ不変。2 台は front/catalog/reco/currency の |Δρ| ≤ 0.001。1 台は front −0.0040、catalog −0.0025、reco −0.0020、cart −0.0093 (飽和 2 点を外すと front/catalog/reco −0.0010〜−0.0024)。ペア差の符号は全て不変。出所: `km2/experiments/rightsizing/analysis-rho5.txt` (`rho_compare_mc4mc5.py`、入力は `rho_raw_mc4mc5.py` で作り直した CSV)。[ ] 方法節: 張り直しの有無で ρ の差は 1 台で最大 0.004 (cart 0.009) と書く。[ ] 限界: サイクル 3 の 1 台 b75v75 だけ CPU が 2〜5% 高い (平均周波数 1.613 GHz と低い、E コア寄りの配置と推定、証拠は弱い)。[ ] 開示: 途中経過 (サイクル 3) を見た後で打ち切らずに予定どおり 6 サイクル完走したこと。
  - [ ] **枠の表を mix-cpu5 で作り直し (2026-11-21、ユーザ指示)**: `km2/experiments/rightsizing/rightsize-pdist-k3-mc5.csv` (r = D1(b50v150、1 台、6 サイクル平均、生カウンタ) / 1.5)。方法節: 3 回目 (pdistk3sep3/pair3) の枠と ρ は、張り直しあり (CLOSE_EVERY=20)・周波数固定・生カウンタの mix-cpu5 から出したと書く。mc4 の表との差は各サービス ±6m 以内。解析 `analyze_pdist_k3.py` は結果を見る前に 3 回目用へ修正 (3 つ同居の Δρ = メンバー間の差の最大と定義) → 方法節にこの定義を書く。
  - [ ] **容量不足の判定 (2026-11-21 アヌビス点検、自分でもコードで確認)**: timeline の pending_pods は Pod の phase だけを見るので「コンテナ作成中」も数える (`km2/experiments/summer2026/sample_hpa.py:53`)。過去の「Pending 0 件」の主張 (例: 302 点すべて 0) は窓内の値で、この定義の下での話。3 回目からは FailedScheduling のイベントを点ごとに回収 (`bundle-vs-loss2.sh`、`collect_events.py`)。方法節: 容量不足は FailedScheduling で判定したと書く。events-*.csv は 2026-11-21 より前は列が 2 つずれている (限界ではなく解析時の注意)。
  - [ ] **イベントの保持期間 5 分 (2026-11-21 アヌビス点検、自分でも確認)**: MicroK8s の API サーバは `--event-ttl=5m` (`/var/snap/microk8s/current/args/kube-apiserver:16`) で、ドライバは点の終わり (t_run+約 626 s) に 1 回だけイベントを回収 → 残るのは t_rel≳326 s の分だけ。smoke-k3mc5 の events には台数を増やすイベントが 0 件 (timeline では 30 回以上の増加)、WARM180/MEAS240 の pdistk3sep2 では 58 件残っていた = 窓を延ばして消えるようになった。**過去の events-*.csv はウォームアップ前半が欠けている**ので、イベントを根拠にした主張 (FailedScheduling 0 件、増減の回数など) は「保持期間内に限る」と書くか、timeline で裏付ける。2026-11-21 修正: ドライバが計測窓の始まりにもイベントを取り uid で重ねる (pdistk3sep3/pair3 から有効)。方法節: 「HPA と載らない Pod のイベントはウォームアップの始めから回収した」と書けるのは 3 回目から。smoke-k3mc5 の「載らない Pod 0 件」はイベントだけでは t_rel≳326 s の分しか裏付けにならない (timeline の pending_pods>0 は同居 2 点の t_rel=47 に 1 サンプルずつ、次で消えている)。
  - [ ] **pdist-k3 3 回目の結果と容量の頭打ち (2026-11-23)**: 結果節の数値の出所 = `km2/experiments/rightsizing/analysis-pdistk3-3.txt` (`analyze_pdist_k3.py pdistk3pair3 pdistk3sep3`)。ρ が近い 5 組 (Δρ≤0.013) 引きずり 0/75、遠い 5 組 (Δρ≥0.13) 46/75、中間 front+currency 2/15。基準の配合 b50v150 は全組 0。**限界に書く**: front+cart b75v200 の c1 で窓の中 (t_rel 497 s〜終わり、窓の約 1/3) に 5 台目 (1140m) が載らず (FailedScheduling、単一ノード 16 コア)、同居が 4 台で頭打ち → この回の「引きずりなし・損 −230m」は容量のせいで、引きずりの数え落としの可能性。c3 は HPA が 5 台を望んだのが窓の最後のサンプル (590 s) だけで、台数 4 は窓のほぼ全体で本物 (timeline で確認、2026-11-23)。この組×配合は c2 で 4→5→4 と揺れており、cart が 70% 線の境目にいる (分離でも cart 4×3/5×9) (主判定から外した場合も (b) 列で併記)。front+catalog c2 b75v200 の −1449m も窓内で 3→4 に増える途中 (Pending 印) で同様に扱う。
  - [ ] **損の数え方 (方法節、2026-11-17 決定・11/23 記録)**: 台数は計測窓の時間平均 (15 s ごとの current_replicas の平均、小数)、分離は 12 サイクルの平均を基準にし分かれ方と sd を併記、損 = 同居台数 × Σ枠 − Σ(分離台数 × 枠)、内訳のプラス側を「引きずられた側」とする。理論 (HPA は整数台数に切り上げ) との書き分け: 理論は「何台の状態か」、測定は「その状態に何割の時間いたか」。出所: 台数 `km2/experiments/rightsizing/tavg-replicas-pdistk3-3.txt` (`tavg_replicas_pdist_k3.py`)、損 `km2/experiments/rightsizing/analysis-pdistk3-3-tavg.txt` (`loss_tavg_pdist_k3.py`)。増え遅れの回は得に見えるので「落ち着いた」の定義が要る (未決)。
  - [ ] **損の計算の審判 (2026-11-23 アヌビス、要点は自分でも確認)**: 実装は独立再計算と全 55 セルで 0.42m 以内一致、窓 = 予約枠の区間 (165 点)、Σ台数×枠 で reserved_avg_cores を 15m 以内に再構成。**要修正**: (重) 回単位の「44/75」は n の水増し (3 回が同じ整数) → セル単位 (b50v150 は枠を合わせた配合なので除く) 遠い 15/20・近い 0/20、組単位 5/5 対 0/5 で書く。近い組 = {front, catalog, reco} と checkout+shipping、遠い組は全て checkout か cart を含む = Δρ とサービスの交絡 (現データでは反論不能、限界に書く)。(中) current_replicas は Ready でない/Pending の Pod も数える → front+cart b75v200 c1 は ready で数えると 4.32→4.00 台、損 +290→+151m。載らない Pod の分は別項目に。(中) front+catalog b75v200 c2 は増え遅れでなく許容幅内 (74〜77%) で 3 台安定。front+cart は窓内で往復 = 300 s の慣らしで定常にならない点がある。(中) 損は引きずり (プラス内訳) と同居の得 (マイナス内訳) の正味 → 引きずりを主張するならプラス側だけで集計。(中) 分離と同居を別時間帯に回した交絡。(軽) サンプル間隔は 15/16 s 混在、直前値保持の重み付けでも損の変化は最大 18m。近い組どうしの Δρ の順位 (0.005/0.006/0.007) は ρ の区間より小さく区別不能。修論・研究会なら修正後に可、査読付きは重の交絡が通らない。
  - [ ] **引きずりの判定は最頻値で (2026-11-23 ユーザ決定)**: 「引きずりが起きたか」は窓内台数の最頻値 (同居) と分離 12 回の最頻値の比較で数える (`km2/experiments/rightsizing/analysis-pdistk3-3.txt` §2「主」列・§4、`analyze_pdist_k3.py`)。台数が揺れた回 (分離の回ごとのブレ、窓内の変化) は印を付けて「議論の余地あり」として扱い、印のない回だけの数 (§4 (c)) を併記する。損の大きさは時間平均 (上の項) で別に出す。検討して採らなかった案 (アヌビス 11/23): 時間平均からの引きずり量・HPA 許容幅を物差しにした時間割合・需要比の開き R。R (Δρ との順位相関 0.98) は「ρ が再現した」ことの補助に使える。交絡の限界: 遠い組はすべて購入専用の冷たいサービス (checkout) か cart を含む。checkout 固有説は front+shipping (Δρ 0.315) で切り分け可 (未実施)。
  - [ ] **最頻値の判定の審判 (2026-11-23 アヌビス、一部自分で確認)**: `analyze_pdist_k3.py` の主判定は独立再計算で 165 観測すべて一致、同数の規則が効いたセル 0、Δρ・affinity (TRAFFIC = `km2/experiments/edge-traffic/results-edge-pairs.csv` の「購入100_閲覧0」、`edge_pair_shares.py`、3 つ同居 62.0 = 3 本の和) も一致。要修正: (1) 独立な単位は配合 (55 セル中 49 セルで 3 回同じ) → 「引きずった配合数/5 (3 回中の再現数)」で書く。近い 0/25 セル・遠い 17/30 セル。(2) 主張は「ρ が近い組は分離の必要台数が全配合で一致し、同居してもそれを超えない」。b50v150 は全サービス 3 台で識別に使えないと注記。(3) Δρ の単調性は言えない (checkout+cart 12/15 > catalog+checkout 9/15)。(4) ブレ印の定義を明文化 (分離の窓内変化 = b50v300 cart c7/c10 を含めるか未決。含めると front+cart・checkout+cart の印なしは 6/9)。§2 の「ブレ印」と「窓内変化」は重なる (front+cart は 3+2 でなく和集合 3)。(5) affinity の条件を方法節に: 2026-09-08、分離 1 台固定・HPA なし・購入 100 周/s・180 s・1 回、ヘッダ = 66 B/セグメントの推定 (デバイス層の Pod 合計と 1〜4% 一致)、分母に cart↔redis を含む。閲覧 200 だと checkout の辺は 0 だが「affinity では選べない」は不変。(6) §2 の「損平均」(最頻値版) は論文に使わない。査読への備え: ρ と枠が同じ mc5 から作られている循環の疑い → 別配合での事前登録が反論になる。
  - [ ] **affinity の測り直し (2026-11-23、ユーザ指示)**: ρ (mix-cpu5) と同じ条件 (分離 1 台固定・limits 上書き・GRPC_LB=1・CLOSE_EVERY=20・k6 v2.4.0・周波数固定) で購入 50 + 閲覧 50 周/s、180 s × 1 回。出所 `km2/experiments/edge-traffic/results-edge-pairs-mc5.csv` → `edge_pair_shares.py` → `km2/experiments/edge-traffic/shares-edge-pairs-mc5.txt`。9/08 (購入 100 のみ) との差は各組 0.6 pt 以内、ただし front+catalog 38.8→41.7・3 つ同居 62.0→65.2、checkout を含む組は 0.4〜0.6 pt 下がる。順位はほぼ不変 → 方法節で pdist-k3 の表に使う affinity をこの値にするなら条件をそのまま書く。b50v50 は pdist-k3 の 5 配合に含まれない (基準 b50v150 とも違う) ことを明記。1 回だけの測定。
  - [ ] **★測り方の誤差 (2026-11-20 アヌビス、自分で再計算して確認)**: measure-mix-cpu.sh:189 の `rate(container_cpu_usage_seconds_total[160s])` は、窓の端から最初/最後のサンプルまでが平均間隔 × 1.1 を超えると補外を半間隔で止めるため、必ず過小に出る。mix-cpu4 で 1612 行中 188 行が 2% 超の過小 (最大 −13.4%、frontend 34 行)。生カウンタ (-raw.csv) の (最後−最初)/(時刻差) で ρ と枠の表 mc4 を作り直すと、1 台の front−reco の差が +0.0065 → −0.0053 に入れ替わる、枠は catalog 533→539 など小幅。方法節: CPU 使用量は生カウンタの差分から出したと書く (作り直したら)。同じ誤差は bundle-vs-loss2 の k6_cpu_sec (increase) にも入る、ノード CPU は未確認。出所スクリプト: アヌビスの検算スクリプト (スクラッチパッド、未保存) → TODO 正式なスクリプト化。
  - [ ] 査読への備え: CLOSE_EVERY=20 の根拠と感度 (偏り・崩壊・予約枠への影響は 20 の 1 条件しか測っていない)。L7 の Ingress が無い構成に限るという限界。k6 のイメージが grafana/k6:latest で版が固定されていない (`km2/experiments/k6/k6-job.yaml:24`) → 2026-11-21 に v2.4.0 の sha256 で固定 (`k6-job.yaml:25`)。方法節に「k6 v2.4.0 (イメージの sha256 を固定)」と書く。mix-cpu5 以前の測定は latest 指定で、版は mix-cpu5 だけ Job の中で確認済み。 **2026-11-21 アヌビス点検 (ノードの containerd の画像一覧で自分でも確認)**: 固定した digest は mix-cpu5 で動いた中身と同じ (latest と同じ index digest、ノードに全層あり → レジストリに届かなくても止まらない)。ノードには k6 の index が 5 種類残っている (e7eeddf1 / 5221b620 / e66db15b / 3e4186ae / 3d8e5c7f、amd64 の作成日 06-30〜11-12) = **mix-cpu5 以前は「版不明」ではなく「期間中に少なくとも 4 回入れ替わった」**。どの測定がどれかは Pod の imageID を記録していないので推定のみ (FOSE ≈ 5221、pdist-k3 やり直し 11/07 ≈ 3e41、mix-cpu4 ≈ 3d8e)。[ ] 方法節: 「k6 v2.4.0 (digest 固定)、ρ・枠 (mix-cpu5) と本番は同じイメージ。それ以前 (FOSE を含む) は latest 指定で期間中に版が更新された」と書き、版をまたぐ比較では負荷側の版の違いを交絡として書く。[ ] 未対応の提案: imagePullPolicy: IfNotPresent の明示、起動前にノードの画像を確認、Job ごとの imageID をログに残す (ドライバは未記録)、Sock Shop の `sockshop/k6/k6-job.yaml:24` は latest のまま。frontend は処理中の要求を待たずに終了する (`src/frontend/main.go:170`) ので、窓の中で台数が減った点の失敗率を別に出す。

## 10. 負荷の配合 (workload mix) と強度を、測定点としてどう決めるか (2026-10-19)

背景 (初学者向けの補足つき): 本研究は各サービスの CPU 使用量 D を **D = c + β·buy + ν·view** という直線で当てはめ、ρ = ν/β を出す。buy・view は『1 秒あたりの周回数』、
β は『購入 1 周あたりの CPU』、ν は『閲覧 1 周あたりの CPU』、c は負荷が無いときの CPU (アイドル)。測定点 (buy, view) をどこに置くかが、ρ の精度と信頼性を決める。
Online Boutique (OB) は buy {0,25,50,75,100} × view {0,75,150,300} から 3 点 (0,0)(75,300)(100,300) を除いた 17 点。
Sock Shop (SS) は 1 周の重さが違い (購入が重く閲覧が軽い)、Node.js の front-end が 1 コアで頭打ちになるので OB と同じ周/秒は流せない。
問い = 『SS の点をどう決めれば論文で説得力があるか』。候補: ①OB と同じ view÷buy 比で全体を縮める (縮め率が自由)、②CPU に占める閲覧の割合をそろえる、③各アプリの容量に対する割合でそろえる。


- [ ] **限界 / 査読への備え (★重要、2026-10-19 アヌビス点検・再計算で確認)**: OB の ρ は**測る範囲 (格子の縮尺) で大きく動く**。1 台、`km2/experiments/rightsizing/results-mix-cpu2.csv` を部分集合で当て直し (CPU 時間 / ×周波数):
  frontend 全点 0.350 / 3/4 (b≤75,v≤150) 0.459 / 半分 (b≤50,v≤150) 0.528 (周波数補正 0.312 / 0.356 / 0.380)、catalog 0.344 / 0.445 / 0.473、reco 0.364 / 0.458 / 0.476、cart 0.176 / 0.184 / 0.164、currency 0.259 / 0.268 / 0.270。
  ブートストラップ区間 (±0.01) は**サイクル間のばらつきだけ**で、範囲の決め方による揺れ (±0.1〜0.2) を含まない。catalog に最も近い相手は全点で front、半分で reco に入れ替わる。front・catalog・reco の 3 つが cart・currency から離れていることは全縮尺で保たれる。
  周波数で補正すると揺れは半分以下 → 原因の大半は DVFS と推測 (§8, §9.1)。**本文で書くこと**: 区間を「サイクル由来」と「設計 (縮尺) 由来」に分けて報告、縮尺感度の表、主張は順位が安定な組に限る。出所: `km2/experiments/rightsizing/analysis-rho-scale.txt` (`analyze_rho_scale.py`)。
  **ユーザ決定 (2026-10-19)**: 表は載せ、「ρ の値そのものより、近いペアか遠いペアかに意味がある」という立て付けにする。根拠 = pdist-k3 の 10 組で、近い組 (Δρ 最大 0.055) と遠い組 (最小 0.069〜0.091) の間に、どの範囲・どちらの補正でも隙間があり、近い/遠いの分類は保たれる。
  **2026-10-20 訂正 (アヌビス点検・自分で analysis-rho-scale.txt 39・43 行目を確認)**: 境目 0.05 を固定すると、CPU 時間の半分範囲で front+catalog (0.055) と front+reco (0.051) が「遠い」に入れ替わる。「1 組も変わらない」は誤り。保たれるのは**順序による分離** (近い 4 組の Δρ の最大 < 遠い 6 組の最小) で、これは重い側・軽い側の削り、間引き、1 点除外、無作為 9 点 300 通り、ブートストラップ 400 回のすべてで成り立った (アヌビスの検算 scratchpad chk.py / bs.py、**正式な出所スクリプトは TODO** = analyze_rho_scale.py へ範囲の取り方を足す)。書くときの文 = 「ρ の推定値は当てはめに使う範囲で動いた (frontend 0.35〜0.53)。しかし 10 組を Δρ で並べると、近い 4 組と遠い 6 組は、範囲の削り方・間引き・1 点除外のいずれでも重ならずに分かれた。境目 0.05 は結果を見た後に決めた値で、範囲によって 2 組が越えるため、主張は固定の境目ではなく Δρ の順序による分離として述べる。」
  追加でできる計算: (a) 範囲の取り方を analyze_rho_scale.py に入れて表にする (b) Δρ の順位と引きずり回数の順位相関 + 順列検定 (10 組で検出力が低いことも明記) (c) 重い点での線形性 (残差、buy×view の項) (d) checkout+shipping (閲覧で呼ばれない組 = 自明な近さ) を除いても残るか。国際会議に出すには (a)(b) と線形性の説明が要る。近い組の中の順位 (front+catalog が最も近い等) は範囲で入れ替わるので主張しない。
- [ ] **環境節 / 限界 (2026-10-20)**: MicroK8s は snap の自動更新が有効 (1.32/stable)。6/1 以降の全データは v1.32.13 (rev 8702) で測定 (`snap list microk8s` で確認)。2026-10-20 にユーザが `sudo snap refresh --hold microk8s` で更新を無期限停止 (`snap list` に held)。12〜1 月に追加測定するときは、比べる相手 (分離) も同じ時期に測り直し、別バッチとして書く (室温・DVFS・版の違いが交絡するため)。
- [ ] **結果節 (OB pdist-k3 の書き方、2026-10-20 アヌビス見通し)**: 主張は「ρ が近い組は配合が変わっても引きずられにくい」という**近い/遠いの二値**に限る。近い (Δρ<0.05、4 組) 2/48 回・遠い (6 組) 42/72 回 (`km2/experiments/rightsizing/analysis-pdistk3.txt` §2、再計算で一致)。
  **セル単位でも書く** (3 サイクルがほぼ同じ台数になるため実質 40 セル): 近い 0/16 セル、遠い 14/24 セル (2/3 回以上)。基準配合 b50v150 は枠の作り方から引きずりが出ないので、除けば遠い 14/18。出所スクリプト: TODO (セル単位の集計を analyze_pdistk3 に足す)。
  しきい値 0.05 は結果を見た後に決めた値 → ~~「0.02〜0.09 のどこで切っても分類は同じ」~~ (2026-10-20 訂正: 全点 CPU 時間でも 0.02 では catalog+reco 0.021 が遠いに入る、範囲を変えると成り立たない) → 固定の境目ではなく「Δρ の順序で近い 4 組と遠い 6 組が重ならずに分かれる」と書く (上の訂正を参照)。**「Δρ が大きいほど引きずる」(連続的な主張) は書かない** (遠い組の中で単調でない: 0.09→3/12、0.20→10/12、0.36→6/12)。10 組は独立でない (front が 4 アーム) ので検定はしない。分離と同居は別の時間帯に測った (限界節)。
- [ ] **査読への備え (呼び出しグラフの言い換えではないか)**: 近い組は閲覧経路どうし・購入経路どうし。反論材料 = 両方の経路から呼ばれる currency (Δρ 0.09)・cart (0.17) が引きずりでも中間。決定打は SS の front-end+catalogue (同じ閲覧経路なのに ρ が遠い) が引きずられるか (未測定)。
- [ ] **方法節 (配合の決め方)**: 経緯 = 2026-10-19 アヌビス判定は「限界測定は不要」(ρ はアプリ内で比べる量、容量の定義で値が何倍も変わり設定値 (limits, MAX_VUS) にも依存、割合で決めても縮尺依存は残る)。
  その後 (10/19 夜) 一度「ある程度限界を測る」方針にし、OB の粗い測定を 1 回行った (`km2/experiments/rightsizing/results-limit-coarse.csv`: 購入 200 まで通過・250 は email 絞り 14% で失敗、閲覧 800 まで通過・1000 で取りこぼし 7.4%)。
  **2026-10-20 ユーザ決定: 限界に対する割合で配合を決める話は「なかったことにする」**。論文には書かない。OB の粗い測定データは使わず保管のみ。SS は「どれくらいの負荷に耐えるか」を前回 (b24v120) より強い負荷で素朴に確かめ、その結果で格子を決める。
  **2026-10-20 (同日・再転換) ユーザ決定: 限界 = 計測窓の取りこぼしが 1% を超える手前の段、と定義する。さらに buy と view を 1 つの「負荷」指標にまとめる必要がある**。SS の耐久試験 (b100 / v400 / b40v200 まで取りこぼし ≤1%) では限界に届かなかったので、段を伸ばした追加測定が要る。1 つの指標のまとめ方は未決 (案: 各負荷を「その負荷だけのときの限界」で割って足した和)。
### 10.0 結論

- **衝突 (既出) は無い。** これは新規性の問いではなく『方法の正当化』の調査。読んだ範囲では、**『別のアプリの間で配合や周/秒を数値でそろえる』慣行は見つからなかった**。
  揃えているのは『各アプリの容量 (max load / 飽和点) に対する割合』(PARTIES, SPECpower, Stewart & Shen, BUNGEE) か、そもそも揃えない (TeaStore の Eismann らは絶対 req/s)。
- 文献の決め方は 6 類型 (§10.1)。**ρ のような『係数を回帰で出す』目的に直接答えるのは類型 D (資源需要推定) と E (実験計画) で、そこでの要点は ①共線性を避ける ②負荷水準を複数 ③飽和の手前で測る**。
- **推奨 1 (本命)**: 規則をそろえ数値を変える = 『各因子の最大値 = 単独飽和点の X%、かつボトルネックの予測使用率 ≤ u_max の格子点だけ測る』。OB の 17 点も同じ規則で説明できるか確認する (§10.3)。
- **推奨 2 (併用)**: 識別用の格子 (推奨 1) と、検証用の標準ミックス風の点 (TPC-W 風。ATOM が Sock Shop で前例) を分ける。
- 候補①『OB と同じ比で縮める』は、文献の支持が無く縮め率が恣意的。ただし縮め率を『容量の X%』で決めれば推奨 1 の特殊解になる。候補②『CPU に占める閲覧の割合をそろえる』は先例を見つけられず、しかも **ρ を知ってから配合を決める循環** (ν/β を求めるために ν/β を使う) になる (私の考察。文献ではない)。

### 10.1 類型と代表論文

確認度の凡例: ★原典PDFで確認 (2026-10-19) / 要約のみ = abstract・検索要約・孫引き / 書誌のみ = Crossref 等で書誌は確認、本文未読。

| 類型 | 決め方 | 代表 (bib key) | 具体的な決め方 | 確認度 |
|---|---|---|---|---|
| A. 標準ミックス (固定比) | 業界標準の配合をそのまま使う | TPC-W (browsing 95/5・shopping 80/20・ordering 50/50 の 3 種。ordering 側が購入系の割合) | 3 配合 × 利用者数。購入系の割合が 5% / 20% / 50% | 要約のみ (仕様書本体 tpcw-d55.doc は未取得。検索要約と `singh2010mixaware` ★・`gias2019atom` ★ の記述で一致を確認) |
| A | 〃 (Sock Shop で TPC-W 風) | Gias, Casale, Woodside, ATOM, ICDCS 2019 (`gias2019atom`) | Sock Shop の Home/Catalog/Carts = 63/32/5 (browsing)、54/26/20 (shopping)、33/17/50 (ordering)。利用者 1000/2000/3000、思考時間 7 s。『TPC-W で提案された配合に似せた』と本文に明記。検証用の負荷は『軽・普通・重』になるよう配合と利用者数を選んだ | ★ (Imperial Spiral の PDF) |
| A | アプリ付属の固定比 | DeathStarBench socialNetwork の `mixed-workload.lua` (`dsbsocialnet`) | read-home 0.60 / read-user 0.30 / compose 0.10 をコードに固定。**比の根拠は README に無い** | ★ (ソースを curl) |
| A | 学習と試験で比を変える | Sinan, ASPLOS 2021 (`zhang2021sinan`) | 学習 = Compose:ReadHome:ReadUser = 5:80:15、試験 = 10:80:10 / 1:90:9 / 5:70:25 (『SNS の利用シーンを代表する』と主張。出典 [42] は未確認) | ★ (arXiv 2105.13424) |
| A | 利用者型の比 (Sock Shop) | PPTAM 系 `avritzer2020`、`camilli2022` | visitor 40 / buyer 30 / order visitor 30 | §7 ★ (由来の WESSBAS は未読) |
| B. 実トレース・自然な変動 | 実運用トレースの配合変動をそのまま使う | Stewart, Kelly, Zhang, EuroSys 2007 (`stewart2007nonstat`) | 本研究の目的には孫引きのみ: 『実運用の自然な配合の多様性があれば共線性は起きにくい』(`kalbasi2010thesis` ★ の 2.2 節の記述) | 書誌のみ + 孫引き ★ |
| B | 配合の変化を検出して容量を決める | Singh, Sharma, Cecchet, Shenoy, ICAC 2010 (`singh2010mixaware`) | 例: 短い要求 1 ms / 長い要求 90 ms で、100 req/s のまま配合を 90:10 → 10:90 に変えると処理時間が 990 ms/s → 3610 ms/s (約 4 倍) になる (冒頭の Example 1)。**要求率が同じでも配合で必要容量が変わる**。TPC-W の 3 配合で評価 | ★ (UMass 技術報告版) |
| B | 負荷強度のトレースを SUT の扱える範囲に直す | TeaStore / LIMBO (`kistowski2018teastore`、TAAS 2017 10.1145/3019596) | 『実トレースを LIMBO で取り出し、SUT が扱える範囲に収まるよう修正する』(検索要約。TeaStore 論文本体は有料で未読) | 要約のみ |
| C. 容量 (飽和点) に対する割合 | まず飽和を測り、その X% で測る | Stewart & Shen, NSDI 2005 (`stewart2005nsdi`) | 飽和スループット = 『どの入力率でも達成した最高の成功完了率』。応答時間の検証は入力が飽和の **50–90%** (図では 85%)。配合は read-only / 10% / 20% read-write の 3 水準 | ★ |
| C | 〃 | SPECpower_ssj2008 (`specpower2008design`) | **較正段階で最大スループットを測り** (4 分 × 3 回以上、最後の 2 回の平均)、その 100,90,…,10,0% を目標負荷にする | ★ |
| C | 〃 (別アプリの同居) | Chen, Delimitrou, Martínez, PARTIES, ASPLOS 2019 (`chen2019parties`) | 各アプリの max load = 『p99 が急増する点 (knee、最大 RPS の 60–80%) の RPS』。同居実験は**各アプリの負荷をそれぞれの max load の 10–100% (10% 刻み) で全組合せ** (max load の定義 = 3.1 節 Fig.1、全組合せの記述 = Fig.5 付近の本文)。低負荷 30% / 高負荷 90% で代表 | ★ |
| C | 〃 | Lo ほか, Heracles, ISCA 2015 (`lo2015heracles`) | 負荷を『ピーク負荷に対する %』で横軸にする (図)。ピークの定義の詳細は未確認 | ★ (周波数の件で既読。負荷の定義は未精読) |
| C | 較正してから負荷プロファイルを当てる | Bauer, Herbst, Kounev, ICPE 2017 (`bauer2017proactive`)、BUNGEE | 『システム分析』= 負荷強度と必要資源の対応を、SLO を守れる最大負荷の二分探索で作る → 『ベンチマーク較正』で負荷プロファイルをその対応に合わせて作る | ★ |
| C | サービスごとの容量 | Jindal, Podolskiy, Gerndt, ICPE 2019 (`jindal2019msc`) | Microservice Capacity = SLO を破らずに捌ける最大要求率を、サービスごとに隔離して求める | 要約のみ |
| D. 資源需要推定の設計 | 配合・水準・共線性を要因として振る | Spinner, Casale, Brosig, Kounev, Perform. Eval. 2015 (`spinner2015demand`) | 7 手法を 監視窓・負荷クラス数・負荷水準・共線性・モデル不一致で比較。別の検索要約では クラス数 C={1,2,3}、負荷水準 U={20%,50%,80%} (**出典論文は特定できず、本論文のものとは確認できていない**) | 要約のみ |
| D | 回帰の共線性 | Kalbasi ほか, DEC, TSE 2012 (`kalbasi2012dec`) / 修士論文 (`kalbasi2010thesis`) | 共線性 = 『独立なはずの説明変数どうしが相関し、係数が区別できなくなる』。別の配合で予測すると外れる。対処は PCA (表現力が落ちる)・リッジ回帰 (パラメータが試行錯誤)・DEC (回帰を使わない)。**TPC-W 100 ベンチ + 20 配合のうち 14 配合は Web-DB の CPU 空間を広く覆うように、6 配合は共線性の影響を見るために選んだ** | 修士論文 ★ / 論文本体は未読 |
| D | 実トラフィックの共線性 | Pacifici ほか, Perform. Eval. 2008 (`pacifici2008cpu`) | 実トラフィックでは要求種別の到着率が相関し、推定が悪くなると報告 (`kalbasi2010thesis` ★ の孫引きと検索要約) | 要約のみ |
| D | 配合が変わっても回帰が頑健 | Zhang, Cherkasova, Mi, Smirni, Cluster Comput. 2008 (`zhang2008regression`) | TPC-W、配合が時間で変わる負荷でも CPU 需要の回帰が頑健 (TOMACS 論文の関連研究欄より) | 要約のみ |
| D | 基本式 | Spinner ほか LibReDE (スライド) | 利用率の法則 U_i = Σ_c X_{i,c}·D_c を最小二乗で解く。**本研究の D = c + β·buy + ν·view は、この式に切片 c を足したもの** | ★ (SPEC RG のスライド 16 頁) |
| D | 微小サービスは変動が足りない | ATOM (`gias2019atom`) | 『回帰は観測スループットの変動を仮定するが、マイクロサービスでは十分な変動が無いことが多い。Sock Shop の View item では相関が弱く正確に推定できない (Fig.4a)』→ ATOM はサービス時間の観測から推定 | ★ |
| E. 実験計画法 | 要因・水準・格子を設計する | Jain 1991 (`jain1991art`)、チュートリアル資料 ied_tut.pdf | 『実験の目標 = 最少の実験数で最大の情報』。2^k 要因計画は『各因子 2 水準。**影響が一方向 (単調) のときだけ有効**』。『一度に 1 因子ずつ振る設計は非推奨 (交互作用を見落とす)』。『実験数が多すぎるのも誤り → 2 段階に』。第 2 章: 『重要な因子を因子にしない』『代表的でない負荷』が誤り、『因子と水準は少なめに始め、次の段階で広げる』 | 第 2 章の一部とスライドを ★ (複製サイト経由。第 3 章は目次のみ)、第 5 章 (負荷の選び方) と第 17 章本文は未読 |
| E | D 最適計画 | NIST/SEMATECH e-Handbook 5.5.2.1 (`nisthandbook`) | D 最適 = 情報行列 X'X の行列式を最大にして係数の推定のばらつきを最小にする。**『モデル依存』**で、使いどころの 1 つが『**因子設定に実行できない領域がある (制約付きの設計空間)**』。標準の要因計画と違って直交しない | ★ |
| F. 絶対値で固定 | req/s や利用者数をそのまま | Eismann ほか, ICPE 2020 (`eismann2020perftester`) | TeaStore の browse プロファイルだけ。**700 / 800 / 900 req/s の 3 水準 (絶対値)**、慣らし 20 分 + 計測 5 分。配合は振らない | ★ |
| F | ベンチマーク作法 | v. Kistowski ほか, ICPE 2015 (`kistowski2015build`) | 4 頁。relevance・repeatability・fairness・verifiability・usability の基準のみで、**配合や強度の決め方の具体策は無い** (読んだが使えない) | ★ |

### 10.2 読んで分かったこと (要点)

1. **『同じ配合に揃える』より『同じ規則で決める』が普通。** PARTIES は異なるアプリを同居させるとき、各自の max load の割合 (10–100%) で格子を作る。Stewart & Shen も SPECpower も、まず飽和 (最大スループット) を測ってから、その割合で負荷を決める。
   絶対 req/s で揃える例は Eismann らの TeaStore のみで、そこでは 1 アプリ・1 配合の話。
2. **『飽和点』の定義が論文ごとに違う。** Stewart & Shen = 最大の成功完了率、PARTIES = p99 が急増する knee (最大 RPS の 60–80%)、BUNGEE・Jindal = SLO を守れる最大負荷、SPECpower = 全力で回した最大スループット。
   本研究で使うなら**自分の定義を 1 つ決めて書く** (例: 『front-end の CPU が 1 コアの 80% に達する周/秒』)。
3. **共線性は『設計で避ける』のが基本。** 購入と閲覧を**独立に**振る格子は、2 本の説明変数の相関をほぼ 0 にできる。標準ミックス (TPC-W の 3 配合) だけだと、購入:閲覧の比が 3 通りの『原点を通る直線』上に点が載るだけなので、係数 β と ν の区別が弱くなる (これは最小二乗の標準的な性質で、私の整理。本節で一次文献は確認していない)。
   だから標準ミックスは**識別用ではなく検証用**に回す、が筋が通る。
4. **点の置き方の精度への効き方 (最小二乗の教科書事項。一次文献は未確認)**: ν の推定の分散 ≈ σ² / [ Σ(view_i − 平均)² × (1 − r²) ]。r は buy と view の相関。つまり (a) view の振れ幅が大きいほど、(b) r が 0 に近いほど、(c) 雑音 σ が小さいほど ν は精度良く出る。
   **全体を縮めると (a) が小さくなり精度が落ちる**ので、『縮め率が自由』なら『飽和の手前でできるだけ広く』が合理的。これが『容量の X%』を最大点にする理由づけ。
5. **実験計画法の観点では、OB の『重すぎる 2 点を除く』は『制約付き設計空間』の典型。** NIST は『実行できない領域があるとき』を D 最適計画の使いどころに挙げ、Jain の 2^k は『影響が単調なときだけ有効』と明記する → 本研究は『飽和の手前では CPU が配合に対して直線』という仮定の範囲に領域を限る、と書ける。
   なお本研究の記録 (memory) には『加法性は不成立: view を足すと view が呼ばないサービスも +15〜23%』とあるので、**領域を広げすぎない根拠にもなる** (線形性は領域内の検証が要る)。
6. **ATOM (Sock Shop) は、回帰で需要を推定する難しさを Sock Shop で明示**: 『View item はスループットの変動が小さく相関が弱い』。本研究の SS の ρ が『ほぼ 3 値』になること (§9.5) と整合する材料。
7. **Online Boutique / Sock Shop の配合を別々に決めること自体は問題にならない。** ρ は『1 周あたりの CPU の比』というアプリの性質で、モデルが線形なら配合の取り方に依らない。配合は『識別』と『検証』のための道具、という位置づけを方法節の冒頭で言い切るのが一番強い。

### 10.3 推奨案 (本研究の SS の配合の決め方)

**推奨 1 (本命)「規則をそろえ、数値はアプリごと」= 容量割合 + 使用率の上限**

1. 各アプリで、購入だけ・閲覧だけの**単独ランプ**を 1 回ずつ行い、ボトルネック (SS は front-end) の飽和点 b_sat, v_sat を測る。飽和の定義は 1 つ決めて書く (§10.2-2)。
2. 各因子の水準を b_sat, v_sat の割合で置く (例: 0, 25, 50, 75%)。購入・閲覧の水準数は OB に合わせると『同じ形の格子』と言える。
3. 格子のうち、予測ボトルネック使用率 u(b,v) = (c + β·b + ν·v)/容量 が u_max を超える点は測らない。**OB にも同じ規則を当てて、除いた (75,300)(100,300) だけが超えるか確認する**。超えれば『OB の判断は後付けでなく規則の結果』と言える。超えなければ規則か u_max を見直す。
   (β, ν は先に測った 1 点・2 点の粗い値でよい。または 1 回目の格子の結果で 2 回目を決める二段階 = Jain の『2 段階で』に対応。)
4. 設計診断 (§9.8) を付ける。X, u_max を振って ρ が区間内に収まることを示す。

根拠: Stewart & Shen (50–90%)、PARTIES (別アプリは各自の max load の割合)、SPECpower・BUNGEE (較正してから負荷)、Spinner らの負荷水準、NIST (制約付き設計空間)、Jain (2^k は単調な範囲で有効)。
弱点: X と u_max の数値そのものは文献から決まらない (範囲 50–90%)。感度を示す必要がある。

**推奨 2 (併用)「識別用の格子 + 検証用の標準ミックス」**

- 推奨 1 の格子で β, ν を出し、それとは別に標準ミックス風 (TPC-W の購入割合 5 / 20 / 50% を『周の比』に読み替えた 3 点を、各々 容量の 30 / 60 / 80% 程度の強度で) を測り、回帰からの予測 CPU と実測の誤差を報告する。
- 根拠: ATOM (Sock Shop で TPC-W 風の配合)、Singh ら (TPC-W 3 配合で評価)、Sinan (学習と異なる配合で汎化を試験)。
- 注意: TPC-W の比は『ウェブ操作の比』で、1 周に複数リクエストを含む本研究の『周の比』と単位が違う。読み替え方を書くこと。

**推奨しない案**

- 『OB と同じ view÷buy 比で縮める』: 文献の支持なし。縮め率が恣意的。ただし縮め率を容量の X% で決めるなら推奨 1 の中に含まれる (比は結果として出る)。
- 『CPU に占める閲覧の割合をそろえる』: 先例を見つけられなかった (検索範囲内)。ρ を先に知る必要があり循環する (私の考察)。『閲覧の割合』を軸にするなら、配合の定義を『周の比』でなく『CPU 比』に変えることになり、OB 側も測り直しになる。

### 10.4 位置関係の判定

- 衝突: なし (方法の話であり、主張の新規性とは別)。
- 相補/背景: 全件『背景』。`chen2019parties` (別アプリを各自の容量割合で揃える作法)、`stewart2005nsdi`・`specpower2008design`・`bauer2017proactive` (較正→割合)、`kalbasi2010thesis`・`spinner2015demand` (共線性)、`gias2019atom` (Sock Shop の配合と回帰の難しさ)、`jain1991art`・`nisthandbook` (実験計画)。
- 無関係 (混同注意): `kistowski2015build` (How to Build a Benchmark) は題が似ているが**配合の決め方は書いていない**。TeaStore (`kistowski2018teastore`) の『browse/buy プロファイル』は利用者の行動型の名前で、本研究の buy/view の独立到着率とは別物 (配合を連続的に振る設計ではない)。

### 10.5 検索の記録 (2026-10-19、WebSearch + PDF 直接取得 + Crossref で書誌確認)

- 使った検索語 (英語): "Spinner Casale Brosig Kounev Evaluating approaches to resource demand estimation pdf collinearity workload mix" / "TeaStore micro-service reference application benchmarking load profile browse purchase" /
  "Kraft Pacifici Rolia service demand estimation regression multicollinearity request types workload mix design" / "Kalbasi Krishnamurthy Rolia Dawson DEC multicollinearity workload mix" /
  "resource demand estimation regression workload mixes varying transaction mix to avoid multicollinearity" / "Jain Art of Computer Systems Performance Analysis 2^k factorial design levels" /
  "SPECpower_ssj2008 calibration phase maximum throughput target load levels" / "TPC-W browsing mix shopping mix ordering mix 95% 80% 50%" / "design of experiments microservices performance testing factorial design load levels workload mix" /
  "PARTIES … max load percentage of max load" / "Heracles … peak load" / "optimal experimental design D-optimal linear regression two factors extreme points" / "Stewart Kelly Zhang Exploiting nonstationarity" / "MODE: Mix Driven On-line Resource Demand Estimation" /
  "ATOM model-driven autoscaling microservices Sock Shop … workload" / "Sinan … workload mix social network" / "microservices autoscaling request-type aware workload mix API-level resource requirement estimation"。
- 直接取得できた原典: Kalbasi 修士論文 (カナダ国立図書館 PDF)、Singh ほか UMass 技術報告、ATOM (Imperial Spiral の bitstream API 経由)、PARTIES (Delimitrou 研)、Heracles (Stanford)、SPECpower 設計文書、Eismann ICPE'20 (Waterloo 著者サイト)、Bauer ICPE'17 (research.spec.org)、LibReDE スライド (research.spec.org)、Sinan (arXiv)、Jain チュートリアル資料 (wustl.edu、`-k` が必要)、NIST (HTML)。
- 取得できなかった (403・認証・有料): Spinner 2015 (ScienceDirect・CORE・ResearchGate)、TeaStore MASCOTS 2018 (IEEE、Unpaywall で closed)、Kraft 2009 (ACM)、Zhang 2008 (Springer)、Pacifici 2008 (ScienceDirect)、Kalbasi TSE 2012 (IEEE)、Springer の Systems Benchmarking 章 (14, 17)。
- **出なかったもの (空白の根拠)**: ①『2 つのアプリで配合の数値をそろえて比べる』設計の明示的な議論 ②『CPU に占める閲覧の割合で配合を決める』設計 ③Sock Shop で購入・閲覧を独立に連続的に振る設計 (§7 で既出)。いずれも WebSearch と上記 PDF の範囲。Google Scholar / IEEE / ACM DL の横断は未実施。
- 注意: ユーザ依頼文の『Kraft/Rolia の regression-based』は不正確。Crossref の書誌は **Kraft, Pacheco-Sanchez, Casale, Dawson (VALUETOOLS 2009)**。Rolia は Rolia & Vetland (CASCON 1995) と Kalbasi ほか (DEC) の著者。Rolia & Vetland の本文は未取得 (書誌は検索結果のみ、DOI 未確認のため bib には入れていない)。
  MODE (Kalbasi, Krishnamurthy, Rolia, Richter, CNSM 2011) も Wang–Casale–Sutton の参考文献欄でしか確認できず、DOI 未確認のため bib に入れていない。

### 10.6 次に読むべきもの (配合の観点)

1. Spinner ほか 2015 の本文 (図書館経由) — 負荷水準・クラス数・共線性の試験結果。『共線性が大きいと係数がどれだけ外れるか』を引ければ、格子の設計診断 (VIF) の根拠が強くなる。
2. Kalbasi ほか TSE 2012 と MODE (CNSM 2011) — 『配合を設計して需要を推定する』題の論文。本研究に最も近い設計議論がある可能性。
3. Stewart, Kelly, Zhang EuroSys 2007 — 『実運用の配合の変動を利用する』主張の原典 (いまは孫引き)。
4. Jain の第 5 章 (負荷の選び方) と第 16–17 章 — 実書籍で頁を確認し、『単調な範囲でのみ有効』『2 段階で』の引用頁を確定する。
5. TPC-W 仕様書 (tpcw-d55.doc) — 95/5・80/20・50/50 の定義 (購入系とは何を指すか) を原典で確認。


## 11. 異なる型のリクエスト (buy / view) を 1 つの負荷の物差しにまとめる手段、異なるアプリの間で配合・強度を揃える手段 (2026-10-20)

§10 の続き。§10 は『配合の格子をどう置くか (識別・検証・共線性)』の調査、§11 は『2 種類の負荷を **1 本の軸** にまとめられるか、2 つのアプリで **同じ意味の強度** に揃えられるか』の調査。§10 と重複する PARTIES・Stewart & Shen・SPECpower・ATOM・Sinan・Spinner は再調査していない (そちらを参照)。

### 11.0 結論

- **衝突 (既出) は無い。** 方法の正当化の調査であり、新規性の問いではない。
- **「異なる型を 1 つの軸にまとめる」標準的な方法は存在する。それは待ち行列理論の『利用率の法則を型ごとに足す』こと (総提供負荷 = Σ 到着率 × サービス需要)。** 手元の『アプリ全体の CPU 案』は、この標準手法の特殊形 (需要 = 全コンテナの cgroup CPU の和) と言える。したがって、案そのものは文献の裏付けがある (★ Lazowska 1984 第 3 章を本文確認)。
- **ただし、マイクロサービス研究の主流は、1 本にまとめず『強度 (全体の req/s) + 配合 (型ごとの割合)』の 2 成分のまま扱う** (COLA/Erlang、FIRM。★ 原典確認)。しかも強度は CPU 重みなしの素の req/s。『CPU コストで重み付けした負荷』を強度の軸にした論文は、今回の検索範囲では見つからなかった (DeepRest は逆向きの『型ごとの呼び数 → 資源』の推定)。
- **別アプリ間で配合・強度の数値を揃える慣行は、やはり見つからなかった** (§10.0 の結論を再確認)。揃えているのは『各アプリの容量に対する割合』(PARTIES) と『基準機に対する正規化スコア』(SPECweb2005)。
- **『容量に対する割合の和』案 (保留中) は、数学的に誤りではなく、保守側の近似だった** (§11.2、私の導出)。壊れる原因は『限界を実測する』こと (台数で変わる) であり、割合の和という形ではない。限界を実測せず**サービス需要と枠から計算**すれば、台数に依存しない。
- **推奨 = アプリ全体 CPU 案を維持し、(a) 利用率の法則による『総提供負荷』として位置づけ、(b) 律速サービスの予測利用率で上限を縛る (§11.3)。次点 = 買い × 閲覧の 2 次元平面に『実行可能領域』を描いて、1 本にまとめない (§11.3)。**

### 11.1 用語 (初学者向け)

- **サービス需要 D (service demand)**: 1 件の仕事が、ある資源 (CPU) を使う量。単位は『コア・秒 / 周』。本研究の β (購入 1 周の CPU) と ν (閲覧 1 周の CPU) が、サービスごとの D。
- **利用率の法則 (utilization law)**: 資源 k の使用率 U_k = 到着率 λ × サービス需要 D_k。型が複数あるときは、型 c ごとに λ_c × D_{c,k} を計算して **足す**: U_k = Σ_c λ_c · D_{c,k}。(Lazowska 1984 第 3 章に、CPU 使用率を 3 つの型ごとに 27% + 40% + 8% = 75% と足す例がある。★)
- **総提供負荷 (offered load)**: Σ_c λ_c · D_c。『この負荷が来たら全体で何コア分の仕事が発生するか』。Lazowska は D = Σ_k D_k (全資源の需要の和) を定義している (★ 第 3 章)。
- **律速 (bottleneck)**: 使用率が最初に 100% に達する資源。Lazowska 第 5 章: 到着率の上限は 1/D_max (D_max = 最大の需要を持つ資源の需要)。
- **開ループ / 閉ループ**: k6 は『到着率を固定して投入』する開ループ。待ち行列の閉じたモデル (利用者数 N と思考時間) は閉ループで、本研究とは前提が違う。

### 11.2 『割合の和』案 (保留中) の数学的な位置づけ (私の導出。文献ではない)

記号: λ_c = 型 c の到着率 (周/秒)。D_{c,k} = 型 c が資源 k に要求する CPU (コア・秒/周)。C_k = 資源 k の使える CPU (コア)。λ_c^lim = 型 c を**単独**で流したときの限界 = min_k C_k / D_{c,k}。

- 利用率の法則から U_k = Σ_c λ_c D_{c,k} / C_k。
- λ_c^lim の定義から、全ての k で D_{c,k} / C_k ≤ 1 / λ_c^lim。
- よって **U_k ≤ Σ_c λ_c / λ_c^lim** (全ての k)。左辺が 1 以下なら飽和しない → **Σ_c λ_c / λ_c^lim ≤ 1 は『飽和しない』ための十分条件** (保守側の近似。実行可能領域の内側の三角形)。
- 等号が成り立つのは、全ての型が**同じ資源**で律速するとき。OB のように buy は email、view は frontend と**律速が違う**と、割合の和は実際の領域より狭い (buy が限界ちょうどでも、view の余地は 0 ではない)。
- 問題の本質: 『限界』λ_c^lim を**測る**と、台数 (1 台 / 2 台) ごとに値が変わる。しかし C_k は『台数 × 枠』と**計算できる**ので、**D_{c,k} と枠 r_k から λ_c^lim を計算すれば、台数に依存しない形に直せる**。HPA が見る量そのもの (使用率 = 使用量 / 枠) とも一致する。
- なお『サービス k の必要台数 (小数) = U_k / θ』(θ = HPA の目標使用率)。HPA はこれを切り上げて整数台数にする → 論文の『整数台数の閾値効果』の入力そのもの。

### 11.3 推奨と次点

**推奨: 『総提供負荷 (アプリ全体 CPU) を強度、その中の閲覧の割合を配合』として、利用率の法則で位置づけ、律速の予測利用率で上限を縛る**

1. 重み D_{c} (購入 1 周・閲覧 1 周が**アプリ全体で何コア・秒か**) を、**分離構成の基準点で測って固定**し、表にする (Cosmos DB の RU 表や TPC の配合表のように『重みは固定』と宣言する。測る範囲で比が 0.25 ↔ 0.22 動くことは**重みの不確かさ**として併記)。分離で固定する理由 = 従属変数 (softirq・同居の効果) と無関係な物差しにでき、全アームで同じ強度の意味になる (私の考察)。
2. 強度 = Σ_c λ_c D_c (コア)。配合 = ν·view / (β·buy + ν·view) (閲覧の割合、アプリ全体)。OB の b50v100 と SS の b24v120 が約 33–34% で揃う、は『配合を揃えた』と言える。
3. **上限の制約**: 各サービス k の予測使用率 U_k = (c_k + β_k b + ν_k v) / (θ · r_k) (θ = HPA 目標、r_k = 枠)。**どの格子点でも max_k U_k ≤ u_max** を要件にする (これが §10.3 の推奨 1 の『飽和の手前』を、台数に依存しない形に直したもの)。OB の除いた 2 点 (75,300)(100,300) だけがこの上限を超えるか、確認する (§9.8、未確認)。
4. 弱点への答え: (i)『重いサービスに引っ張られる』→ 上限制約 (3) が律速を見るので、軽いサービスの扱いは別。報告は『アプリ全体 CPU』と『律速の使用率』の 2 本を併記。(ii)『softirq を含まない』→ 含めないのが仕様 (ρ・台数の話は cgroup CPU、softirq は従属変数)。含めた版も補助表で。(iii)『DB 等の構成差』→ DB コンテナを入れた版 / 抜いた版の 2 通りで配合を出し、差を示す (Sock Shop の MongoDB・MySQL、OB の redis)。
5. **査読への答え**: 『なぜ CPU 重みか』→ 利用率の法則 (Denning & Buzen 1978、Lazowska 1984) の標準的な総和。『先行研究は req/s では』→ COLA/Erlang/FIRM は強度 (req/s) と配合 (割合) を別成分に持つ。本研究はその強度を CPU 重みにしただけで、枠組みは同じ。
6. 注意 (Lazowska 第 7 章 ★): 型の違いを無視して**単一の平均クラスに潰す**と、資源の変更に対する予測が大きく外れる例が示されている (CPU 5 倍の例で、単一クラス 2.11 に対し多クラス 5.26)。→ 総提供負荷は**座標**としてのみ使い、『台数・遅延の予測』には使わない (予測にはサービス別の β, ν を使う)。

**次点: 買い × 閲覧の 2 次元平面に『実行可能領域』を描く (1 本にまとめない)**

- 各サービス k について U_k = (c_k + β_k b + ν_k v) / C_k ≤ u_max は (b, v) 平面の**半平面**。全サービス分の共通部分が**多角形 (実行可能領域)**。軸を b/b_ref, v/v_ref (基準点で割る) に正規化すれば、2 つのアプリを**同じ [0,1]² の図に重ねて**比べられる。
- 根拠: 開ループなので上の式がそのまま使える (Lazowska 第 3・5 章の枠組み、私の導出)。閉じたモデルでは配合ごとに律速が変わる『飽和セクタ』(Balbo & Serazzi 1996/1997、abstract のみ)、律速の列挙は線形計画 (Anselmi & Cremonesi 2010、★ 序論と 2 章) と整理されている。
- 利点: 『律速が buy と view で違う』(OB は email / frontend) が**図の折れ線**として見える。測定点が領域のどこにあるかを示せる (格子が飽和の手前に収まる説明になる)。弱点: 図が 2 アプリ分で 1 図に収まらない可能性。多角形の境は予測 (測定ではない) と断る必要。台数ごとに領域が広がる (台数をまたぐ比較は『1 台固定』の測定に限る)。

**やらないほうがよい**: (a) 『単独限界を実測して割合の和』(台数で崩れる、§11.2)。(b) Balanced job bounds (閉ループ前提、Lazowska 自身が多クラスの限界は『広くは使われない』と書いている ★)。(c) SPECweb 流の幾何平均 (ハードウェアの比較用のスコアで、負荷の軸ではない)。

### 11.4 手段ごとのカード

確認度の凡例: ★原典で確認 (2026-10-20) / 書誌のみ = Crossref で書誌確認、本文未読 / abstract のみ。

**M1. 利用率の法則を型ごとに足す (総提供負荷)** 【背景。本研究の手法の根拠】
- (1) 中身: 型ごとに『到着率 × 需要』を計算して足すと、資源の使用率になる (§11.1)。これを全資源について足せば『アプリ全体で何コア分の仕事か』。
- (2) 代表: `lazowska1984qsp` (★ 第 3・5・7 章を著者公開 PDF で確認)、`denning1978operational` (書誌のみ。原典、ACM 403 で未読)。
- (3) 利点: 台数に依存しない (需要は 1 件あたり)。型が何種類でも同じ式。弱点: 型の中の変動 (キャッシュ、JIT) は平均に畳み込まれる。測る範囲で需要が動く (OB 0.25 ↔ 0.22)。
- (4) アプリ全体 CPU 案との関係: **同じもの**。論文での位置づけを与える。

**M2. 律速の使用率 max_k U_k / 必要台数 U_k/θ** 【背景。本研究の主張に最も近い物差し】
- (1) 中身: 全資源の使用率のうち最大のもの。1 を超えると飽和。Lazowska 第 5 章の『到着率の上限 = 1/D_max』。
- (2) 代表: `lazowska1984qsp` (★ 第 5 章。単一クラスの限界のみ、多クラスは『存在するが広くは使われない』)。
- (3) 利点: HPA が実際に見る量 (使用率) と同じ。律速が buy と view で違っても、max で自然に扱える。弱点: 『アプリ全体』ではなく『律速の 1 点』を見るので、アプリ間で値の意味が違う (OB は email/frontend、SS は front-end)。
- (4) 比較: アプリ全体 CPU 案を**補う**もの (上限の制約に使う)。単独では『アプリ全体の重さ』を表せない。

**M3. 実行可能領域 (capacity region) / 飽和セクタ** 【次点】
- (1) 中身: 型ごとの到着率を軸にした平面に、飽和しない範囲を描く。開ループでは半平面の共通部分 (多角形)。閉ループでは配合ごとに律速が変わる『飽和セクタ』。
- (2) 代表: `balbo1996common`・`balbo1997multiple` (abstract のみ、閉ループ)、`anselmi2010bottleneck` (★ 序論・2 章。『律速は配合で変わる』『負荷ベクトルの凸包の境界が律速』『線形計画で列挙』)。
- (3) 利点・弱点: §11.3 次点。
- (4) 比較: スカラー 1 本より**誠実**だが、図の説明が要る。

**M4. 基準となる 1 型で数える (business throughput)** 【背景。固定配合が前提】
- (1) 中身: TPC-C は配合を固定 (Payment ≥43%、Order-Status/Delivery/Stock-Level ≥4%) し、**New-Order だけを数えて tpmC** とする。『business throughput』= 他の型の仕事も配合で暗黙に含む (5.4.1)。
- (2) 代表: `tpcc510` (★ 5.2.3, 5.4 を本文確認)。
- (3) 利点: 単純、業界標準。弱点: **配合を振る本研究には使えない** (配合が固定だから 1 型で代表できる)。
- (4) 比較: 『buy の周/秒』を軸にして view を比 v/b で表す現行の流儀は、これに近い。アプリ間で比を揃える根拠にはならない。

**M5. 配合ごとに別々の指標で報告** 【背景。「1 本にしない」前例】
- (1) 中身: TPC-W は WIPS (標準 80/20)、WIPSb (閲覧 95%。フロント律速)、WIPSo (購入 50%。DB 律速。WIPSo は WIPS の 1/3〜1/2) を**別の指標**として出す。配合が変わると律速が変わることを前提にしている。
- (2) 代表: `tpcw2000smith` (★ 6 頁を通読)、`menasce2002tpcw` (書誌のみ)。
- (3) 利点: OB の buy=email / view=frontend と同じ構図が TPC-W にもある、という**前例**。弱点: 数値の比較は配合ごと。
- (4) 比較: 『律速が型で違うから 1 本にまとめるのは危うい』の裏付けに使える。

**M6. 基準機に対する正規化スコア・幾何平均** 【無関係に近い。混同注意】
- (1) 中身: SPECweb2005 の総合スコアは 3 つの副指標 (Banking/Ecommerce/Support) の**幾何平均**を、基準機のスコアで正規化。
- (2) 代表: `specweb2005faq` (★ 原文)。
- (3) 利点: 異種のワークロードを 1 つの数にする前例。弱点: **機械の性能比較**であり、負荷の強度の軸ではない。
- (4) 比較: 使わない。『1 つの数にまとめる前例』としての脚注程度。

**M7. 強度と配合を別成分に持つ負荷表現 (マイクロサービス研究の主流)** 【背景。本研究の立て付けの裏付け】
- (1) 中身: COLA/Erlang は負荷を『全体の毎秒リクエスト数 + エンドポイントごとの確率分布』のベクトルと定義 (Erlang 3.1 節 A Strawman Solution、COLA 同旨)。未知の配合は学習済みの配合との距離で補間。FIRM は強化学習の状態に『到着率』と『リクエスト型の構成比』を別々に入れる。
- (2) 代表: `sachidananda2024erlang` (★ 3.1 節と Workload Selection)、`sachidananda2022cola` (★)、`qiu2020firm` (★ grep、全文精読ではない)。Sinan・ATOM は §10 参照。
- (3) 利点: 本研究の『強度 + 配合』の 2 成分と同型。弱点: 強度は**CPU 重みなしの素の req/s**。1 リクエストの重さが違うアプリ間 (OB と SS) では強度の意味が揃わない → ここを埋めるのが『CPU 重み』。
- (4) 比較: アプリ全体 CPU 案は、この枠組みの強度を CPU 重みにしたもの。先行研究の枠組みに乗るので説得力が上がる。

**M8. 型ごとの呼び数から資源を推定 (学習)** 【背景。逆向き】
- (1) 中身: DeepRest は『API エンドポイントごとのトラフィック』から各コンポーネントの資源使用量を学習で推定。未見の 3 倍の利用者・未見の形でも 90% 超の精度、と abstract にある。
- (2) 代表: `chow2022deeprest` (abstract のみ。本文は有料)。
- (3) 利点: 本研究の c + β·buy + ν·view の高機能版。弱点: 学習ベースで、ρ のような解釈できる係数は出ない。
- (4) 比較: 負荷の物差しの提案ではない。Related Work で『型ごとの呼び数 → 資源』の先行として触れる。

**M9. 異種の操作を 1 つの『通貨』にまとめる実務の前例 (参考)** 【背景。査読論文ではない】
- (1) 中身: Cosmos DB の Request Unit (RU) は CPU・IOPS・メモリを抽象化した単位。1 KB の点読みが 1 RU。書き込みも検索も RU で測る。
- (2) 代表: `cosmosdbru` (★ 原文。公式ドキュメント)。
- (3) 利点: 『基準の 1 型を 1 単位とし、他の型はその重み付き』という作法の実例。弱点: 論文ではない。
- (4) 比較: 『購入 1 周 = 1 単位、閲覧 1 周 = ρ_app 単位』と書けば、アプリ全体 CPU 案をこの作法で説明できる。脚注か考察で一言。

**M10. 総説 (参照用)**: `calzarossa2016workload` (書誌のみ)。負荷の特徴付け (workload characterization) の総説。『強度と配合』という整理の出典候補。Menascé & Almeida の本 (Capacity Planning for Web Services, Prentice Hall, 2001) も検索結果に出たが、**書誌は検索要約のみ・本文未読・bib 未登録**。

### 11.5 位置関係の判定

- 衝突: なし。
- 背景: M1〜M10 の全件。特に `lazowska1984qsp` (総提供負荷の根拠)、`sachidananda2024erlang`・`sachidananda2022cola`・`qiu2020firm` (強度 + 配合の 2 成分)、`tpcw2000smith` (配合ごとに律速が違う前例)。
- 無関係 (混同注意): `zahorjan1982bjb` (Balanced job bounds) は題が『bound』で『限界』に聞こえるが、**閉ループの性能上限**であり、開ループで型を足す話ではない。`specweb2005faq` の幾何平均は負荷の軸ではない。Maguluri らの『capacity region』(クラウドの VM 型の割り当て、INFOCOM 2012) は検索で書誌のみ確認したが、Pod の使用率とは別問題と判断 (本文未読、bib 未登録)。

### 11.6 検索の記録 (2026-10-20、WebSearch + 原典 PDF 直接取得 + Crossref / Unpaywall)

- 使った検索語 (英語): "Lazowska Quantitative System Performance … utilization law multiple classes" / "Balbo Serazzi asymptotic analysis of multiclass closed queueing networks common bottleneck saturation sector" / "DeepRest … API traffic composition resource utilization" /
  "TPC-C tpmC New-Order … minimum mix percentages" / "microservices autoscaling workload composition request types different resource cost request mix CPU per request type weighted load normalized" / "Erms … ASPLOS 2023" / "FIRM … workload generation request types" /
  "multi-class workload capacity region maximum sustainable throughput request mix …" / "autoscaling microservices weighted request rate by CPU cost of each endpoint workload intensity single metric heterogeneous requests Kubernetes" / "Azure Cosmos DB request units normalized cost …" /
  "Menascé Almeida Capacity Planning for Web Services workload characterization …" / "SPECweb2005 overall score composite …" / "TPC-W WIPS … browsing shopping ordering mix metric" / "microservices bottleneck shifts with request mix …"。
- 取得できた原典: Lazowska 第 3・5・7 章 (homes.cs.washington.edu/~lazowska/qsp/Images/Chap_NN.pdf)、Anselmi & Cremonesi プレプリント (polaris.imag.fr)、TPC-C 仕様 5.10 (Brown 大のコピー)、TPC-W 白書 (tpc.org)、SPECweb2005 FAQ、Erlang (著者サイト)、COLA (arXiv)、FIRM (USENIX)、Cosmos DB ドキュメント。
- 取得できなかった: Denning & Buzen 1978、Zahorjan 1982、DeepRest、Erms (全て ACM DL が HTML を返す。Unpaywall で Denning・Zahorjan は OA と出るが、実体は同じ ACM のページで本文は取れなかった)、Balbo & Serazzi (ScienceDirect)。
- **出なかったもの (空白の根拠)**: ①『リクエスト型ごとの CPU コストで重み付けした負荷』を**強度の軸**にしたマイクロサービス論文 ②『別アプリ間で配合・強度を数値で揃える』議論 ③マイクロサービスの『実行可能領域 (買い × 閲覧)』を描いた論文。いずれも WebSearch と上記 PDF の範囲。Google Scholar / IEEE / ACM DL の横断は未実施。
- Erms (ASPLOS'23) は『共有マイクロサービスを複数のオンラインサービスが使う』問題設定だが、**本文は取得できず abstract (検索要約) のみ**。負荷の定義は未確認。PARTIES・Sinan・ATOM・DeathStarBench は §10 で確認済み。

### 11.7 次に読むべきもの (優先順)

1. Lazowska 1984 第 4 章 (入力と出力、`Chap_04.pdf`) と第 12 章 (既存システムのパラメータ化) — 測った CPU から D を出す手順が書いてある。重みを『基準点で測って固定』する根拠に引ける。
2. Denning & Buzen 1978 の本文 (図書館経由) — 利用率の法則の原典。引用頁を確定する。
3. DeepRest (EuroSys'22) の本文 (図書館経由) — 『型ごとの呼び数 → 資源』の最も近い先行。ρ との関係を書くなら必須。
4. Erms (ASPLOS'23) の本文 — 『複数サービスが共有』『負荷の定義』を確認。
5. Balbo & Serazzi 1996/1997 — 『配合ごとに律速が変わる』を原典で引く (図書館経由)。Anselmi & Cremonesi 2010 の 3〜4 章 (本研究は開ループなので、閉ループとの差を書くため)。

---

## 12. Java (JVM) の起動時 CPU と HPA の誤判断 (2026-11-10)

きっかけ: Sock Shop (MicroK8s 単一ノード、HPA 70%、ContainerResource) で、HPA が増やした新しい Java (Spring Boot) Pod が起動後 0〜60 秒に 0.7〜1.4 コア、60〜180 秒に 0.1〜0.4 コア使い、枠が 16〜18m のサービスでは利用率が数千 % になって台数が上限 12 まで暴走した。Go / Node.js の新しい Pod は跳ねない。対策案 = Java のコンテナだけ readinessProbe を 180 s 遅らせる。
用語補足: **JIT** = 実行中に頻出コードを機械語へ変換する JVM の仕組み (最初は CPU を食う)。**クラスロード** = 起動時に大量のクラスを読み込む処理。**warm-up** = これらが落ち着いて定常の速さになるまでの期間。

### 12.0 結論

1. **既出 (学術)**: 本研究と同じ現象 (Sock Shop の carts = Java Spring が起動時に CPU を食い、K8s HPA が負荷と誤認して台数が暴走する) を書いた論文が **1 本ある: Dashtbani & Tahvildari (2025, arXiv:2510.02585, bib: `dashtbani2025`)** ★原典PDFで確認 (2026-11-10)。ただし /login 経路だけ・HPA 50%・仮想マシン 2 台のクラスタで、**主題は『ベンチマークの落とし穴』であり、同居 (co-location) ではない** → 位置関係は**背景 (現象の先行例)**。衝突ではない。
2. 公式ドキュメントに答えがある (§12.2): 『readinessProbe を起動 CPU が落ち着くまで遅らせる』は**公式が推奨している対処**。ただし**「Ready になる前の CPU」しか除けない**。Ready 後の最初の測定窓までしか除外されないので、Ready になった後に続く CPU (特に『リクエストが来て始まる JIT』) は HPA に入る (§12.2 の (c))。
3. 学術論文で『JVM warm-up が HPA を誤らせる』を**主題にした**ものは、検索した範囲 (WebSearch のみ) では Dashtbani 以外に出なかった。他は技術記事 (ベンダ・ブログ) のみ。
4. Sock Shop を使う他のオートスケール研究 (Nunes SEAMS'24, ScalerEval, STaleX) の本文を grep したが、Java warm-up の扱いを書いたものは無かった (§12.3)。

### 12.1 論文カード (学術)

#### 12.1.1 Dashtbani & Tahvildari (2025) — ★原典PDFで確認 (2026-11-10, arXiv PDF を pdftotext で全文確認)
- 書誌: Majid Dashtbani, Ladan Tahvildari (Univ. of Waterloo), "Key Considerations for Auto-Scaling: Lessons from Benchmark Microservices", arXiv:2510.02585 [cs.SE], 2025-10-02。査読済み版の有無は未確認。bib: `dashtbani2025` (既登録)。
- **ベースライン**: 比較実験の対象は『6 種のオートスケーラ (KHPA、制御理論、学習系、ブラックボックス最適化、依存関係考慮)』を、落とし穴を直した前後で比べる形。**同居との比較ではない**。
- **測定環境**: Sock Shop (13 サービス)、Kubernetes、AMD EPYC 7742 ×2 (256 vCPU) / 1 TB のサーバを VM で区切り、制御 1 + ワーカー 2。Locust + WorldCup98 トレース、**/login のみ** (front-end → user → carts)。KHPA の CPU しきい値 50%、最大 20 Pod、requests 100m / limits 300m (Fig. 1)。Istio / overlay の有無は記述なし。
- **指標**: 台数の時系列 (Fig. 1a)、Pod ごとの CPU (Fig. 1b)、平均応答時間 (SLO 150 ms、Fig. 9)。
- **何を書いたか (原文)** §III-A G1: *"the autoscaler triggered scale-out events even when no external workload was present. ... the Carts service, implemented as a Java Spring application, exhibits high CPU usage during JVM startup. KHPA interpreted this temporary spike as load, launching unnecessary replicas. These new replicas also exhibited the same behavior, creating a loop of runaway scaling."* = **本研究の暴走と同じ形**。
  対処の提案: *"heavy startup logic should be encapsulated in an initContainer with separate resource quotas ..."* (だが Table IV では *"We were unable to use initContainers to isolate JVM startup. Instead, we manually modified the Linux cgroup configuration to temporarily allocate more CPU during the boot phase."*)。
  G4: *"we used a readiness probe that marked the pod as ready only after the JVM was fully initialized. This ensured KHPA didn't count the pod until it could serve real traffic."* + 起動遅延つき livenessProbe。G3: Carts は健全性エンドポイントが無く、JAVA_OPTS で有効化した。G2: 複数 Java Pod が同時に起動すると CPU 競合 (Carts を 5 台に制限して対処)。G5: probe の timeout / 初期遅延はインフラ性能に合わせて調整が要る (TrainTicket では厳しい timeout で再起動の無限ループ)。
- **注意 (読み方)**: G4 は『Ready にした後は HPA が数えない』という方針の記述で、**どれだけ遅らせたか (秒数) と、その前後の効果の定量結果は本文に無い** (Fig. 1 は対処前の暴走のみ。対処後の台数の図は無い。pdftotext で確認、図は目視していない)。
- **限界**: 単一実験条件 (/login のみ)、1 回の実験か繰り返しかの記述なし。
- **判定: 背景 (現象の先行例)。** 理由 = 『Java 起動 CPU → HPA が誤認 → 暴走』と『readiness で抑える』を既に示すが、同居・Pod 粒度・softirq は扱わない。本研究の寄与 (同居の効果) とは主張が衝突しない。**ただし『Sock Shop の Java で暴走が起きる』ことを本研究の新発見として書いてはいけない** (既出)。群: C群 (オートスケール、背景)。

#### 12.1.2 Nunes, Nejati, Sabetzadeh, Nakagawa (2024, SEAMS) arXiv:2403.08798 (bib: `nunes2024`) — ★原典PDFで確認 (2026-11-10、起動に関する箇所のみ grep)
- Sock Shop で提案手法 MS-RA と K8s HPA を比較。§2 の箇条書きに *"Optimizing startup time: ... expensive startups potentially impacting autoscaling efficiency"* とあるが一般論で、Java warm-up の対処や測定は無い。判定: 背景 (warm-up の扱いは書いていない)。

#### 12.1.3 その他 Sock Shop 利用論文
- ScalerEval (arXiv:2504.08308) と STaleX (arXiv:2501.18734, §7.2 の #9): pdftotext + grep (warm / jvm / java / cold / startup / JIT / initiali) で warm-up の扱いは出ず (STaleX は『起動時間・初期化遅延が要る』の一般論 2 行のみ)。判定: 無関係 (この論点では)。
- Avritzer 2020 / Camilli 2022 / Rahman 2019 は**この観点では未確認** (本文を warm-up で grep していない)。

#### 12.1.4 Barrett, Bolz-Tereick, Killick, Mount, Tratt (2017) "Virtual Machine Warmup Blows Hot and Cold" — abstract のみ (検索結果の要約)
- OOPSLA 2017 / PACMPL 1(OOPSLA) 52, DOI:10.1145/3133876, arXiv:1602.00602。主張 = 小さな決定的ベンチマークでも多くの VM が定常 (peak) に落ち着かない (traditional な warmup に従うのは (VM, benchmark) の 43.3–56.5%)。
- 位置関係: 背景。『warm-up の長さは一定でなく、落ち着かないこともある』の学術的根拠に使える (本研究の『Java Pod が 3〜8 分たっても古い Pod より CPU が多い』の裏付け候補)。**引用前に本文を読むこと**。bib: `barrett2017warmup`。

### 12.2 Kubernetes 公式ドキュメントの正確な記述 (技術資料。★原文を取得して確認 2026-11-10)

出所: kubernetes/website の `content/en/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale.md` (main、最終更新 2026-08-04 を GitHub API で確認) を raw で取得。公開 URL = https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/ 。実装の裏取り = kubernetes/kubernetes `pkg/controller/podautoscaler/replica_calculator.go` (master、最終コミット 2026-08-31)。**あなたのクラスタの K8s バージョンの doc と一致するかは未確認** (v1.30 以降の ContainerResource を使っているので近いはずだが、版で文言が違う可能性)。

**(a) Algorithm details の原文** (「Ready でない Pod」の扱い):
> "When scaling on CPU, if any pod has yet to become ready (it's still initializing, or possibly is unhealthy) _or_ the most recent metric point for the pod was before it became ready, that pod is set aside as well."
> "Due to technical constraints, the HorizontalPodAutoscaler controller cannot exactly determine the first time a pod becomes ready when determining whether to set aside certain CPU metrics. Instead, it considers a Pod "not yet ready" if it's unready and transitioned to ready within a short, configurable window of time since it started. This value is configured with the `--horizontal-pod-autoscaler-initial-readiness-delay` command line option, and its default is 30 seconds. Once a pod has become ready, it considers any transition to ready to be the first if it occurred within a longer, configurable time since it started. This value is configured with the `--horizontal-pod-autoscaler-cpu-initialization-period` command line option, and its default is 5 minutes."
> "Furthermore, if any not-yet-ready pods were present, and the workload would have scaled up without factoring in missing metrics or not-yet-ready pods, the controller conservatively assumes that the not-yet-ready pods are consuming 0% of the desired metric, further dampening the magnitude of a scale up."
> "Note that the _original_ value for the average utilization is reported back via the HorizontalPodAutoscaler status, without factoring in the not-yet-ready pods or missing metrics, even when the new usage ratio is used."

**(b) 専用節 "Pod readiness and autoscaling metrics" の原文** (この節自体が Java を例に挙げている):
> "`--horizontal-pod-autoscaler-cpu-initialization-period` (default: 5 minutes). This defines the time window after a Pod starts during which its **CPU usage is ignored** unless: The Pod is in a `Ready` state **and** The metric sample was taken entirely during the period it was `Ready`. This command line option helps **exclude misleading high CPU usage** from initializing Pods (for example: Java apps warming up) in HPA scaling decisions."
> "`--horizontal-pod-autoscaler-initial-readiness-delay` (default: 30 seconds). This defines a short delay period after a Pod starts during which the HPA controller treats Pods that are currently `Unready` as still initializing, **even if they have previously transitioned to `Ready` briefly**."
> "You can only set these command line options cluster-wide."
> "Good practice for pod readiness: Configure a `startupProbe` that doesn't pass until the high CPU usage has passed, or Ensure your `readinessProbe` only reports `Ready` **after** the CPU spike subsides, using `initialDelaySeconds`. And ideally also set `--horizontal-pod-autoscaler-cpu-initialization-period` to **cover the startup duration**."

**(c) 実装 (`groupPods`) で確認した動作** — doc の文章より正確:
- CPU のとき、Pod ごとに `unready` を判定。Pod の Ready 条件が無い / startTime が無い → unready。
- `startTime + cpuInitializationPeriod` がまだ未来 (= 起動から 5 分以内) なら: **`condition.Status == False` (Ready でない) または `metric.Timestamp < Ready に変わった時刻 + metric.Window` (Ready 後、測定窓 1 つ分がまだ溜まっていない)** のとき unready 扱い。
- 5 分を過ぎた Pod なら: Ready でなく、かつ『Ready になるべき時刻が起動+30 s 以内』のときだけ unready。
- unready の Pod は `removeMetricsForPods(metrics, unreadyPods)` で平均から**除かれる**。ただしスケールアップ側 (usageRatio > 1) で unready Pod があるときだけ、**その Pod を 0% として平均に戻して**再計算し、方向が反転するか許容幅内なら何もしない (= 台数を抑える)。
- この関数は ContainerResource でも同じ (`GetResourceReplicas(..., container string)` の中で呼ばれ、unready 判定は Pod 全体の Ready 条件 = 全コンテナの AND)。

**判定: あなたの理解『readinessProbe を遅らせれば起動時の CPU は HPA に入らない』は、基本的に正しい。公式も推奨している。ただし 4 つの条件がある。**
1. 除かれるのは『**Ready になる前**の CPU と、Ready 後の最初の測定窓 1 つ分』だけ。Ready になった後の CPU は (起動から 5 分以内でも) 入る。★既定の 5 分 (`cpu-initialization-period`) は『起動後 5 分間は無視する』ではない。Ready に変わった後、窓 1 つ分が溜まれば数えられる。今回 0〜60 秒の跳ねが HPA に入ったのは、Ready が 10〜40 秒で来たから。
2. 180 s 遅らせて除けるのは『Ready 前の CPU』のみ。**Ready になった後に出る CPU (特にリクエストが来て始まる JIT / キャッシュの暖機) は除けない**。今回の 0〜60 秒の跳ねのうち、起動処理 (クラスロード・Spring の初期化) は Ready 前で消えるが、トラフィック駆動の JIT は Ready (= 180 s 後) にずれて HPA に入る可能性がある。**これは私 (Claude) の推測で、実測で確かめるべき**: 遅延 readiness にしたときの Ready 直後 0〜120 秒の CPU を見る (§9.16 の TODO)。公式の文言も『spike が収まった後に Ready にせよ』であって『起動後の時間で除く』ではない。
3. 遅らせた分、新しい Pod は 180 s 間リクエストを受けない (Service のエンドポイントは Ready の Pod だけ) → 容量が届くのが遅れる。unready を 0% として扱う規則が台数を抑えるので暴走は止まりやすいが、本当に負荷が増えたときの追従は遅れる。
4. `--horizontal-pod-autoscaler-*` はクラスタ全体の設定で Deployment ごとには変えられない (公式)。MicroK8s での設定方法 (kube-controller-manager の引数ファイル) は**未確認**。ここを変えると全アプリに効く。同居 Pod では 1 つのコンテナの遅い readiness が Pod 全体の Ready を遅らせ、他のコンテナの CPU も判断から外れる (論文の論点『同居は Ready が AND』と同じ)。

### 12.3 JVM warm-up の対策の一覧 (簡潔。技術資料は全て『技術資料』と区別)

| 対策 | 何をするか | 確認度 | 出所の種別 |
|---|---|---|---|
| readinessProbe の initialDelaySeconds | spike が収まるまで Ready にしない → HPA が数えない | K8s doc ★原文確認。Dashtbani G4 ★ | 公式 + 学術 |
| startupProbe | 遅い起動のために liveness / readiness を起動成功まで止める。doc は HPA 用に『startupProbe が spike 収束まで通らないようにせよ』とも書く (§12.2 (b))。注: startupProbe が通るまで readiness も走らない | K8s doc ★原文確認 (probes: *"Protect slow starting containers with startup probes"*) | 公式 |
| HPA 側の設定 (cpu-initialization-period を起動時間に合わせる) | 起動直後のサンプルを除く期間を延ばす (ただし §12.2 の 1 の通り Ready 後は効かない) | K8s doc ★ | 公式 |
| 起動時だけ CPU を厚くする | GKE CPU startup boost (VPA + in-place resize。Ready 後に requests を戻す)。Dashtbani は cgroup を手で触って起動時だけ CPU を増やした | GKE ブログ ★原文確認 (2026-10-03 付、HPA と併用するなら *"ensure a robust readinessProbe is defined and keep durationSeconds short"*)。Dashtbani Table IV ★ | ベンダ + 学術 |
| 起動処理を initContainer に分離 | メインコンテナの指標を定常だけにする | Dashtbani G1 ★ (ただし著者らも Sock Shop では実現できなかった) | 学術 |
| 台数の上限・レート制限 | Java Pod の同時起動を抑える (Dashtbani は carts を 5 台に制限) / namespace の quota | Dashtbani G2, G10 ★ | 学術 |
| CRaC (Coordinated Restore at Checkpoint) | 暖まった JVM のスナップショットから再開 | Spring Framework doc ★原文確認: *"allow implementing systems capable of reducing the startup and warmup times of Spring-based Java applications with the JVM"*。Linux のみ、CRaC 対応 JVM が必要、自動チェックポイントは *"does not allow to have a fully warmed-up JVM"* | 公式 doc |
| AOT キャッシュ (JDK 24 の JEP 483 クラスロード・リンク、JDK 25 の JEP 515 メソッドのプロファイル) | 前回の実行のクラス・プロファイルを起動時に使う | JEP 515 ★原文確認 (openjdk.org、*"Improve warmup time by making method-execution profiles from a previous run ... instantly available"*)。JEP 483 は Summary の冒頭のみ | 公式 (OpenJDK) |
| GraalVM native image | Java を事前コンパイルして JIT を無くす | GraalVM 公式 ★ (*"Native Image is a technology to compile Java code ahead-of-time to a binary"*、*"Starts in milliseconds"*、closed world とリフレクションの制限) | 公式 |
| JIT 設定 (`-XX:TieredStopAtLevel=1` など) | C2 コンパイルを止めて起動時 CPU を減らす (定常性能は落ちる) | 検索要約のみ (ブログ。公式 doc 未確認) | 技術記事 |
| warm-up リクエストを Ready 前に流す | Ready 前に自分でトラフィックを当てて JIT を終えてから Ready にする (BlaBlaCar、Azul の JMX による未完了コンパイル数でゲート) | 検索要約のみ。BlaBlaCar の Medium 記事は 403 で本文を取れなかった | 技術記事 |

**注意**: JVM 側の対策 (CRaC・AOT・native) は『アプリの実装を変える』ので、本研究 (Sock Shop の公開イメージのまま比較) では**使わず、限界・今後の課題に書くのが妥当**。使う候補は K8s 側の設定 (readiness / startupProbe / 起動時間に合わせた枠) だけ。

### 12.4 技術資料 (学術でない。区別して書く)
- Kubernetes 公式 HPA doc (上記) ★、probes doc ★。
- GKE "CPU startup boost" ブログ (Google Cloud, 2026-10-03, Abdel Sghiouar ほか) ★原文確認 — Spring Boot の起動 CPU を *"class loading, classpath scanning, instantiating dependency injection containers, and running Just-in-Time (JIT) compilation"* と列挙。URL: https://cloud.google.com/blog/products/containers-kubernetes/gke-cpu-startup-boost-faster-pod-starts-lower-costs
- BlaBlaCar "Warm up the relationship between Java and Kubernetes" (Medium、https://medium.com/blablacar/warm-up-the-relationship-between-java-and-kubernetes-7fc5741f9a23) — **本文は 403 で取れず、検索要約のみ**。要約 = 冷たい Pod が長く CPU を使う → HPA が増やす → さらに冷たい Pod が増える循環。対策 = Ready 前の warm-up。著者・日付は未確認。引用するなら本文を読んでから。
- StormForge / CloudBolt "scale jvm kubernetes"、Azul/Kedify、Alibaba Cloud (CPU burst) — 検索要約のみ。ベンダ記事。

### 12.5 位置関係の判定 (まとめ)
| 文献 | 判定 | 理由 |
|---|---|---|
| Dashtbani & Tahvildari 2025 | **背景 (現象の先行例。『新発見』と書かない)** | 同じ現象と readiness での対処を書く。同居・Pod 粒度は扱わない |
| Nunes 2024 / ScalerEval / STaleX | 無関係 (この論点では) | Java warm-up の対処を書いていない |
| Barrett 2017 | 背景 (引用前に精読) | warm-up は一定でない、の一般的根拠 |
| K8s 公式 doc | 背景 (方法節の根拠) | 方法の根拠として引用 |

### 12.6 検索の記録 (2026-11-10、WebSearch + curl で原典取得)
- WebSearch: "Kubernetes HPA Java startup CPU spike JIT compilation autoscaler overscaling warm-up" (技術記事 10 本以上、学術 0)、"JVM warm-up microservices autoscaling cold start containers Kubernetes paper arXiv" (arXiv:2510.02585 が唯一の学術)、"Sock Shop autoscaling HPA experiment Java carts orders warm-up period"、"\"Sock Shop\" \"JVM\" warm-up autoscaling evaluation ..." (extended。2510.02585、2403.08798、2504.08308 など)、"Barrett ... Virtual Machine Warmup"、"JVM startup warm-up techniques survey CRaC GraalVM ..." (学術の総説は出ず、ブログのみ)、"empirical study Java cold start JIT ... arXiv" (サーバーレスの cold start 研究ばかりで HPA とは無関係)、"horizontal pod autoscaler new pods startup transient ... cpu-initialization-period study" (公式 doc・ベンダ・コミュニティ投稿のみ)。
- 出なかったもの (空白の根拠): 『HPA × JVM 起動 CPU』を**実測で定量**した査読論文 (Dashtbani 以外)。『CRaC の査読つき測定』。範囲 = WebSearch (Google Scholar / IEEE Xplore / ACM DL の直接検索はしていない)。空白と断定しない。
- 取れなかった: BlaBlaCar (Medium 403)、openjdk.org の WebFetch (403。curl は通る)。

### 12.7 次に読むべきもの
1. Dashtbani Fig. 1 の図と §VI (評価) を目で確認 — 暴走の台数と、readiness 対処後の効果が図で示されているか (pdftotext では図の中身は見えない)。
2. BlaBlaCar の記事の本文 (ブラウザで) — 『Ready 前に warm-up リクエストを流す』の具体的な手順と数値。
3. Barrett et al. 2017 の本文 — warm-up が一定でないことの根拠。
4. 実機で確認: 180 s 遅延 readiness にしたとき、Ready 直後の 0〜120 秒の CPU が HPA に入るか (§12.2 の 2)。

### 12.8 Sock Shop を HPA／オートスケールの評価に使った論文は Java の特性をどう扱ったか (2026-11-10 追加調査)

**目的**: 「Sock Shop の Java (carts / orders / shipping / queue-master) の起動時 CPU・warm-up・メモリ・GC に先行研究は触れているか」を本文で確かめ、本研究が JVM 対策 (readiness 遅延など、§9.16) を『先行研究の標準』として引けるかを判断する。
**方法**: §7.2・§13.1 の Sock Shop 利用論文の PDF を `pdftotext` し、`Java|JVM|Spring|warm-up|cold start|startup|JIT|garbage|GC|class load|heap|readiness|probe|boot|initialization delay|ramp` を、改行を潰した全文に対して検索 (前後 150〜300 字を目視)。ページ番号は pdftotext の改ページで数えた (論文のページ番号と 1 ずれうる)。
Dashtbani & Tahvildari 2025 は §12.1.1 のとおり (参照のみ)。

**結論 (先に)**: **Dashtbani 2025 以外の Sock Shop×オートスケール論文 11 本 (下表) は、Java／JVM の起動・warm-up・GC に言及していない (または一般論 1〜2 行のみ)。** 言語構成を一文で説明するのは PEMA と Buzato 系の 2 本だけで、いずれも特性には踏み込まない。
したがって (i)「Sock Shop の Java で HPA が暴走する」を『この分野で既知の標準的注意』として引けるのは Dashtbani 1 本だけ、(ii) 他の論文の Sock Shop の結果には JVM の起動 CPU が**混ざっている可能性**があるが、各論文は除去も議論もしていない (ここは推測。実測はしていない)、と書ける。

| 論文 (bib / 出所) | (1) 言及の有無と原文 (節・ページ) | (2) 扱い | (3) 結果の解釈に使ったか | 確認度 |
|---|---|---|---|---|
| COLA (arXiv:2112.14845 v3、bib `sachidananda2022cola`) | Java／JVM／warm-up の語は**本文に無し** (参考文献を除く grep で 0 件)。『startup script』は VM 起動時のデータ投入の話で JVM ではない (§評価の制約) | 言及なし。負荷は 10 分／負荷、評価で『接続数を起動時に 1 度調整』(クライアント側の話) | 使っていない | ★PDF 全文 grep |
| PEMA (arXiv:2202.00057、HPDC'22、bib `hossen2022`) | **言語構成の説明のみ**: 「The front-end is implemented using NodeJS, orders and carts microservices are implemented using Java, and the rest ... Go. ... Queue-Master which is implemented in Java」(§2.1 Microservice Prototypes、PDF p.3)。JVM／warm-up／GC の語なし | 言及なし。PEMA は CPU 配分を反復で探す方式で、『反復ごとに応答時間を見る』設計。起動の遅さは扱わない | 使っていない (Java は性能差の説明に出ない) | ★PDF 全文 grep |
| ScalerEval (arXiv:2504.08308、FSE Companion'26、bib `xie2026scalereval`) | 『System startup』の節 (p.2) は『ベンチマークの導入・初期状態の準備』の話で、JVM ではない。Java／JVM／warm-up の語なし | 評価ごとに環境を『reset』して独立性を保つ (p.2)。= 起動直後の影響を**手順で揃える**が、Java 固有の対策ではない | 使っていない | ★PDF 全文 grep (4 頁の短報) |
| STaleX (arXiv:2501.18734、bib `dashtbani2025stalex`) | 一般論のみ: 「variations in computational needs or initialization delays during scaling require service-specific scaling parameters」(§I)、「service boot time」(特徴量、§III p.3)、「Each service has unique timing characteristics, including its startup time and resource provisioning requirements」(p.4) | **サービスごとの起動時間で PID 制御のループ周期を変える**(「we adjust the PID controller's loop timing based on each service's boot time」)。= 起動の遅さをスケーラの設計に取り込む唯一の例。ただし Java／JVM とは書かない | 設計の動機に使うが、Java の特性として説明はしない (同じ著者の Dashtbani 2025 が、後で JVM を扱う) | ★PDF 全文 grep |
| MS-RA (arXiv:2403.08798、SEAMS'24、bib `nunes2024`) | 一般論: 「Optimizing startup time: The server type influences resource consumption during container startup, with expensive startups potentially impacting autoscaling efficiency. Some servers initially require substantial resources, which decrease significantly post-startup」(§2、p.3)。Java／JVM の語は JMeter の説明にのみ | 『要求仕様』の項目として起動の高コストを挙げるが、**実験での対処 (warm-up 時間・readiness) の記述なし** | 使っていない (HPA が台数を 20 まで増やす現象は『stabilization 時間』で説明、Java の起動とは結ばない) | ★PDF (§12.1.2 の再確認。今回は全文 grep) |
| StatuScale (arXiv:2407.10173、TAAS'25、bib `wen2025statuscale`) | **語なし** (Java／JVM／warm-up／startup のいずれも 0 件)。『cooling-off period』は頻繁なスケール抑止 (jitter) の一般機構 | 『cooling-off period』を入れる (起動の遅さが理由とは書かない) | 使っていない | ★PDF 全文 grep |
| Buzato & Goldman 2026 IJNC (bib `buzato2026ijnc`) | **言語構成の説明のみ**: 「The microservices in this application are developed using Java, Go, and Node.js」(§3.1、p.6)。束ね方 By-stack は Java サービス (Cart, Order, Shipping, Queue) を 1 コンテナに束ねる。JVM／warm-up／GC／起動の語なし | 言及なし。HPA は 150% しきい値・最大 4 Pod (理由は『1 ノードの Pod 数上限』で JVM ではない)。**各シナリオ 10 分、新規ユーザを前半 5 分で追加** (負荷の立ち上げのみ) | 使っていない。メモリ・CPU の増加は『スループットが増えるから』と解釈 (thesis §5.2、§7.3 で既記) | ★PDF 全文 grep (IJNC)。**修士論文 (thesis) は今回再取得に失敗し Java 観点では未再確認** (§7.3 のとき別目的で精読済み) |
| LSRAM (arXiv:2411.11493)、MSARS (arXiv:2409.14953)、ChainsFormer (arXiv:2309.12592)、ORACL (arXiv:2602.05292) | LSRAM・ChainsFormer: Java／warm-up／startup の語なし (参考文献を除く)。MSARS: 『cold starts』は**強化学習の初期学習の話**で JVM ではない。ORACL: 『initial warm-up interval』(p.11) は**学習・比較手法 FIRM の初期の遅延**で JVM ではない | いずれも対処なし | 使っていない | ★PDF 全文 grep |
| Dashtbani & Tahvildari 2025 (bib `dashtbani2025`) | §12.1.1 を参照 (carts の JVM 起動 CPU、readiness、cgroup で起動時のみ CPU 増など) | 同上 | 同上 | ★PDF (§12.1.1) |
| Avritzer 2020／Camilli 2022／Rahman & Lama 2019 | **今回も未確認** (Rahman は著者 PDF の URL を再特定できず取得失敗。Avritzer・Camilli は有料／EuropePMC、今回未取得)。これらは HPA ではなく『配置構成・性能モデル』の論文 | — | — | 未確認 |

**読み取れること**
1. 『Sock Shop の Java の warm-up を扱った論文』は標本では Dashtbani 2025 のみ。**本研究が readiness 遅延で Java を扱うのは先行研究の標準手順に従うわけではなく、Dashtbani と K8s 公式 doc に拠る**、と書く (§9.16 の方針と一致)。
2. 先行研究の Sock Shop の結果は、Java の起動 CPU を含んだまま HPA 比較をしている可能性がある (推測)。『分離 (Sock Shop 既定) の HPA 台数が Java の起動で膨らむ』ことは、既存の比較 (MS-RA の 20 台張り付きなど) の一因かもしれないが、各論文は原因を JVM と書いていないので**引用して断言しない**。
3. STaleX の『起動時間でスケーラの周期を変える』は、**起動の遅さを制御設計に入れた例**として Related Work に一行引ける (JVM とは書いていない点を明記)。

**検索の範囲 (限定)**: 上記 PDF の全文 grep (語の網羅は上のとおり)。追加の WebSearch 1 本 ("Sock Shop autoscaling Kubernetes carts orders Java Spring Boot slow startup JVM CPU spike HPA evaluation paper") は Dashtbani・MS-RA・STaleX・StatuScale を返しただけで新しい論文は出なかった。Google Scholar／IEEE／ACM DL の直接検索はしていない。ここに載らない Sock Shop 論文が JVM に触れている可能性は残る (『先行例は Dashtbani のみ』と断定せず『確認した範囲では』と書くこと)。

---

## 13. HPA／オートスケール論文が評価に使うベンチマーク OSS と、3 つ目のアプリの選定 (2026-11-10)

**目的**: ユーザの依頼「HPA を扱っている論文で利用されている OSS を調査し、3 つ目のアプリの参考にしたい」。
**方法**: WebSearch で候補論文を拾い、arXiv／USENIX／著者サイトの PDF を `pdftotext` して実験節を grep・読了。アプリ側は GitHub (API と raw) の README・ソース・manifest・ライセンスを直接取得。
**範囲の限定 (重要)**: これは**系統的サーベイではない**。WebSearch ＋ 既存 §6・§7 の芋づる＋ Dashtbani/COLA の参考文献、で集めた 19 本の標本。Sock Shop を使う論文は §7 の検索が先にあったので**偏って多い**可能性が高い。
頻度は「目安」であり、母集団の割合ではない。Google Scholar／IEEE Xplore／ACM DL の直接検索はしていない。
確認度の記号: **★PDF** = 原典 PDF を取得し該当節を読んだ (全文精読ではない箇所は明記) / **abstract のみ** / **未確認**。

### 13.0 結論

1. **評価に使われるアプリは 5 系統に集約される**。Sock Shop (8 本)、Online Boutique (7 本)、Train-Ticket (6 本)、DeathStarBench の Social Network／Hotel Reservation (どちらも 5 本、DSB 全体で 7 本)、Bookinfo (2 本)、TeaStore (2 本)。Acme Air と Robot Shop は HPA 論文の**評価対象としては標本に 0 本** (Robot Shop は GRAF の動機図に出るのみ)。
2. **本研究の既存 2 アプリ (OB と SS) は、この分野で最も使われる 2 つそのもの** (標本 19 本中、OB 7 + SS 8)。3 つ目を何にしても比較のしやすさ (条件 e) は、DSB の Hotel Reservation が最良 (標本で 5 本が使用、Sinan／FIRM／PEMA／Autothrottle／StatuScale)。
3. **条件 (a)〜(e) を総合した推薦**:
   - **第 1 候補: DeathStarBench Hotel Reservation** — Go・gRPC (JVM なし、条件 d 良)、リクエスト型が 4 種 (search／recommend／reserve／user) で配合の既定値がコードにある (条件 a 良)、先行例が多い (条件 e 良)、軽い (条件 b、推測)。**弱点 = 宛先が Consul 経由 (環境変数ではない)** (条件 c は中)。
   - **第 2 候補: OpenTelemetry Demo (astronomy shop)** — 宛先が `*_ADDR` 環境変数でサービスごとにポートが異なる (条件 c 良)、多言語だが JVM 系が 3 つ (ad・recommendation・fraud-detection。recommendation は閲覧経路上にある) (条件 d はやや難)、Locust が重み付きタスク (条件 a は中)。**弱点 = HPA 論文での先行例が標本 0 本 (条件 e 悪)**、観測基盤 (Kafka・OpenSearch・Jaeger 等) が重い。
   - **第 3 候補: TeaStore** — 公式に **browse と buy の 2 プロファイル** (Lua) がある (条件 a は最良)、性能工学の標準アプリ (ICPE/MASCOTS) で HPA との比較例あり。**弱点 = 6 サービス全て Java (条件 d 悪)**、Tomcat の待受ポートが共有ベースイメージで 8080 固定で、サービス発見が registry 経由 (条件 c 悪)。ユーザの懸念 (JVM 起動 CPU で HPA が暴走) がそのまま当たる。
   - **非推奨: Train-Ticket** (42/47 サービスが Java、条件 d・b 悪)、Bookinfo (4 サービスで同居の組合せが乏しい)、Social Network (Thrift・C++、36 サービス、本研究の gRPC／HTTP と通信方式が違い過ぎる。ただし負荷配合 read-home 0.6／read-user 0.3／compose 0.1 の既定値はある)。
4. **新発見 (衝突候補) — Buzato & Goldman (2026, IJNC)**。§7.3 の Buzato 修士論文の**査読付きジャーナル版** (HPA 実験)。Sock Shop で「複数サービスを同一コンテナに束ねる × HPA」を測っており、主題が近い。判定 = **相補** (理由は 13.4)。Related Work に必須。

### 13.1 論文ごとの表 (評価に使ったアプリ・負荷ツール・オートスケーラ)

凡例: SN = Social Network、HR = Hotel Reservation、MM = Media、OB = Online Boutique、SS = Sock Shop、TT = Train-Ticket、BI = Bookinfo、TS = TeaStore。「基準」= 比較相手のオートスケーラ。「—」= 本文に記述なし／読んだ範囲で見つからず。

| # | 論文 | 年 | 会議／誌 | アプリ | 負荷ツール | 基準 (比較相手) | 環境 | 確認度 |
|---|---|---|---|---|---|---|---|---|
| 1 | Sachidananda & Sivaraman "Collective Autoscaling for Cloud Microservices" (COLA。arXiv v3。**公刊版は EuroSys '24 "Erlang" と推定** — Crossref の同著者・同題材、タイトルは別。同一内容かは未照合) | 2021/2022 | arXiv:2112.14845 | Simple Web Server、BI (4)、OB (11)、SS (14)、TT (64) の 5 つ (括弧は論文表のサービス数) | Locust | **K8s HPA** (CPU しきい値 10〜90% を掃引)、クラスタオートスケーラ | GKE | ★PDF (表 1 と §2、2026-11-10) |
| 2 | Qiu ほか "FIRM" | 2020 | OSDI '20 | DSB (SN・MM・HR) と TT の計 4 ベンチ | wrk2 (負荷変動注入) | K8s autoscaling、AIMD | K8s | ★PDF (grep、2026-11-10) |
| 3 | Zhang ほか "Sinan" | 2021 | ASPLOS '21 (DOI 10.1145/3445814.3446693) | DSB の SN、HR | Locust | 経験的オートスケール (本文 [4])、PowerChief。**Docker Swarm 上であり K8s ではない** | 4 台の 80 コアサーバ + GCE | ★PDF (grep、2026-11-10) |
| 4 | Wang ほか "Autothrottle" | 2024 | NSDI '24 | TT、SN、HR | Locust (全リクエスト型を混ぜる) | **K8s-CPU、K8s-CPU-Fast** (K8s 既定の CPU 方式。HPA そのものかは未確認)、Sinan | K8s | ★PDF (grep、2026-11-10) |
| 5 | Hossen, Islam, Ahmed "PEMA" | 2022 | HPDC '22 | TT (41)、SS (13)、HR (18) | — (RPS を指定する形。ツール名は本文に見つからず) | 商用の規則ベース (RULE)、最適 (OPTM) | K8s 5 台 (2×10 コア Xeon) | ★PDF (grep、2026-11-10) |
| 6 | Park ほか "GRAF" | 2021 | CoNEXT '21 (DOI 10.1145/3485983.3494866) | SN (評価)、OB (評価)。Robot Shop と BI は動機の図のみ | SN は Vegeta、OB は Locust | K8s オートスケーラ | K8s | ★PDF 一部 (ダウンロードが途中で切れた PDF を grep、2026-11-10) |
| 7 | Xie ほか "PBScaler" | 2024 | IEEE TSC 17(2) 604–616 (DOI 10.1109/TSC.2024.3376202) | OB、TT | — (Wiki 由来の負荷パターンを注入。ツール名は未確認) | KHPA、MicroScaler、SHOWAR | 3 台 (計 44 コア、220 GB) | ★PDF (grep) |
| 8 | Ahmad ほか "Smart HPA" | 2024 | ICSA '24 (DOI 10.1109/ICSA59870.2024.00013) | OB | Locust (OB 付属スクリプト) | **K8s HPA** | AWS t3.medium × 10 | ★PDF (§IV 冒頭の実験環境と負荷の節を確認。全文精読ではない) |
| 9 | Ahmad ほか "SecureSmart HPA" | 2025 | arXiv:2506.05693 | OB | Locust | HPA 系 | — | ★PDF (grep) |
| 10 | Meng ほか "DeepScaler" | 2023 | ASE '23 (DOI 10.1109/ASE56229.2023.00038) | TT (41)、OB、BI | Locust (開ループ非同期と著者が記述) | AWS 方式、MMN、他 (K8s HPA は未確認) | 公衆クラウド | ★PDF (grep) |
| 11 | Xie ほか "ScalerEval" | 2026 | ACM FSE Companion '26 (DOI 10.1145/3803437.3806415、4 頁) | OB、SS | Locust (Wiki-Pageviews 由来) | KHPA (20/50/80%)、Showar、PBScaler | K8s + Istio | ★PDF (§7.2 と同じ) |
| 12 | Dashtbani & Tahvildari "Key Considerations..." | 2025 | arXiv:2510.02585 (bib `dashtbani2025`) | SS (評価)。BI・OB・SS・TT の 4 つを導入して課題を比較 | Locust + WorldCup98 | 6 手法 (KHPA 含む) | 1 台 (AMD EPYC 7742 2 基) | ★PDF (§12 参照) |
| 13 | Dashtbani & Tahvildari "STaleX" | 2025 | arXiv:2501.18734 | SS | Locust + WorldCup98 | HPA | 自前 K8s | ★PDF (grep) |
| 14 | Nunes ほか "MS-RA" | 2024 | SEAMS '24 (bib `nunes2024`) | SS | JMeter | **K8s HPA** | — | ★PDF (§12) |
| 15 | Wen ほか "StatuScale" | 2025 | ACM TAAS 20(1) 1–25 (DOI 10.1145/3686253) | SS (8 サービス)、HR | Locust + Alibaba トレース | 3 つの最先端手法 (HPA を含むかは未確認) | K8s | ★PDF (grep) |
| 16 | Goli ほか "Waterfall" | 2021 | CLOSER '21 (DOI 10.5220/0010407701900198) | **TS** | **JMeter** (25 分の browse 負荷) | **K8s HPA** | K8s 1 + 4 ノード | ★PDF (§6、2026-11-10) |
| 17 | Horn, Fard, Wolf "Multi-objective Hybrid Autoscaling" | 2022 | Euro-Par '22, LNCS 13440, pp.233–250 (DOI 10.1007/978-3-031-12597-3_15) | **TS と推定** (著者の GitHub リポジトリの dataset 名と TeaStore の README の事例一覧による間接確認。論文本文は未取得) | — | 一般的な HPA | — | abstract + 間接 (本文未読) |
| 18 | Buzato & Goldman "Extended version of Microservices Performance Optimization Through HPA" | 2026 | Int. J. Networking and Computing 16(1) 52–75 (DOI 10.15803/ijnc.16.1_52。ページ頭は "Number 2" と表記) | SS | Locust (閉ループ) | HPA の有無 × 4 通りの束ね方 | AWS EKS、t3.xlarge | **★PDF (全文の主要節、2026-11-10)** |
| 19 | AdaScale (§6.3.1) | 2026 | arXiv:2607.15681 | SN | — | K8s HPA、NetMARKS_Scale | 16 VM | abstract + HTML 要約のみ (§6.3.1) |
| — | BASE (Meng ほか) arXiv:2402.12962 (TSC 2026, DOI 10.1109/TSC.2026.3668105) | 2026 | IEEE TSC | **未確認**。WebSearch の要約は「OB・SS・TT を含む 5 ベンチ」と書いたが、私が取得した arXiv v2 の本文に benchmark 名・Locust 等の語が 1 つも出ない (grep 0 件)。要約の誤りか版の違いか不明なので**表に含めない** | — | — | — | 未確認 |
| — | Zafar ほか (配置系、§7.2) | 2026 | arXiv:2606.25922 | SS・TS・BI を同時 | k6 | — | — | §7.2 の記録のみ |

SS を使う他の論文 (Avritzer、Camilli、Rahman、LSRAM、MSARS、ChainsFormer、ORACL、RCA 系など) は §7.2 の表にある。それらの多くは負荷の研究か故障診断で、HPA 論文ではない。

### 13.2 アプリ別の使用頻度 (標本 19 本。上の表 #1〜#19、重複して数える)

| アプリ | 本数 | 使った論文 (#) | 備考 |
|---|---|---|---|
| Sock Shop | 8 | 1, 5, 11, 12, 13, 14, 15, 18 | MS-RA、STaleX、Buzato で HPA と直接比較 |
| Online Boutique | 7 | 1, 6, 7, 8, 9, 10, 11 | Smart HPA 系は OB 付属の Locust をそのまま使用 |
| Train-Ticket | 6 | 1, 2, 4, 5, 7, 10 | 全て大規模クラスタ。サービス数 41〜64 |
| DSB (SN／HR／MM) | 7 (SN 5、HR 5、MM 1) | 2, 3, 4, 5, 6, 15, 19 | SN: 2, 3, 4, 6, 19。HR: 2, 3, 4, 5, 15 |
| Bookinfo | 2 (評価)＋2 (動機・解析のみ) | 1, 10 (評価)／6, 12 | |
| TeaStore | 2 | 16, 17 | 17 は間接確認 |
| Acme Air／Robot Shop | 0 (評価) | — | Acme Air は Buzato の関連研究、Robot Shop は GRAF の動機図のみ |

負荷ツール (確認できたものの本数): Locust 12 (1, 3, 4, 6〔OB〕, 8, 9, 10, 11, 12, 13, 15, 18)、JMeter 2 (14, 16)、wrk2 1 (2)、Vegeta 1 (6〔SN〕)。**k6 は HPA 論文では見つからず**、§7.2 の Zafar 1 本のみ。
開ループか閉ループかを明記したのは DeepScaler の「open-loop asynchronous」のみ (§7.2 の結論と同じ)。

### 13.3 アプリ別の特徴表

確認度: **[原典]** = GitHub のソース・README・manifest・LICENSE を 2026-11-10 に取得して確認 / **[論文]** = 論文の記述を孫引き / **[推測]** = 私の推測。

| 項目 | Online Boutique (既存) | Sock Shop (既存) | **Hotel Reservation (DSB)** | **OpenTelemetry Demo** | **TeaStore** | Train-Ticket |
|---|---|---|---|---|---|---|
| 作者・リポジトリ | Google `GoogleCloudPlatform/microservices-demo` | Weaveworks `microservices-demo/microservices-demo` | Cornell `delimitrou/DeathStarBench` の `hotelReservation/` | OpenTelemetry `open-telemetry/opentelemetry-demo` | Würzburg 大 `DescartesResearch/TeaStore` | 復旦大 `FudanSELab/train-ticket` |
| サービス数 | 11 [原典 README の表: アプリ 10 + loadgenerator] | 8 + インフラ 5 (Buzato の記述 [論文]) | アプリ 10 (`services/` 直下の 10 ディレクトリ) [原典]。`config.json` から MongoDB 8・memcached 4 の宛先 [原典]。PEMA は 18 と数える [論文] | `src/` 直下に約 15 のアプリサービス (ad, cart, checkout, currency, email, fraud-detection, accounting, payment, product-catalog, quote, recommendation, shipping, frontend, frontend-proxy, image-provider, load-generator など) + Kafka・PostgreSQL・OpenSearch・Jaeger・Prometheus・Grafana 等 [原典 `src/` の一覧] | 5 サービス (webui, auth, persistence, image, recommender) + registry + MariaDB [原典 README] | 41 [原典 README]。リポジトリの `ts-*` は 47 ディレクトリ [原典] |
| 言語 | Go (frontend, checkout, productcatalog, shipping)、C# (cart)、Node.js (currency, payment)、Python (email, recommendation)、**Java は ad のみ** [原典 README] | Java (carts, orders, shipping, queue-master)、Go (catalogue, user, payment)、Node.js (front-end) [論文 Buzato] | **全て Go** [原典 README 冒頭「build with Go and gRPC」] | 多言語: Go (checkout, product-catalog)、.NET (cart, accounting)、**JVM 系 3 つ = ad, recommendation, fraud-detection** (`build.gradle` の有無で判断)、Node.js (frontend, payment)、C++ (currency)、Rust (shipping)、Ruby (email)、PHP (quote)、Python (load-generator ほか) [原典 `src/` のツリーの build ファイル、2026-11-10。言語は拡張子でなくビルドファイルからの判断] | **全て Java** (Tomcat + WAR) [原典 Dockerfile・start.sh] | **42/47 ディレクトリが `pom.xml` を持つ (Java)**、残りは Node.js・Python・Go [原典 repo tree、README の言語表と整合] |
| 通信方式 | **gRPC** (frontend→各サービスは gRPC、利用者→frontend は HTTP) | **HTTP (REST)** + 非同期 RabbitMQ | **gRPC** (+ HTTP の frontend) [原典 dialer.go] | gRPC と HTTP の混在 (`EMAIL_ADDR=http://...`、`SHIPPING_ADDR=http://...`、他は host:port) + OTLP [原典 .env] | HTTP (REST) + Netflix Ribbon によるクライアント側負荷分散 [原典 README] | HTTP (REST、Spring) [README] |
| 状態を持つサービス | 1 (Redis。cartservice 用) | 4〜5 (MongoDB 3、MySQL 1、RabbitMQ 1 ほか) | MongoDB 8 + memcached 4 [原典 config.json] | PostgreSQL、Kafka、OpenSearch ほか (Valkey は未確認) | MariaDB 1 | MySQL (サービスごと。数は未精査) |
| 負荷の種類 | Locust: 1 つの利用者クラス内の重み付きタスク (browse が主、addToCart、checkout)。**本研究の自作 k6 で購入型／閲覧型を分けている** | 上流 load-test は 1 本のみ (§7.1)。**自作 k6 で購入型／閲覧型** | `mixed-workload_type_1.lua` (wrk2) 1 本に **4 種の型の比 search 0.60／recommend 0.39／user 0.005／reserve 0.005** [原典]。型ごとに通るサービスが異なる (search→search,geo,rate,profile／recommend→recommendation,profile／reserve→reservation,user) | Locust: `WebsiteUser` に重み付きタスク (browse_product 10、get_recommendations 3、get_ads 3、view_cart 3、add_to_cart 2、checkout 1、checkout_multi 1、flood_home 5、ask_agent 3 ほか)、Playwright ブラウザ利用者も [原典 locustfile.py] | **公式に 2 プロファイル `teastore_browse.lua` (DB を変更しない閲覧) と `teastore_buy.lua` (注文まで)**、JMeter の browse、Locust (50% が購入) [原典 examples/] | Locust 等 (複数シナリオ、未精査) |
| 宛先の変更 (同居のしやすさ) | **◎ 環境変数 `*_SERVICE_ADDR`**。ポートはサービスごとに異なる (本研究で実績) | **× 全てポート 80、宛先は固定名** (本研究で困った点) | **△** サービス間は `consul://consul:8500/srv-xxx` で **Consul 登録経由**。ポートは `config.json` でサービスごとに別 (8081〜8089)。宛先名 "srv-xxx" は Go ソース内の文字列 [原典 server.go・dialer.go・config.json] | **○** `.env` に `*_ADDR` (host:port) があり、サービスごとにポートが違う (AD 9555、CART 7070、CHECKOUT 5050、CURRENCY 7001、EMAIL 6060、PAYMENT 50051、PRODUCT_CATALOG 3550、RECOMMENDATION 9001、SHIPPING 50050 ほか) [原典 .env]。manifest は Helm/生成物で未精査 | **×** Tomcat の待受は共有ベースイメージの `server.xml` で **8080 固定** (さらに 8005／8009)、`SERVICE_PORT` は registry への**通知用**で待受を変えない。サービス発見は registry 経由 [原典 server.xml・start.sh・GET_STARTED.md]。同居するには**イメージの作り直し**が要る | 不明 (未精査) |
| 保守状況 (最終 commit) | 活発 (2026-10-27) | **アーカイブ済み** (2023-12-05、"deprecation notice") | 2024-06-27 (リポジトリ全体)。更新は鈍い | **活発** (2026-11-07) | 2025-01-08 (README 修正)。最新リリース v1.4.2 は 2022-08-17 | 2022-11-01 (既定ブランチ)。他ブランチに 2025-11 の push あり |
| K8s manifest | あり (`kubernetes-manifests/`、`release/`) | あり (本研究で使用) | あり (`hotelReservation/kubernetes/`、`helm-chart/`) | **Helm チャート**、`kubernetes/` に生成物 (今回未精査) | あり (`examples/kubernetes/` の `teastore-clusterip.yaml` 等 9 本と Helm) | Helm (README) |
| ライセンス | Apache-2.0 | Apache-2.0 | **README は GPL v2、リポジトリの LICENSE ファイルは Apache-2.0** (**食い違い**。引用時は README の記述に注意) [原典] | Apache-2.0 | Apache-2.0 | Apache-2.0 |
| 16 vCPU に載るか | 載る (本研究で実績) | 載る (本研究で実績) | **載る見込み** [推測: Go 10 サービス + データ層、各 Go サービスは軽量] | 載るが**観測基盤が重い** [推測。メモリ要件は README の grep では出ず未確認] | 載る見込み [推測: 6 JVM + MariaDB。JVM のヒープ設定は `TOMCAT_HEAP_MEM_PERCENTAGE`] | **厳しい** [推測: 42 の Spring JVM。1 つ 300〜500 MB なら 12〜20 GB。COLA は 64 サービスを GKE で動かした [論文]] |
| 先行例の数 (標本) | 7 | 8 | **5** (Sinan, FIRM, PEMA, Autothrottle, StatuScale) | **0** (WebSearch で HPA 論文は見つからず) | 2 | 6 |

DeathStarBench Social Network (参考): Thrift RPC、C++ 中心、論文表 1 で 36 ユニークサービス・Media 38 [論文 DSB ASPLOS'19 を取得し表 1 を確認]。`mixed-workload.lua` の比は read-home 0.60／read-user 0.30／compose 0.10 (§10.1 で確認済み)。
- **SN の宛先と同居のしやすさ (2026-11-14、`delimitrou/DeathStarBench` commit 6ecb097 (2024-06-27) の `socialNetwork/` を取得して確認)**: (1) C++ の各サービスは自分の待受ポートも相手の宛先 (addr・port) も **`service-config.json` から読む** (例 `src/TextService/TextService.cpp` 26〜35 行)。環境変数ではない。(2) **全アプリサービスの待受が 9090 で同じ** → 同じ Pod に入れるとポートが衝突するので、同居させるサービスはポート番号を変える必要がある (SS の『全部 80』と同じ問題だが、SN は設定ファイルで変えられる)。(3) Helm チャートは**サービスごとに別の ConfigMap** に `service-config.json` を入れて `/social-network-microservices/config/` に差し込む (`charts/<svc>/values.yaml` の configMaps、`templates/_baseConfigMap.tpl`) → `helm template` で書き出せば、Pod ごとに宛先を localhost に書き換えられる。(4) 例外は入口の **nginx-thrift**: 宛先を Lua スクリプトに直書き (`"compose-post-service" .. k8s_suffix, 9090` など、`nginx-web-server/lua-scripts/`)。しかも Helm 版は起動時の initContainer で**別人のフォーク (`github.com/dimoibiehg/DeathStarBench`) を git clone して** Lua を取ってくる → nginx を同居の対象にするなら Lua を書き換えて ConfigMap 等で差し込む必要がある。再現性の面でも、起動のたびに外部のフォークを取る点は固定が要る。(5) Helm の既定は requests = limits = CPU 100m・メモリ 128Mi、レプリカ 1、HPA のひな形 (`_baseHPA.tpl`、autoscaling/v2、CPU とメモリ 60%、1〜10 台) は既定で無効。


### 13.4 位置関係の判定

| 文献 | 判定 | 群 | 理由 |
|---|---|---|---|
| **Buzato & Goldman 2026 (IJNC)** | **相補 (最重要。引用して差分を明示)** | B 群＋同居系 | 同じ主題の近縁。**ベースラインは「HPA 付きで 1 マイクロサービス = 1 コンテナ (Pod)」** (本研究の分離と同種で、ICTer のような 1 サービス 1 ホストではない)。束ねる単位は**「同一コンテナ内に複数サービスのプロセス」** (Pod 内の別コンテナではない。§7.3 と同じ、論文は Pod 内同居を扱わないと thesis に明記)。環境は AWS EKS・t3.xlarge (4 vCPU)・**シナリオごとに 2 ノード**・Locust 閉ループ・HPA は CPU／メモリ**150%**・1〜4 Pod・6 サンプル。指標は throughput・応答時間・絶対 CPU・メモリ・費用など (softirq／リクエスト当たりは無し、予約枠 requests の増減も測っていない)。結果は「束ねるほど HPA 下で throughput +66% (all-in-one、中負荷)、応答時間 −32%」。静的な束ね (4 通り固定)。**今回判明した新事実**: 本誌版は「相関分析」「実務の指針」「束ね方の決定木 (負荷強度・結合度・運用優先度で選ぶ)」を追加し、「**変動が大きい／異種の負荷では、より modular な束ねが望ましい**」と定性的に書く (IJNC 本文 §7.2 の指針 1)。さらに指針 5 で「Kubernetes の **Pod 内での束ね**は中間案になりうる」と述べ、**§8 の今後の課題に「Pod 内の束ね (同一コンテナでなく同一 Pod) への拡張」を明記**している (原文、2026-11-10)。= 著者自身が Pod 内同居を**未着手**と認めている (本研究の空白の傍証)と同時に、**同じ著者グループが次に同じことをやりうる**という競合リスク。この文は本研究の「配合に応じて必要台数が入れ替わる相手とは損が出る」と**方向が同じ**。ただし根拠は定性的で、需要の向き ρ のような測定量は持たない。衝突でない根拠: ①Pod 内コンテナ同居ではない、②予約枠の増減を測らない、③閉ループ・絶対 CPU、④選択基準が定性的。 |
| COLA／Erlang | 背景 (C 群) | | HPA を基準に、Online Boutique・Sock Shop 等で評価。別 Pod 前提 (§4)。 |
| Smart HPA／SecureSmart HPA | 背景 (C 群) | | サービスごとの HPA の上限・下限を動的に再配分。Online Boutique。同居は扱わない。 |
| PBScaler／DeepScaler／ScalerEval／Dashtbani 系 | 背景 (C 群) | | 評価アプリの使われ方の根拠。 |
| FIRM／Sinan／Autothrottle | 背景 (C 群) | | DSB と TT の使用例。**Autothrottle は本文で「リクエスト型の構成は一定のまま (constant workload composition)」と明記** — 配合を振る本研究と対比できる。 |
| Goli ほか 2021 (TeaStore + HPA) | 背景 | | TeaStore を HPA と比べた例。同居は扱わない。 |

### 13.5 3 つ目の適性の判定 (条件 a〜e)

評価: ◎ 良い／○ 可／△ 難あり／× 悪い。根拠の [原典]／[推測] は 13.3 の表のとおり。

| 候補 | (a) 2 種以上の負荷・反応の向きが違う | (b) 16 vCPU に載る | (c) 宛先の変更が容易 | (d) JVM が少ない | (e) 先行研究との比較 | 総合 |
|---|---|---|---|---|---|---|
| **Hotel Reservation** | ○ 4 型の比がコードにある。search と recommend は通るサービスが違う。reserve は書き込み。**反応の向きが違うかは実測が要る** (read 系が 99%) | ◎ [推測] | △ Consul 経由。ただしポートは別、Go ソースは自由に改変可 | ◎ 全て Go | ◎ HPA 系 5 本 (Sinan, FIRM, PEMA, Autothrottle, StatuScale) | **第 1 候補** |
| **OpenTelemetry Demo** | ○ 重み付き Locust。購入 (checkout) と閲覧 (browse_product) が分かれる | △ 観測基盤が重い [推測] | ◎ `*_ADDR` 環境変数、ポートは別 | △ JVM 系 3 つ (うち recommendation は閲覧経路上＝閲覧型の CPU に JVM の起動・暖機が混ざりうる) | × HPA 論文で見つからず | **第 2 候補** |
| **TeaStore** | ◎ 公式に browse／buy の 2 プロファイル | ○ [推測] | × ポート 8080 固定・registry。イメージ作り直し要 | × 全て Java | ○ 2 本 (性能工学の標準) | **第 3 候補**。(d) を受け入れる場合のみ |
| Train-Ticket | ○ 多シナリオ | × [推測] | 不明 | × | ◎ 6 本 | 非推奨 |
| Bookinfo | × 実質 1 型 | ◎ | ○ (Istio 前提の HTTP) | △ reviews が Java | ○ 2 本 | 非推奨 (4 サービスで同居の組合せが少ない) |
| Social Network | ○ 3 型 | △ 36 サービス | △ Thrift | ○ C++ | ◎ 5 本 | 非推奨 (通信方式が違い過ぎる) |

**推薦の理由 (第 1 候補)**: 本研究の主張は「配合を変えたとき、同居の相手によって台数の入れ替わりが起きる」なので、(a) の**反応の向きの違い**が最重要。Hotel Reservation は型ごとに通るサービスが分かれる点で OB／SS と同様の構造を作れる見込みだが、**4 型のうち 3 つが読み取り系で、「購入型 vs 閲覧型」のようにきれいな 2 群になるかは実測するまで分からない** (推測)。
(d) は Go のみで JVM 問題が出ない。(e) は DSB が最も引用される OSS の 1 つ (Gan ほか ASPLOS'19、bib `gan2019dsb`)。(c) は Consul のため一手間 (Consul の宛先が localhost になるよう登録をいじる、または宛先文字列を直して再ビルド)。
**TeaStore が (a) で最良なのに第 3 候補な理由**: Java 6 本で、ユーザが §12 で調べた起動時 CPU の暴走をそのまま招く。readiness を遅らせて回避する前提なら選べる。

### 13.6 検索の記録 (2026-11-10)

- WebSearch (standard): "Kubernetes HPA microservices autoscaling evaluation benchmark applications Online Boutique Sock Shop TeaStore Train-Ticket DeathStarBench" (ScalerEval、DeepScaler、Dashtbani、Smart HPA、PBScaler、BASE、MS-RA、STaleX が出た)／"microservice autoscaling survey benchmark applications used in evaluation Train-Ticket Hotel Reservation Social Network HPA comparison" (PEMA、Survey が出た)／"TeaStore Kubernetes Horizontal Pod Autoscaler evaluation autoscaler microservice benchmark paper" (**TeaStore と HPA の査読論文は、これでは出ず**。TeaStore の GitHub README の「使われた論文」一覧から Goli／Horn を拾った)／"Horn Fard Wolf Multi-objective Hybrid Autoscaling ... TeaStore"／"Goli Mahmoudi Khazaei Ardakanian Holistic ML-based Autoscaling TeaStore HPA"／"Kubernetes autoscaling microservices evaluation Acme Air OR Robot Shop OR OpenTelemetry Demo horizontal pod autoscaler paper" (**Acme Air・Robot Shop・OTel Demo を評価に使う HPA 論文は出ず**。Buzato & Goldman IJNC 2026 が出た)／GRAF／SHOWAR／Erms。
- arXiv API (id_list) でメタデータ、Crossref API で DOI・巻号ページを確認 (PBScaler、StatuScale、GRAF、Smart HPA、DeepScaler、ScalerEval、IJNC)。arXiv の全文検索クエリは機能しなかった (多くの語で 0 件)。
- 原典取得: arXiv PDF (2112.14845、2008.08509、2309.00859、2303.14620、2202.00057、2403.07909、2506.05693、2403.08798、2407.10173、2501.18734、2504.08308、2510.02585、2402.12962)、USENIX (Autothrottle)、Cornell 著者サイト (Sinan、DSB)、York 大／SciTePress (Goli)、KAUST の授業ページ (GRAF、**途中で切れたダウンロード**)、J-STAGE (IJNC、24 頁)。
- **取れなかった**: SHOWAR (par.nsf.gov の PDF が壊れていた)、Horn ほか (TU Darmstadt のサーバに接続不可)、Erms の本文 (§6.3.4 のまま abstract のみ)。
- GitHub: API (リポジトリ情報・最終 commit・ライセンス・ツリー)、raw (README、server.go、dialer.go、config.json、.env、locustfile.py、*.lua、server.xml、start.sh、manifest)。
- **空白の根拠 (限定付き)**: 「OTel Demo を HPA 論文で評価に使った例」「Acme Air／Robot Shop を HPA 論文で評価に使った例」は、**WebSearch の上記クエリでは出なかった**。Google Scholar・IEEE Xplore・ACM DL の直接検索はしていないので、存在しないとは断定しない。
- 注意: 検索ツールが返す要約文は、原典と食い違うことがあった (BASE の要約は benchmark 名を述べたが、取得した arXiv v2 の本文には出ない)。今回の表は原典で確認できたものだけを載せた。

### 13.7 次に読む／次にやること (優先順)

1. **Buzato & Goldman IJNC 2026 の §5.2〜§6 (CPU・コストの結果と相関分析) と Fig. 12 (決定木)** を図まで見る — pdftotext では図の中身が見えない。「変動が大きい負荷では modular が良い」の根拠が測定か意見かを確かめ、Related Work の差分の文を確定する。IPDPS 2025 の会議版 (同論文 [3]) の書誌も未確認。
2. **Hotel Reservation を 1 台に載せて、型ごとの CPU を測る (実機で)** — search／recommend／reserve を単独で流して各サービスの CPU が型ごとにどう動くか (ρ の「向き」が分かれるか)。これで第 1 候補の (a) が確定する。※実験はユーザが起動する。
3. **Hotel Reservation の Consul 経由の宛先を、同居 Pod でどうするか** — `consul://` の登録アドレスを Pod IP のままにして同一 Pod 内の自己宛が loopback に落ちるか、宛先文字列を `localhost:ポート` に直すか。ソース改変の量を見積もる。
4. **OTel Demo のサービスごとの言語と、1 台でのメモリ** — 条件 (b) と (d) の確認 (今回は `src/` の一覧のみ)。
5. SHOWAR (SoCC '21) と Erms (ASPLOS '23) の本文 — どのアプリを使ったか (今回は取得できず)。

### 13.8 DeathStarBench Hotel Reservation (HR) を評価に使った 5 本の精読 (2026-11-12、依頼: 3 つ目のアプリ候補 HR の参考)

**範囲**: §13.1 の表で grep 済みだった #2 FIRM、#3 Sinan、#4 Autothrottle、#5 PEMA、#15 StatuScale を、HR に関わる節 (評価環境・負荷・結果・付録) を中心に読んだ。**全文精読ではない** (ML モデルの中身や他アプリの節は読んでいない)。pdftotext 後のテキストを grep して該当節を読む方式。図の中身 (数値の棒グラフ) は読めていない。
**取得元**: FIRM = arXiv 2008.08509、Sinan = Cornell 著者サイトの PDF (ASPLOS 版、ページ 167–181)、PEMA = arXiv 2202.00057、Autothrottle = USENIX の PDF (NSDI '24)、StatuScale = arXiv 2407.10173 **v1 (2024-07-14)**。StatuScale の TAAS 公刊版 (DOI 10.1145/3686253) は v1 と同一とは限らない (未照合)。
**先に結論**: 5 本とも **HR は『オートスケーラ／資源配分器の評価対象』であり、同居 (co-location) や Pod 内の束ね方を変数にした論文は無い**。したがって本研究の主張とは**衝突しない**。HR の配合を数値で書いたのは Autothrottle だけ (Appendix A: Search 60%／Recommend 39%／Reserve 0.5%／Login 0.5%)。

| # | 論文 (bib key) | 解く問題 | 手法 (水平/垂直、ML/規則、単位) | HR の使い方 | 主な数値 | 本研究との関係 | 確認度 |
|---|---|---|---|---|---|---|---|
| 1 | Qiu ほか FIRM, OSDI '20 (`qiu2020firm`) | SLO 違反の原因となる『クリティカルパス上の犯人サービス』を見つけ、その資源 (CPU 上限・メモリ帯域など) を細かく調整する | **垂直** (サービスごとの資源の上限を RL で調整)。SVM で犯人特定 + 強化学習。単位 = 個々のコンテナ | DSB の SN・MM・**HR (15 サービス)** と TT (41) の 4 つ。K8s、15 台の 2 ソケット物理ノード (56〜192 コア)、anti-colocation 規則なし。wrk2 の**開ループ**、**全リクエスト型を一様に**生成。HR の配合は『一様』としか書かれない | SLO 違反を K8s autoscaling 比で最大 16×、AIMD 比で 9× 減らし、要求 CPU 上限を最大 62% (29〜62%) 減 (Abstract、§4)。HR 単体の数値は図のため未確認 | **背景**。基準は K8s autoscaling と AIMD で、同居ではない。ただし『性能干渉を注入して犯人を見つける』ので、同居の損 (干渉) の議論の背景になる | ★本文 (§4.1 評価環境を読了、他は grep) |
| 2 | Zhang ほか Sinan, ASPLOS '21 (`zhang2021sinan`) | 依存するサービス間の連鎖的な SLO 違反を避けつつ、サービスごとの CPU を最小にする | **垂直** (サービスごとの CPU 配分を 10%/30% 刻みで増減)。CNN + 決定木の ML (サービスごとの短期予測 + 長期予測)。単位 = サービス (tier) | DSB の SN と **HR** (Go、gRPC、memcached + MongoDB。DB は 80 ホテル・500 ユーザ)。**Docker Swarm** (K8s ではない)、80 コア × 4 台のローカル + GCE。Locust、ユーザ数を 9 段階に増やす (ユーザ 1 人あたり平均 1 RPS のポアソン到着)。QoS = p99 200 ms。HR の配合は本文に見つからず (**未確認**。Social Network の配合だけ別の図で変える) | HR: Sinan と AutoScaleCons のみ QoS を常に満たし、Sinan は CPU 使用を平均 25.9%・最大 46.0% 減 (§5.3 の Fig. 11 の説明)。AutoScaleOpt は 1900 ユーザまでしか QoS を満たさない | **背景**。基準の autoscale は『使用率 [60,70)% で +10%、[70,100]% で +30%』という**垂直**の規則 (Swarm)。台数は変えず、同居も扱わない | ★本文 (§2.2.1、§5.1、§5.3 を読了) |
| 3 | Hossen, Islam, Ahmed PEMA, HPDC '22 (`hossen2022`) | 人手の探索や ML の学習データ無しで、SLO を保ったまま資源を減らす道筋を見つける | **垂直** (CPU を 0.1 コア単位で減らす、フィードバック制御。規則の勾配降下に近い)。ML 無し。単位 = 全サービスの CPU 配分、2 分間隔 | TT (41)・SS (13)・**HR (18 サービス)** (全て Go・gRPC、80 ホテル・500 ユーザ)。K8s、master 1 + worker 4 (2×10 コア Xeon、128 GB)。**SLO は HR だけ 50 ms** (TT 900 ms、SS 250 ms)。更新は 2 分間隔。負荷は RPS を直接指定 (ツール名・リクエスト型の配合は本文に無し) | PEMA は OPTM (網羅探索の最適) にほぼ一致し、RULE (K8s の規則) より最大 33% (SS の高負荷) 少ない資源 (§4.1 の Fig. 15)。HR 単独の数値は図のため未確認 | **背景**。基準は RULE (K8s の規則ベース) と OPTM。限界の節に『垂直と水平の得失の比較はしない』と書く (原文: "does not explicitly address the impacts and trade-offs among vertical ... and horizontal ... resource scaling") | ★本文 (§1、§2.1、§4 冒頭、限界を読了) |
| 4 | Wang ほか Autothrottle, NSDI '24 (`wang2024autothrottle`) | SLO を満たす最小の CPU を、アプリ全体の『目標 (throttle target)』とサービス単位の局所制御の 2 階層で決める | **垂直** (サービスごとの CPU 上限を Linux cgroup で制御)。局所 = 規則 (Captain)、全体 = 軽い RL (Tower、Vowpal Wabbit)。水平 (台数) は未対応と明記 (§6 で今後の課題)。単位 = サービス群 (CPU 使用率の k-means で 2 群) | TT (68)・**HR (17 サービス、各 1 レプリカ)**・SN (28)。K8s + Docker、160 コア (Azure VM 32 コア × 5) と 512 コア (物理)。Locust (トレースを再生)、**HR は Search 60%／Recommend 39%／Reserve 0.5%／Login 0.5% の固定配合** (Appendix A)。トレースは diurnal／constant／noisy／bursty の 4 種。SLO = p99 100 ms (HR)。ウォームアップに 200 RPS を 15 秒 + 60 秒待つ (Appendix G) | CPU 節約 (対 最良の基準): TT 最大 26.21%、SN 最大 25.93%、**HR 最大 7.34%** (Abstract、Table 1)。HR で効果が小さい理由は『要求が平均 3 サービスしか通らず単純なため』(§5.2) | **背景**。基準は K8s-CPU／K8s-CPU-Fast (使用率しきい値を 0.1〜0.9 で手動探索) と Sinan。配合は一定にすると明記 (§3.2 付近、原文: "our focus in this work remains on constant workload composition ... following the setup in prior work") = 配合を振る本研究の位置づけの根拠 | ★本文 (§5.1、5.2、付録 A・F・G を読了、§3.2 は grep) |
| 5 | Wen ほか StatuScale, ACM TAAS 20(1) 2025 (`wen2025statuscale`) | 突発的な負荷の急増 (バースト) を検出し、垂直と水平を使い分けて応答時間を保つ | **垂直 + 水平の両方**。負荷状態の検出 (抵抗線／支持線) で垂直スケール、複数指標の評価で水平 (レプリカ数)。PID 制御 + LightGBM 系。20 秒間隔。単位 = サービス | SS (8 サービス) と **HR** (user・reservation・search・recommendation・profile などと記述、サービス総数は本文に見つからず)。K8s、master 1 + worker 2 (各 4 コア・4 GB の VM、CentOS 7)。Locust + Alibaba cluster-trace-v2018 の CPU 使用率を負荷の形に写す (リクエスト型の配合は書かれず) | 平均応答時間: SS で 8.59〜12.34%、**HR で 7.30〜11.97%** 改善 (Abstract)。HR の p99 では GBMScaler 比 12.87%、Showar 比 4.13%、Hyscale 比 12.26% (§4.4)。SLO 200／250 ms で違反数を比較 | **背景**。基準は GBMScaler・Showar (自前再実装)・Hyscale で、**K8s HPA そのものは基準に入っていない** (原文は『Hyscale は K8s の autoscaler と似た考え方』と説明するのみ)。同居は扱わない | ★本文は arXiv v1 の §4 を読んだ (公刊版との同一性は未照合) |

**5 本に共通する読み取り**:
1. 5 本とも **K8s HPA (台数) を直接の基準にしていない or していても HR の主結果ではない**。主戦場は『サービスごとの CPU 量 (垂直)』。FIRM の基準は K8s autoscaling (種別は未確認)。**HPA の台数が Deployment 単位で決まることによる粒度の問題 (本研究の主張) を扱った論文は 5 本の中に無い**。
2. **HR を『小さな負荷で効果が出にくいアプリ』と書いたのは Autothrottle** (要求が平均 3 サービスしか通らない)。PEMA は HR だけ SLO を 50 ms と厳しく置く。**HR は 1 リクエストあたりのホップ数が少ない = 通信コストの比率が相対的に小さい可能性があるが、これは本研究の測定が要る (推測)**。
3. **配合**: 明記は Autothrottle の Search 60／Recommend 39／Reserve 0.5／Login 0.5 のみ。FIRM は『一様』、Sinan・PEMA・StatuScale の HR は配合が本文から見つからず (読んだ範囲)。DSB の wrk2 の既定スクリプトの配合は本節では未確認 (§13.3 の『配合の既定値がコードにある』と整合するかは、DSB リポジトリで要確認)。
4. **HR のサービス数の数え方が論文でばらつく**: FIRM 15、Autothrottle 17、PEMA 18 (バックエンドの memcached・MongoDB を含めるかの違いと推測。**未確認**)。本研究で『HR は N サービス』と書くときは、どの数え方か (DB・cache を含むか) を明記すること。
5. レプリカ数を明記したのは Autothrottle だけ (Appendix D: HR は各サービス 1 レプリカ)。他 4 本は読んだ範囲で未確認。

**HR を同居実験に使うなら参考になること**:
1. **計測の入口は Search と Recommend の 2 型**: 既定配合では Search 60% + Recommend 39% で 99%。Reserve と Login は各 0.5% で、Reserve は予約の書き込みを伴うはずだが (一般知識で、5 本の本文では未確認)、既定配合では 1% 未満なので HR は読み取り主体。本研究の buy／view に対応させるなら『view = Search/Recommend、buy = Reserve (+ Login)』が自然だが、**Reserve の比率を上げた配合 (既定は 0.5%) は 5 本のどれにも見つからなかった**ので、配合の軸は本研究が自分で定義することになる (WebSearch／本文 grep の範囲)。
2. **HR は通過サービス数が少ない**: Autothrottle は『平均 3 サービス』と書く。FIRM・Sinan の図 (Sinan Fig. 1 の tier 名: Frontend の下に Search／Recommend／Reserve／User、その下に Geo／Rate／Profile と memcached・MongoDB) から見て、浅い 3 層構造に見える (図の矢印の向きまでは未確認)。**同居で通信が減る便益は小さい (OB の checkout のようなファンアウトが無い) 可能性**があり、ρ (必要台数の比) の向きは型ごとに実測が要る。
3. **起動の軽さ**: 全て Go・gRPC (Sinan §2.2.1、PEMA §2.1)。Sock Shop で問題になった JVM 起動 CPU は無い。memcached と MongoDB は別 Pod にして同居の対象外にできる (Sinan Fig. 1 の『Caching & DB』層と『Business logic』層の区別が使える)。
4. **ウォームアップの先例**: Autothrottle は HR に 200 RPS を 15 秒送り 60 秒待つ (Appendix G)。本研究の窓の取り方の根拠に引用できる (ただし K8s の HPA 前提ではない)。
5. **SLO の置き方が論文でばらつく** (Sinan 200 ms／Autothrottle 100 ms／PEMA 50 ms／StatuScale 200・250 ms)。本研究は SLO を使わず取りこぼしと softirq/req を見るので、SLO を決める必要は無いが、『HR は p99 50〜200 ms 級の軽いアプリ』という共通認識は使える。
6. **宛先の変更**: 5 本とも HR の宛先を改変していない (読んだ範囲)。§13.7 の第 3 項 (Consul 経由の宛先の扱い) は 5 本からは分からない → 引き続き TODO。

**位置関係の判定 (5 本とも)**: 衝突なし。いずれも**背景** (A〜D 群の『オートスケール・資源配分』群。同居は扱わない)。
**検索の記録**: 検索はしていない (§13.6 の検索で既に拾った 5 本の PDF の再取得と精読のみ)。FIRM = arXiv 2008.08509、PEMA = arXiv 2202.00057、StatuScale = arXiv 2407.10173、Autothrottle と Sinan = §13.6 で取得済みの PDF。
**未確認**: Sinan／PEMA／StatuScale の HR の配合、FIRM の HR 単体の数値、PEMA の Fig. 15(c)・Autothrottle の HR の Table 1 の個別値 (pdftotext で表が崩れていた)、StatuScale の TAAS 公刊版との差。


### 13.9 HR を評価に使い、かつ水平スケール (レプリカ数・Pod 数の増減。HPA を含む) を扱う論文の探索 (2026-11-12、依頼: HR を 3 つ目のアプリにする際の先行例)

**先に結論 (「無い」と断定はしない。範囲は検索の記録を参照)**:
1. **本文で『HR を使った』と『水平スケール (レプリカ数を増減)』の両方を確認できた論文は、StatuScale (§13.8 #5) の 1 本だけ**。ただし StatuScale の基準に K8s HPA は入っていない。
2. **Erms (ASPLOS '23)** は HR を使い、コンテナ数を決める (水平寄り) と読める。ただし確認の根拠は**著者公開の artifact README** (リポジトリ) と Crossref の書誌までで、**論文本文は ACM が 403 で取得できず未読**。表では『準確認』とする。
3. **HR を使うが垂直のみ**: FIRM・Sinan・PEMA・Autothrottle (§13.8)、**Nodens (ATC '23)**、**SurgeGuard (SC '24)**、**Reclaimer (arXiv 2023)**。
4. **HR を使っていない (本文 grep 0 件)**: SHOWAR、COLA、PBScaler、DeepScaler、Smart HPA、Graph-PHPA、Ursa、AWARE、ARBITER、Morphis、SLO-Scaler、ADASCALE、LSRAM、STaleX、MAS-H2、NimbusGuard。GRAF と ScalerEval は §13.1 の既存確認 (OB/SN と OB/SS) のまま。
5. **『HR で K8s HPA を比較相手にした水平スケール論文』は、今回の範囲では見つからなかった。** **(2026-11-12 訂正: §13.10 で、HR と SN の上で HPA を土台にした自作 autoscaler を作り、HPA のしきい値・requests・limits を掃引した `shetty2025cpulimits` (SoCC '25) を見つけた。HR × HPA の先行例は 1 本ある。ただし焦点は limits で、水平スケールの粒度や同居ではない。)** 本研究と衝突する (同居・Pod 内の束ね方を変数にした) 論文も無い。
6. **本研究に最も近いのは Nodens (配合の振り方)** と **COLA の一節 (DeathStarBench が水平スケールの評価に向かない理由)**。どちらも衝突はしない。下の『本研究との関係』を参照。

**用語 (初学者向け)**: 水平スケール = 同じサービスの Pod (コピー) の台数を増減する。垂直スケール = 1 つの Pod／コンテナに割り当てる CPU の量を増減する。K8s HPA は水平 (Deployment の replicas を変える)。

#### 13.9.1 結果の表

凡例: 「HR 本文」= HR を評価に使ったことを論文本文 (または著者公開物) で確認したか。「水平」= レプリカ数・コンテナ数を変える手法か。★ = 原典 PDF の本文で確認 (pdftotext → grep、該当節を読んだ。全文精読ではない)。

| # | 論文 (bib key) | HR 本文 | 水平 | 水平の扱い・基準 | HR の使い方 | 確認度 | 本研究との関係 |
|---|---|---|---|---|---|---|---|
| 1 | Wen ほか StatuScale (TAAS 2025、`wen2025statuscale`) | ○ | ○ (垂直と併用) | 自前。基準は GBMScaler・Showar・Hyscale で **HPA は含まない** (§13.8) | SS と HR、K8s (master 1 + worker 2)、Locust + Alibaba トレース | ★arXiv v1 (§13.8) | 背景 (水平あり、HPA 基準なし) |
| 2 | Luo ほか Erms (ASPLOS '23、`luo2023erms`) | ○ (著者 README) | ○ (コンテナ数を決める) と読める | 『Online Scaling determines how many containers are allocated to each microservice』(README)。基準は本文未読で**不明** | DSB の SN・MM・HR の 3 つ、K8s、Jaeger + Prometheus、wrk2、テスト用ノード 4 台以上 | **本文未読**。README と Crossref まで | 背景 (共有サービスの優先度制御。同居の可否は変数でない)。本文を読むまで確定しない |
| 3 | Shi ほか Nodens (USENIX ATC '23、`shi2023nodens`) | ○ ★ | × (垂直 + 移動) | cgroup で CPU 量を変える、足りなければサービスを別サーバへ移す。基準は FIRM と ELIS | **改変 HR** (5 種の呼び出しグラフ = 5 種の問い合わせ型)。K8s v1.20.4、8 ノード | ★本文 (§3.2、§3.3、§5〜 の該当箇所を grep で読んだ) | 背景。**配合を振った先例** (下記) |
| 4 | Ghosh, Yadwadkar, Erez SurgeGuard (SC '24、`ghosh2024surgeguard`) | ○ ★ | × (コア数の割り当て) | 水平は『今後の課題的な言及』のみ | SN と HR (各 2 アクション)、wrk2 開ループ、K8s の記述なし | ★本文 (評価の節と artifact) | 背景 |
| 5 | Fettes, Karanth, Bunescu Reclaimer (arXiv:2304.07941、`fettes2023reclaimer`) | ○ ★ (HR 15 サービス) | × (`docker update --cpus`) | AutoScale (AWS 型の規則) と Sinan が基準 | 評価は Social Media と HR の 2 つ、Locust (Sinan と同じスクリプト)、**単一サーバ・K8s ではない** | ★本文 | 背景 (単一サーバだが垂直) |
| 6 | Alghadban ほか DriftGuard-SLA (Computation 14(10) 229、2026、`alghadban2026driftguard`) | ○ (Crossref の abstract) | **未確認** | 検索エンジンの要約は『K3s、HPA の CPU 目標 150 ミリコア、1〜2 レプリカ』と書いたが**本文を取得できず裏が取れていない** | HR、K8s。目的は故障後の回復 (予測トリガの自己修復) で、スケールの評価ではない可能性が高い | **abstract のみ** (MDPI が 403) | 背景 (要読。HPA を条件に置いたなら『HR で HPA が動く』先例) |
| 7 | Qiu ほか FIRM / Zhang ほか Sinan / Hossen ほか PEMA / Wang ほか Autothrottle | ○ | × (垂直) | §13.8 | §13.8 | ★ (§13.8) | 背景 |

**HR を使っていないことを本文 grep で確認したもの** (grep = 'hotel' が 0 件。pdftotext 後。2026-11-12): SHOWAR (SN・TT・OB。par.nsf.gov purl/10400291)、COLA (arXiv v3。後述の一節あり)、PBScaler (arXiv:2303.14620)、DeepScaler (arXiv:2309.00859)、Smart HPA (arXiv:2403.07909)、Graph-PHPA (arXiv:2209.02551。Bookinfo)、Ursa (HPCA '24、arXiv:2401.02920。SN・Media 等)、AWARE (USENIX ATC '23)、ARBITER (arXiv:2607.19182)、Morphis (arXiv:2602.01044。TrainTicket)、SLO-Scaler (arXiv:2608.18390。SN)、ADASCALE (arXiv:2607.15681)、LSRAM (arXiv:2411.11493)、STaleX (arXiv:2501.18734)、MAS-H2 (arXiv:2603.07607)、NimbusGuard (arXiv:2604.11017)。
**取得できず未確認**: GRAF (CoNEXT '21。OA の PDF なし。§13.1 の部分 PDF では SN・OB)、Derm (ISCA '24、DOI 10.1109/ISCA59077.2024.00039。OA なし。Erms と同じ著者グループなので HR を使う可能性はあるが**推測**)、ScalerEval (§13.1 のとおり OB・SS)。

- **追記 (2026-11-14)**: **Cilantro** (Bhardwaj ほか、OSDI '23、`bhardwaj2023cilantro`) も HR を使い、**レプリカ数を増減する水平スケール**だった (原典 PDF §6「we horizontally scale the workloads by adding more replicas to their Kubernetes deployment」)。上の結論 1『HR と水平の両方を本文で確認できたのは StatuScale だけ』は 2 本に直る。ただし HPA は基準に入っていない (基準は Resource-Fair・EvoAlg・ε-greedy)。詳細は §9.24。

#### 13.9.2 論文ごとのカード

**(a) Erms — Luo, Xu, Ye, Xu, Zhang, He, Yang, Xu. ASPLOS '23 (Proc. 28th ASPLOS Vol. 1), pp. 62–77, DOI 10.1145/3567955.3567964 (Crossref で確認)。journal 版 = ACM TOCS 42(1–2) 1–28, DOI 10.1145/3631607 "Optimizing Resource Management for Shared Microservices: A Scalable System Design" (Crossref で確認)。**
- 確認度: **本文未読** (dl.acm.org が 403、Unpaywall の Zenodo 7133267 は 160 MB の artifact tar で PDF ではない)。確認したのは (i) 著者公開リポジトリ github.com/Cloud-and-Distributed-Systems/Erms の README、(ii) 検索で得た TOCS の abstract の要約、(iii) Crossref の書誌。**引用前に本文を読むこと。**
- 何をする研究か: 複数のオンラインサービスが同じマイクロサービスを共有する環境で、SLA (遅延の約束) を満たす最小の資源を決める。遅延を『負荷・コンテナ数・干渉』の区分線形関数で近似し、共有サービスでは優先度付きのスケジューリングをする。
- 水平の扱い: README の原文 "Online Scaling determines how many containers are allocated to each microservices" (README、確認 2026-11-12)。= サービスごとのコンテナ数を決める手法。abstract の要約は『コンテナ数を最大 1.6 倍、SLA 違反確率を 5 倍減らす』(TOCS 版)。**基準 (比較相手) は本文未読のため不明。HPA を含むかも不明。**
- HR の使い方: README 原文 "We evaluate Erms using DeathStarBench, including three applications, Social Network, Media Services and Hotel Reservation."。K8s 上、Jaeger と Prometheus で計測、wrk2 同梱。配合・負荷は静的負荷 (約 6 時間) と動的負荷 (約 20 時間) のスクリプト。
- 本研究との関係: **背景 (暫定)**。共有サービスのスケール (水平) は扱うが、『同居による HPA の粒度の変化』は扱わない見込み。ただし本文未読なので**『衝突なし』は暫定**。

**(b) Nodens — Shi, Zhang, Tong, Chen, Fu, Guo. USENIX ATC '23. URL https://www.usenix.org/conference/atc23/presentation/shi (citation メタデータで著者確認)。**
- 確認度: ★原典 PDF (usenix.org の PDF を pdftotext→grep で該当箇所を読んだ)。
- 何をする研究か: 負荷や呼び出しグラフが急に変わった後、QoS (遅延の約束) を回復するまでの時間を短くする。ネットワーク通信量から各サービスの負荷を見積もる。
- 水平の扱い: **水平ではない**。原文『Nodens uses Linux cgroups to adjust CPU resources』『VPA in Kubernetes also supports in-place pod vertical scaling』。足りなければ負荷の低いサーバへ**サービスを移動 (migrate)** する。基準は FIRM と ELIS (ベイズ最適化) で、HPA ではない。related work では SHOWAR・PEMA・ATOM を『水平または垂直のヒューリスティクス』と一括して述べるのみ。
- HR の使い方: 『HR ベンチマークは広く使われる HotelReservation を**改変**したもの。5 種の呼び出しグラフ (最寄りホテル検索、評価最高検索、最安推薦、総合推薦、予約) に対応する』(§3.2)。実験は 3 台の K8s、拡張評価は 8 ノード (E5-2630 v4、K8s v1.20.4)。負荷ツール名は grep で見つからず**未確認**。
- **配合を振る**: 『1.5X(2:1:2:1:4) = 負荷が 1.5 倍になり、5 種の呼び出しグラフの比率が 2/10、1/10、2/10、1/10、4/10 に変わる』(§3.3)。基準状態は 1X(2:2:2:2:2)。= **HR で型の比率を振った先例**。§13.8 では『HR の配合を振った論文は 5 本に無い』としたが、**Nodens がそれを覆す** (§13.8 の該当文は『5 本の中には無い』と範囲を限っていたので矛盾はしない)。ただし Nodens の HR は改変版で、**振った目的は QoS 回復時間の測定**であり、必要台数 (ρ) の比の変化を見る本研究とは目的が違う。
- 本研究との関係: **背景**。配合 (呼び出しグラフの比率) を振る根拠として引用できる。同居は扱わない。

**(c) SurgeGuard — Ghosh, Yadwadkar, Erez. "Fast and Efficient Scaling for Microservices with SurgeGuard". SC '24 (SC24: Int. Conf. for High Performance Computing, Networking, Storage and Analysis), pp. 1–15, DOI 10.1109/SC41406.2024.00103 (Crossref で確認)。**
- 確認度: ★本文の一部 (par.nsf.gov purl/10632610 の PDF は本文の途中から始まり、評価の節と artifact 付録を grep で読んだ。冒頭の問題設定・基準の詳細は未読)。
- 水平の扱い: 垂直 (コンテナへのコア数の割り当て。1 回に 1 コアずつ)。原文『we expect the ability of SurgeGuard to better tolerate surges to also benefit horizontal-scaling controllers, by managing QoS ... while the autoscaler launches a new container』= 水平は未対応で、併用の可能性に触れるのみ。基準は Parties と Caladan。
- HR の使い方: SN と HR (各 2 アクション)。wrk2 の開ループ (自前改変のスパイク付き)。K8s の記述は読んだ範囲で参考文献のみ。
- 本研究との関係: **背景** (HR を使う垂直制御の一例)。

**(d) Reclaimer — Fettes, Karanth, Bunescu. arXiv:2304.07941 (2023-04-17)、ACM 形式の原稿。掲載先は未確認。**
- 確認度: ★arXiv の本文 (評価の節、基準、環境を読んだ)。
- 水平の扱い: **水平ではない**。単一サーバ上で `docker update --cpus=core_allocation` によりサービスごとの CPU コア数を RL で決める。基準は AutoScale (AWS 型。使用率 [30,50)% で +10%、[50,100]% で +30% など、CPU 割り当ての増減) と Sinan。
- HR の使い方: 『HR は 15 マイクロサービス』『Locust のスクリプトは Sinan 公開のものと同一』『HR は 500〜3500 ユーザで学習・試験』。結果: HR で平均 CPU 割り当てを Sinan 比 27.5%、AutoScale 比 38.4% 削減、HR は全手法で QoS 違反 0 (評価の節、§4 付近。節番号は pdftotext の並びからの推定)。
- 本研究との関係: **背景**。K8s でも水平でもない。

**(e) DriftGuard-SLA — Alghadban, Ghoneim, Alshemaimri. Computation 14(10), 229 (2026-09-28)、DOI 10.3390/computation14100229 (Crossref で確認)。**
- 確認度: **abstract のみ** (Crossref の abstract)。MDPI の本文は 403。
- abstract の記述: 『K8s ベースの DeathStarBench Hotel Reservation に対する有界な制御器』『350 回の実験 (70 組の対照ブロック × 5 方針 × 6 種の故障と故障なし)』。結論は『予測トリガの優位は確定せず、コスト削減や一般化は主張できない』。
- 水平の扱い: **未確認**。検索エンジンの要約は『HPA の CPU 目標 150 ミリコア、1〜2 レプリカ』と述べたが、**一次資料で確認していない**ので記録のみ。故障回復の研究で、スケールの効率を測る研究ではない可能性が高い。
- 本研究との関係: **背景 (暫定)**。HR を K8s と HPA で動かした先例になるかは、本文を取得して確認すること。

#### 13.9.3 COLA の一節: DeathStarBench を水平スケールの評価に使わなかった理由 (★arXiv:2112.14845 v3 の本文、確認 2026-11-12。評価の節の Microservice Applications の段落)

原文: "We considered using the popular DeathStarBench opensource benchmark suite [13]. While DeathStarBench has been used for vertical autoscaling evaluations [43, 56, 57], where the fraction of utilized CPU is scaled up/down, we find it is ill-suited to the horizontal+cluster autoscaling at the heart of COLA. First, DeathStarBench applications fix both the number of deployed VMs and the assignment of each microservice to these deployed VMs. ... Second, the benchmark applications require a startup script to be invoked on each VM to add data, code, and libraries to the VM. ... Both shortcomings could be fixed with sufficient engineering, but we found it easier to use other applications instead."
- 読み取り: (i) **DSB (HR を含む) が垂直の評価に偏って使われる**という見立ては、本研究の検索結果 (HR を使う 6 本のうち水平は StatuScale のみ) と整合する。(ii) 理由は『VM の台数とサービスの割り当てが固定』『各 VM に起動スクリプトが必要』で、**クラスタオートスケーラ (VM の台数) を含む評価の話**。**単一ノードで Pod 数を増減する本研究には当てはまらない**。(iii) ただし『起動時にデータを入れる』点は、HR のレプリカ増加時の注意につながる (次項)。

#### 13.9.4 HR をレプリカ増減で使うときの実務上の注意 (学術論文ではない。GitHub の PR。内容は裏取りしていない)

youngmin-kaist/DeathStarBench の PR #1 "hotelReservation: benchmark patch set (rate query fix, consul deregister, idempotent seeding, ambient L7 support)" (https://github.com/youngmin-kaist/DeathStarBench/pull/1 。フォークの PR で、アップストリームに取り込まれたかは**未確認**。確認 2026-11-12、WebFetch の要約のみ)。
- `GetRates` が空の Mongo フィルタで全件走査し、`/hotels` の上限が 4,143 RPS から 13,421 RPS になったという主張 (16 コアのノード)。PR の説明は『rate／reservation のレプリカ増加を有効にする』と書く。
- Pod が消えても consul から登録が消えない (SIGTERM で deregister していない) → **Pod を入れ替えるたびに古い宛先が残る**。
- 起動のたびに初期データを再投入するので、レプリカや再起動で重複する (約 10〜11 倍と主張)。
- → 本研究で HR を HPA でスケールさせるなら、(i) consul の登録が Pod の増減に追随するか、(ii) 初期データの重複、(iii) 宛先解決 (§13.7 第 3 項の Consul の件) を**事前に点検する価値がある**。これは先行研究ではなく、実機で確かめるべき TODO。

#### 13.9.5 本研究との位置関係の判定

- 衝突 (既出): **無し**。同居・Pod 内の束ね方・HPA の粒度を変数にした HR の論文は、今回の範囲で見つからなかった。
- 相補: 無し (近い問題設定は無い)。
- 背景: StatuScale、Erms (暫定)、Nodens、SurgeGuard、Reclaimer、DriftGuard-SLA (暫定)、FIRM、Sinan、PEMA、Autothrottle。
- 無関係 (混同注意): Avritzer ほかの JSS 2026 (Trubiani 共著、HR を含む多数のアプリで『アーキテクチャの複雑さと性能・スケーラビリティ』を測る。オートスケーラの研究ではない。本文 grep で HR 17 件)。arXiv API の全文検索は abstract しか引かないので、HR の検索には向かない。

**最も近い論文**: 水平 + HR の本文確認ができたのは StatuScale だけ (HPA は基準外)。**配合を振る観点では Nodens**。**『HPA 下で Deployment 単位の粒度を扱う』観点では Buzato & Goldman (§13.4、SS の話)** のままで、HR 側に相当する論文は見つからなかった。

#### 13.9.6 検索の記録 (2026-11-12)

- WebSearch (standard): "hotel reservation DeathStarBench horizontal autoscaling replicas Kubernetes HPA microservices" (HR 専用の論文は出ず、Smart HPA・COLA が出た)、"Erms ... ASPLOS 2023 DeathStarBench"、"SHOWAR ..."、"Nodens microservice autoscaling DeathStarBench hotel reservation workload prediction replicas"、"Graph-PHPA ..."、"AWARE ... ATC 2023"、"Derm SLA-aware ..."、"hotelReservation microservices dynamic scaling replicas Horizontal Pod Autoscaler latency SLO experiment paper"、"SurgeGuard ..."。
- WebSearch (extended): "Hotel Reservation DeathStarBench autoscaler number of replicas compared against Kubernetes HPA CPU threshold reinforcement learning" (Reclaimer・DriftGuard-SLA が出た)、"proactive horizontal scaling microservices evaluated on DeathStarBench HotelReservation SocialNetwork ... HPA baseline arXiv 2024 2025" (SN の論文ばかり)、"autoscaling microservices graph neural network HotelReservation ..." (HR の GNN 論文は出ず)、"co-locate microservices same pod DeathStarBench hotelReservation autoscaling HPA granularity" (COLA の一節・DSB の PR が出た)。
- arXiv API (abs 検索): `abs:"hotel reservation" AND abs:autoscaling` 0 件、`all:"hotel reservation" AND all:replicas` は StatuScale のみ、`all:DeathStarBench AND all:HPA` は ARBITER・SLO-Scaler (どちらも HR 不使用)。**arXiv API は全文を引かないので、abstract に HR と書かない論文は拾えない**。
- Crossref (書誌確認)、Unpaywall、Semantic Scholar API (Erms の OA URL の確認)、各 PDF の pdftotext + grep。
- **空白の根拠としての限界**: 範囲は WebSearch と arXiv API と PDF の grep のみ。IEEE Xplore・ACM DL・Google Scholar は未使用。ACM DL・MDPI・IEEE は 403 または OA なしで本文を取れなかった (Erms、Derm、GRAF、DriftGuard-SLA)。**『HR で HPA を基準にした水平スケール論文は無い』と断定はできない**。

#### 13.9.7 次に読む (優先順)

1. **Erms の本文** (ASPLOS '23 または TOCS 版)。HR で水平寄りの決定をする唯一の有力候補で、基準・負荷の配合・HPA の有無が未確認。大学図書館の経由か著者への依頼が要る。
2. **Derm (ISCA '24)**。Erms と同じ著者グループで、『動的な呼び出しグラフ』= 配合変化を扱う。HR を使うかは推測。
3. **DriftGuard-SLA の本文**。HR を K8s + HPA で動かした具体的な設定 (しきい値、レプリカ上限) が書かれている可能性。
4. **DSB の hotelReservation のコード** (consul 登録、初期データ投入、wrk2 の既定配合)。レプリカ増減で使えるかの実機点検。

### 13.10 HPA を扱った論文が評価の対象にしたシステム (2026-11-12、依頼: 『HPA 論文はどんなシステムで評価しているか』を集計し、本研究の選び方 (OB・SS・HR 候補) が標準的かを判断する)

**範囲の限定 (最初に)**: 系統的サーベイではない。arXiv API (abs/all 検索 約 20 本)、WebSearch (標準 4 本・extended 3 本)、既存 §13.1・§12.8・§13.9 の再利用、Crossref／Unpaywall での書誌確認。IEEE Xplore・ACM DL・Google Scholar は直接引いていない。**ここで分かるのは『確認できた 29 本の傾向』であり、母集団の割合ではない。** 「HPA 論文の評価対象」の包括的な集計は、データベースを直接引かないと主張できない。
**『HPA を扱った』の採用基準**: HPA を (a) 改良・拡張する、(b) 比較の基準にする、(c) その上で実験／挙動を分析する、のいずれかで、**本文 (PDF を pdftotext) で HPA の使用を確認できたもの**。VPA のみ・HPA と比較していない独自水平スケーラは表から除いた (除外一覧は 13.10.5)。確認度の記号は §13 冒頭と同じ (★PDF = 原典 PDF 本文／abstract のみ／未確認)。「grep」は語の出現を見て該当段落を読んだもので、全文精読ではない。

#### 13.10.0 結論 (先に)

1. **衝突 (既出) は無し。** 『HPA 下で複数コンテナを同一 Pod に同居させ、予約枠 (requests) と softirq で評価する』論文は今回の範囲では見つからなかった。HPA × 束ねの最近傍は引き続き Buzato & Goldman 2026 (`buzato2026ijnc`、SS、**1 コンテナ内の束ね**、§13.4)。**Pod 内の複数コンテナを扱う論文は 29 本中 0 本。**
2. **評価対象は OB・SS・DeathStarBench Social Network が中心** (29 本中 OB 8、SS 6、SN 5)。**本研究の OB と SS は標準的な選び方**。ただし OB と SS を**両方**使うのは 29 本中 2 本 (COLA、ScalerEval) で、組合せとして珍しくはないが多数派でもない。
3. **実在の企業システムを評価した HPA 論文は 29 本中 0 本。** 全て OSS ベンチマークか自作の合成アプリ。自作・合成のみ (OSS ベンチマークを使わない) は **9 本 (31%)**、うち 8 本はここ 2 年 (2024〜2026) の論文で、品質は幅広い (査読付きは一部。表の確認度と『種別』を見る)。
4. **単一ノードの K8s で評価した HPA 論文は、確認できた範囲で 2 本だけ** (Dashtbani 2025 の 1 台サーバと NimbusGuard の KinD 1 台のラップトップ。どちらも微妙で、本研究の『MicroK8s 単一ノード 16 コア・実機』と完全に同じ条件の論文は無い)。他は 2〜16 ノードの複数ノードで、多くは AWS／GKE のクラウド。**単一ノード・overlay なしは少数派なので、限界節に『ノード間通信を含む構成には一般化できない』と明記する価値が高い** (13.10.4)。
5. **§13.9 の結論を 1 点訂正する。** §13.9 は『HR で K8s HPA を基準／土台にした水平スケール論文は見つからなかった』と書いた。**今回、`CPU-Limits kill Performance` (Shetty ほか、SoCC '25、arXiv:2510.10747) が DeathStarBench の Hotel Reservation と Social Network を EC2 で動かし、HPA を土台にした自作オートスケーラ (YAAS) を作り、HPA のしきい値・requests・limits を掃引している**ことを本文で確認した。HR × HPA の先行例は 1 本ある。ただし焦点は limits の是非で、同居や Pod の粒度ではない (背景)。
6. **本研究の結果の主張を裏付ける一文**: 『CPU-Limits kill Performance』は、limits がレイテンシを悪化させるので autoscaler は limits を外すべきだと主張する (本文 §3)。本研究が実測した『limits を requests と一緒に縮めるとスロットリングで桁違いに悪化する』(CLAUDE.md、scale-third 実験) と方向が一致する。**ただし私が読んだのは本文の一部 (grep) なので、引用前に §3 を通読すること。**

#### 13.10.1 集計 (29 本。重複して数える。『他』は自作・合成・不明)

| 対象システム | 本数 | 論文 (表の番号) |
|---|---|---|
| Online Boutique (OB、11 サービス、Go 主体の gRPC) | 8 | 1, 2, 3, 4, 5, 16, 25, 26 |
| Sock Shop (SS、Java／Go／Node.js 混在) | 6 | 1, 5, 6, 7, 8, 11 |
| DeathStarBench Social Network (SN、C++・Thrift) | 5 | 12, 14, 15, 16, 24 |
| Train-Ticket (TT、Java 41〜64) | 3 | 1, 2, 17 (14 は言及のみ) |
| Bookinfo (BI、4 サービス) | 2 | 1, 13 |
| TeaStore (全て Java) | 2 | 9, 10 (10 は間接確認) |
| DeathStarBench Hotel Reservation (HR) | 1 | 24 |
| 他 (自作・合成・汎用 Web アプリ・ML 推論・Redis Cluster 等) | 11 (うち『他のみ』= 9) | 1 (Simple Web Server)、18〜23、26 (Redis Cluster)、27〜29 |

- **訂正 (2026-11-13、§13.11.0 の 6)**: #14 SHOWAR は SN・TT (41)・OB (10) の 3 つを評価に使っていた (結果の図は SN のみ)。上の表の OB は 8→9 本、TT は 3→4 本に読み替える。
- 『他のみ』= OSS ベンチマークを使わない 9 本 = 18 (対象アプリ不明)、19、20、21、22、23 (不明)、27、28、29。
- **種別 (査読の有無)**: 査読付き会議／誌と確認できたもの = COLA (EuroSys '24 と推定、同一性は未照合)、Smart HPA (ICSA '24)、PBScaler (IEEE TSC)、MS-RA (SEAMS '24)、Gym-HPA (NOMS '23)、Nguyen 2020 (Sensors)、Serracanta 2025 (IEEE Access)、Buzato (IJNC)、SHOWAR (SoCC '21)、Waterfall (CLOSER '21)、Horn (Euro-Par '22)、CPU-Limits (SoCC '25)、NimbusGuard (ICOIN 2026)、NeuroScaler (ICC 2026 の論文として投稿されたと arXiv に記載)、ScalerEval (FSE Companion '26)。**arXiv のみ (査読の有無は未確認)**: SecureSmart HPA、Dashtbani 2 本、STaleX、AdaScale、SLO-Scaler、ARBITER、Morphis、MAS-H2、KARMA、AutoSLO、Platformatic (技術報告)、Punniyamoorthy。Joyce 2024 は Research Square のプレプリント。
- **環境**: クラウド (AWS／GKE／EC2) = COLA、Smart HPA、Buzato、Graph-PHPA、SHOWAR、MAS-H2、Platformatic、CPU-Limits (8 本)。オンプレ・研究室・大学クラウド = PBScaler、Morphis、AdaScale、Nguyen、AutoSLO、Dashtbani (6 本)。不明 = 他。**ノード数**: 1 台のみ (K8s のコントロールプレーンとワーカーが同一機) は NimbusGuard (KinD、MacBook Pro M4 Pro 1 台)、Dashtbani 2025 (2×EPYC 7742 の 1 台、§12 の記録) の 2 本。1 台の物理機で複数 VM = Nguyen 2020 (i7-8700 に 5 VM)。ワーカー 1 台 + master = KARMA (8 vCPU)。残りは 2〜16 ノード。
- **同居 (1 Pod に複数コンテナ)・Pod 粒度を扱う論文**: **0 本**。近いのは、(i) Buzato (1 コンテナ内の束ね)、(ii) Gym-HPA (複数 Deployment の依存を状態に入れる)、(iii) Smart HPA (サービス間で資源の余りを再配分)、(iv) SHOWAR (affinity ルールをスケジューラへ渡す)、(v) CPU-Limits (requests／limits とノード詰め込み)、(vi) Morphis・AdaScale (依存や配置を考慮)。いずれも Pod 内のコンテナ構成は変数にしていない。

#### 13.10.2 論文ごとの表

凡例: HPA の扱い = 改良／基準／土台 (その上で実験・分析)。「—」= 読んだ範囲で記載なし。SN = Social Network、BI = Bookinfo、TT = Train-Ticket、TS = TeaStore。bib key が無いものは 13.10.6 で新規追加 (bib は『未引用』注記)。

| # | 論文 (bib key) | HPA の扱い・設定 | 対象システム (種別・サービス数・言語) | 負荷 | 環境 | 同居／粒度 | 確認度 |
|---|---|---|---|---|---|---|---|
| 1 | Sachidananda & Sivaraman COLA (arXiv:2112.14845、`sachidananda2022cola`) | 基準。CPU しきい値 10〜90% を掃引 | Simple Web Server、BI(4)、OB(11)、SS(14)、TT(64)。全て OSS ベンチ + 1 つの合成アプリ | Locust | GKE | 扱わない | ★PDF (§13.1) |
| 2 | Xie ほか PBScaler (arXiv:2303.14620、`xie2024pbscaler`、IEEE TSC) | 基準 (KHPA = 『K8s の既定の水平スケール。しきい値 T を資源 R に設定』と本文に定義) | OB、TT(40 超) | Wiki 由来のパターン注入 | 3 台 (計 44 コア、220 GB)、研究室 | 扱わない | ★PDF (2026-11-12 に KHPA の定義を再確認) |
| 3 | Ahmad ほか Smart HPA (arXiv:2403.07909、`ahmad2024smarthpa`、ICSA '24) | 改良。サービス間で余った資源を足りないサービスへ再配分。指標は CPU 利用率 | OB(11) | Locust (OB 付属) | AWS t3.medium × 10 | サービス間の資源再配分 (Pod 内ではない) | ★PDF (§13.1) |
| 4 | Ahmad ほか SecureSmart HPA (arXiv:2506.05693、新規 key `ahmad2025securesmart`) | 改良 (Smart HPA の耐障害化) | OB | Locust | — | 扱わない | ★PDF grep (§13.1) |
| 5 | Xie ほか ScalerEval (arXiv:2504.08308、`xie2026scalereval`) | 基準 (KHPA 20/50/80%) と評価基盤 | OB、SS | Locust (Wiki-Pageviews 由来) | K8s + Istio | 扱わない | ★PDF (§13.1) |
| 6 | Dashtbani & Tahvildari "Key Considerations" (arXiv:2510.02585、`dashtbani2025`) | 基準 (6 手法に KHPA を含む) | SS で評価。BI・OB・SS・TT を導入して課題を比較 | Locust + WorldCup98 | **1 台** (2×EPYC 7742) | 扱わない | ★PDF (§12) |
| 7 | Dashtbani & Tahvildari STaleX (arXiv:2501.18734、`dashtbani2025stalex`) | 基準。HPA しきい値 25/50/60/70% | SS | Locust + WorldCup98 | 自前 K8s | 扱わない | ★PDF grep (§13.1・§12.8) |
| 8 | Nunes ほか MS-RA (arXiv:2403.08798、`nunes2024`、SEAMS '24) | 基準 (HPA)。要求駆動の自己適応 | SS (OB は言及のみ) | JMeter | — | 扱わない | ★PDF (§12) |
| 9 | Goli ほか Waterfall (`goli2021waterfall`、CLOSER '21) | 基準 (K8s HPA) | **TeaStore** (全 Java) | JMeter (25 分の browse 負荷) | K8s 1 + 4 ノード | 扱わない | ★PDF (§13.1) |
| 10 | Horn, Fard, Wolf (`horn2022moha`、Euro-Par '22) | 基準 (一般的な HPA)。ハイブリッド多目的 | TS と推定 (間接確認) | — | — | — | abstract + 間接 (本文未読。引用前に読む) |
| 11 | Buzato & Goldman (`buzato2026ijnc`、IJNC) | **土台** (HPA の有無 × 束ね 4 通り)。しきい値 150% (§9.17) | SS | Locust (閉ループ) | AWS EKS、t3.xlarge、2 ノード／シナリオ | **1 コンテナ内の束ね**。Pod 内別コンテナは今後の課題と本人が記述 | ★PDF (§13.4) |
| 12 | Chen ほか ADASCALE (arXiv:2607.15681、新規 key `chen2026adascale`) | 基準 (K8s HPA と NetMARKS Scale)。配置とスケールを同時に決める | **SN** (3 つの root 操作)、DeathStarBench | wrk (本文で 5 回) 。3 つの root 操作の**混合比を振る** (Alibaba は背景説明のみ) | 16 VM (ワーカー 15 × 8 コア、K8s v1.27/1.28)、大学の研究クラウド、ノード間遅延を人工的に追加 | 配置を扱うが Pod 内は扱わない | ★PDF grep (2026-11-12) |
| 13 | Nguyen, Zhu, Liu Graph-PHPA (arXiv:2209.02551、新規 key `nguyen2022graphphpa`) | 基準 (『ルールベースの K8s HPA』)。LSTM + GNN の予測型 | BI | 「実データセット由来」のリアルタイム負荷 (Locust の語あり) | AWS + Prometheus + Grafana | 扱わない | ★PDF grep (2026-11-12) |
| 14 | Baarzi & Kesidis SHOWAR (SoCC '21、DOI 10.1145/3472883.3486999、新規 key `baarzi2021showar`) | 基準 (『default Kubernetes autoscalers』= HPA と VPA の組。本文に『HPA』の語は無い)。水平 + 垂直の両方を制御 | SN が主 (本文の語数 7)。OB・TT は言及のみで評価に使ったかは未精査 | Locust、Wiki 由来 | AWS の VM クラスタ | affinity のヒントをスケジューラへ。Pod 内は扱わない | ★PDF grep (2026-11-12) |
| 15 | Wang ほか SLO-Scaler (arXiv:2608.18390、新規 key `wang2026sloscaler`) | 基準。K8s HPA (**CPU 目標 60%**)、KEDA、LSTM-Pred | **SN** (12 サービス) | Locust、Alibaba 2022 トレース由来、周期・バースト・長裾 | ワーカー 5 台 (8 vCPU・16 GB) | 扱わない | ★PDF (2026-11-12、実験節を読んだ) |
| 16 | Habibi & Leon-Garcia ARBITER (arXiv:2607.19182、新規 key `habibi2026arbiter`) | 基準 (HPA／資源のみの制御は、故障の種類や下流の対象を選べないと主張)。LLM を使う是正制御 | SN と OB (OB は移植性の確認) | 負荷ツールは未特定 (grep の『wrk2』は SN の API 名 `/wrk2-api/` で、ツール名ではない) | 4 ノード | 配置修正を含むが Pod 内は扱わない | ★PDF grep (2026-11-12) |
| 17 | Tang ほか Morphis (arXiv:2602.01044、新規 key `tang2026morphis`) | 基準 (『HPA 比で総 CPU を最大 38% 削減』が図 12 の説明) | **TT** (41 サービス) | Locust (3 つの負荷シナリオ: 漸増・高負荷持続・スパイク + 高原。本番トレースに似せて較正。別に 40 時間の自前ストレス試験で QueryTicket・BookTicket・Pay を収集) | 物理 3 台 (各 64 コア・128 GB)、10 Gbps | 呼び出しグラフの変化を扱う | ★PDF grep (2026-11-12) |
| 18 | Hamzeh & Vahdatian MAS-H2 (arXiv:2603.07607、新規 key `hamzeh2026mash2`) | 基準 (HPA と Cluster Autoscaler。本文は『HPA の CPU は 80% 超で推移』と記述) | **対象アプリは未特定** (grep で名前が出ない) | k6 (Heartbeat とフラッシュセール) | GKE | 扱わない | ★PDF grep。アプリ名は未確認 |
| 19 | Wanigasooriya & Ekanayake NimbusGuard (arXiv:2604.11017、ICOIN 2026、DOI 10.1109/ICOIN68469.2026.11480646、新規 key `wanigasooriya2026nimbusguard`) | 基準 (HPA と他)。DQN による予測型 | **自作** (Python/FastAPI の CPU 消費を決定的にした 1 つのステートレスアプリ) | 自作 asyncio スクリプト (固定シード) | **KinD (K8s v1.28) を MacBook Pro M4 Pro 1 台** (8 vCPU・16 GB を割当) | 扱わない | ★PDF (2026-11-12、実験節を読んだ) |
| 20 | Soulé ほか KARMA (arXiv:2505.21559、新規 key `soule2025karma`) | 基準 (KHPA、Gym-HPA、Rlad-core、AWARE の 3 つの RL + KHPA)。MAS で自動生成 | **自作の合成** ('Chained Services' など) | Locust + 自作スクリプト (DDoS を模擬) | ワーカー 1 台 (8 vCPU・32 GB) + 学習用 GPU 機 | 扱わない | ★PDF (2026-11-12、環境の節) |
| 21 | Chaves ほか NeuroScaler (arXiv:2602.08191、新規 key `chaves2026neuroscaler`) | 基準 (K8s HPA。遅延由来の目標) と MPC | **汎用の Web アプリ 1 つ** (名前なし) | k6 | — | 扱わない | ★PDF grep |
| 22 | Tymoshenko ほか Platformatic (arXiv:2604.19705、技術報告、新規 key `tymoshenko2026platformatic`) | 基準 (HPA と KEDA)。Node.js の event loop 利用率で予測 | **自社製品の Node.js ワークロード** | k6 (別 EC2 から) | EKS (K8s v1.35)、m5.2xlarge × 4 | 扱わない | ★PDF grep (テスト環境の節) |
| 23 | Punniyamoorthy ほか (arXiv:2512.23415、新規 key `punniyamoorthy2025slocost`) | 基準 (既定と調整済みの K8s オートスケール)。SLO・コスト意識 | **『代表的なマイクロサービスとイベント駆動の負荷』と書くのみで、具体名は本文に無し** | — | — | 扱わない | ★PDF grep。評価の記述が薄く、引用に不向き |
| 24 | Shetty ほか **CPU-Limits kill Performance** (arXiv:2510.10747、SoCC '25、DOI 10.1145/3772052.3772219、新規 key `shetty2025cpulimits`) | **土台**。HPA の上に自作の autoscaler (YAAS) を作る。requests・limits・HPA しきい値 (CPU.Thres) を掃引。『しきい値 = 100 − 余裕』と設定 | **HR と SN** (DeathStarBench) | — (grep で見つからず) | EC2 クラスタ | **requests／limits とノード詰め込み** (同居は『ノード内のコンテナの共存』の意味) | ★PDF 一部 (§3 を grep。通読は未) |
| 25 | Li, Sabetzadeh, Nejati AutoSLO (arXiv:2605.01533、新規 key `li2026autoslo`) | 基準 (HPA の **CPU しきい値 80%**) と PBScaler。遺伝的プログラミング | **OB (11)** + LLaMA-3 の LLM チャットボット | IoTECS で生成 | master 1 + ワーカー 2 (Xeon Gold 6338 × 2、512 GB、A40 GPU)、Istio | 扱わない | ★PDF (2026-11-12、事例の節) |
| 26 | Santos ほか **gym-hpa** (NOMS 2023、DOI 10.1109/NOMS56928.2023.10154298、新規 key `santos2023gymhpa`) | 基準 (KHPA。『Deployment ごとに独立に動き、依存関係を知らない』と本文)。強化学習 | **OB** と Redis Cluster | Locust (+ Prometheus 用 Locust Exporter) | K8s クラスタ (規模は読んだ範囲に無し)。シミュレーション環境も併用 | 複数 Deployment の依存を状態に入れる (Pod 内ではない) | ★PDF (imec の公開版、2026-11-12) |
| 27 | Nguyen, Yeom, Kim, Park, Kim (Sensors 20(16):4621、DOI 10.3390/s20164621、新規 key `nguyen2020hpa`) | **土台** (HPA の挙動分析。既定の Resource Metrics と Prometheus のカスタム指標を比較) | **自作の CPU 集約アプリ** (リクエストを受けると CPU を使い続ける) | Gatling (最大 1800 req/s) | **物理 1 台 (i7-8700) の上に 5 VM** (master 1 + worker 4、K8s 1.15.1)。requests 100m・limits 200m、レプリカ 4〜24 | 扱わない | ★本文 (PMC のオープンアクセス、2026-11-12) |
| 28 | Serracanta ほか (IEEE Access 13:7160–7166、2025、DOI 10.1109/ACCESS.2025.3526751、新規 key `serracanta2025hpastability`) | **土台** (HPA の制御理論モデルと安定性解析。サービスグラフへ拡張) | **合成** (3 サービスのカスケード。各 8 ms の算術を実行) | k6 (20〜22 VU、20 分) | 実機テストベッド (規模の記載は読んだ範囲に無し)。HPA v2、CPU **requests 100m の 80%** | サービスグラフの伝播を扱う | ★PDF (UPC の公開版、2026-11-12) |
| 29 | Joyce & Sebastian (Research Square プレプリント、2024、DOI 10.21203/rs.3.rs-4262320/v1、新規 key `joyce2024hpaml`) | **土台** (HPA の評価。ML 推論の 3 アプリ) | **ML モデル 3 つ** (CPU 集約) | JMeter | K8s 3 ノード (master 1 + worker 2、各 4 コア・8 GB)、クラウド。レプリカ 2〜50 | 扱わない | ★PDF (プレプリント、査読なし) |

#### 13.10.3 位置関係の判定

- **衝突 (既出): 無し。** HPA × 同居 (Pod 内の別コンテナ) × requests × softirq を扱う論文は見つからなかった (範囲は 13.10.7)。
- **相補**: Buzato & Goldman 2026 (#11、§13.4 のとおり。束ねの単位が 1 コンテナ内で、指標・負荷・予約枠の扱いが違う)。
- **背景**: 上の表のほぼ全て。特に (a) `shetty2025cpulimits` (#24)＝HPA のしきい値と requests／limits の関係を HR・SN で掃引した先例。本研究の『limits は据え置き、requests だけ縮める』の方針の裏付けに使える。(b) `nguyen2020hpa`・`serracanta2025hpastability` (#27・#28)＝HPA の挙動 (指標の取得周期・スケールまでの遅れ・安定性) の一次資料。(c) `santos2023gymhpa` (#26)＝HPA が Deployment 単位で依存関係を知らないという**本研究の出発点と同じ指摘**を OB で述べている。
- **無関係 (混同注意)**: HGraphScale (arXiv:2511.01881、階層グラフ学習の自動スケール。シミュレーションで HPA を基準にしない)、AAPA (arXiv:2507.05653、サーバーレス向け)、`Optimal Configuration of API Resources in Cloud Native Computing` (arXiv:2512.23494、TeaStore を使うが本文に HPA の語が 0 件)。検索語『HPA』『autoscaling』で出るが、本研究の主題とは別。

#### 13.10.4 本研究 (OB・SS・HR 候補) の選び方は標準的か。査読への備え

- **OB と SS の選択は標準的。** 29 本中 OB が 8 本、SS が 6 本。他のベンチマークと比べて最も使われる側に入る。両方を使う論文も 2 本ある (COLA、ScalerEval)。
- **HR は少数派だが前例はある。** HR を HPA 論文で使うのは #24 (SoCC '25) の 1 本だけ (§13.9 の StatuScale は HPA が基準にない)。『HR を 3 つ目に選ぶ根拠』としては、先行例の数よりも (i) Go・gRPC で JVM 起動 CPU の交絡が無い、(ii) 型ごとの配合の既定値がある、(iii) 通過サービス数が少ない、という条件 (§13.5) で説明する方が安全。先行例が少ないことは弱点として隠さず『本研究の HPA 実験を HR で行った例は見つからなかった (範囲: 13.10.7)』と書く。
- **想定される指摘と答え**
  1. 「なぜ実在の企業システムで評価しないのか」→ 確認できた HPA 論文 29 本の全てが OSS ベンチマークか合成アプリで、実システムは 0 本。企業の実サービスは構成が公開されず、Pod 内の構成を変える実験が許されない (これは推測。論拠は『先行研究も同じ』に限る)。
  2. 「単一ノード 16 コアは小さい／現実的でない」→ 単一ノード・overlay なしは、**同居の効果を通信経路の差 (veth/bridge と loopback) に切り分けるための意図的な条件**。他の論文は複数ノードで、ノード間通信と同居の効果が混ざる。単一ノードの先例は 2 本だけ (NimbusGuard、Dashtbani)。今回取得した約 40 本の本文に『softirq』の語は 0 件 (grep)。softirq を指標にした HPA 論文は見つからなかった。限界は『ノード間通信 (overlay・VXLAN) を含む構成には一般化できない』と明記する (§9.1 の方針と同じ)。
  3. 「自作の負荷 (buy／view の配合) は標準か」→ 標準は Locust (閉ループ) と、実トレース (Alibaba・Wiki・WorldCup98) による**負荷の総量の変動**。リクエスト型の配合を振る論文は少ない (Nodens、ADASCALE が操作の混合比を振る。§13.9、#12)。本研究の k6 開ループは標準ではなく、閉ループの双安定を避けるための意図的な選択 (CLAUDE.md、`openloop-k6-capacity` のとおり)。
  4. 「HPA の設定 (目標 70%) は妥当か」→ 先行研究の設定は幅広い: 60% (SLO-Scaler)、80% (AutoSLO、Serracanta)、50% の既定 (Autothrottle の K8s-CPU)、10〜90% の掃引 (COLA)、25〜70% (STaleX)、20/50/80% (ScalerEval)、150% (Buzato)。70% は範囲内で、特別ではない。
- **同居を扱う先行例は実質ゼロ**という主張を書くときは、『確認できた範囲で』と限定する。範囲は 13.10.7。

#### 13.10.5 除外したもの (表の外。理由付き)

| 論文 | 除外の理由 (本文で確認した範囲) |
|---|---|
| DeepScaler (arXiv:2309.00859、`meng2023deepscaler`) | 本文に『HPA』『KHPA』『Horizontal Pod Auto』の語が **0 件** (2026-11-12)。基準は AWS 方式・MMN 等。§13.1 では『K8s HPA は未確認』としていたので、HPA 論文には数えない |
| FIRM (arXiv:2008.08509、`qiu2020firm`) | 本文に HPA の語が 0 件。『Kubernetes autoscaling』は垂直寄りの制御 |
| Autothrottle (`wang2024autothrottle`) | 基準 K8s-CPU・K8s-CPU-Fast は『K8s の既定の autoscaler の再実装』と書くが、動作は『CPU 使用量 / しきい値 = 割り当て量』を決める**垂直** (割り当て量の更新)。HPA ではないと判断。§9.17 の引用 (配合を一定にする記述) は有効なまま |
| Sinan (`zhang2021sinan`) | Docker Swarm 上で K8s ではない (§13.1) |
| StatuScale (arXiv:2407.10173、`wen2025statuscale`) | 基準は GBMScaler・Showar・Hyscale で HPA は含まない (§13.8)。本文中の『HPA』は関連研究の説明のみ |
| LSRAM (arXiv:2411.11493)、MSARS (arXiv:2409.14953)、Ursa (arXiv:2401.02920) | HPA の語は関連研究の説明と比較表のみ (MSARS・Ursa は grep で 0 件または説明のみ)。実験の基準にしていない |
| HGraphScale (arXiv:2511.01881)、AAPA (arXiv:2507.05653) | 上の『無関係』 |
| GRAF (`park2021graf`) | 基準が『K8s オートスケーラ』としか読めておらず、HPA と確認できない (途中で切れた PDF)。判定保留 |
| Springer の『RL-Based Autoscaling for Cost and Performance Optimization in Kubernetes Clusters』 (link.springer.com/chapter/10.1007/978-3-032-10344-4_3) | WebSearch の要約のみ (HPA・VPA・KEDA との比較、9 ノード EKS)。本文・書誌の確認ができなかった。**表に入れない** |
| 『Business-Aware SLA-Driven Autoscaling for Kubernetes Microservices Using Application-Level Observability』 (ResearchGate の項) | WebSearch の要約のみ。本文を取得していない。表に入れない |
| BASE (arXiv:2402.12962) | §13.1 のとおり、取得した版の本文にベンチマーク名が出ず未確認 |
| Nodens・SurgeGuard・Reclaimer | 垂直のみ (§13.9) |

#### 13.10.6 bib への追加 (全て『未引用』注記。`FOSE2026-TeX-UTF8/fose2026.bib` に追記済み)

`ahmad2025securesmart`、`chen2026adascale`、`nguyen2022graphphpa`、`baarzi2021showar`、`wang2026sloscaler`、`habibi2026arbiter`、`tang2026morphis`、`hamzeh2026mash2`、`wanigasooriya2026nimbusguard`、`soule2025karma`、`chaves2026neuroscaler`、`tymoshenko2026platformatic`、`punniyamoorthy2025slocost`、`shetty2025cpulimits`、`li2026autoslo`、`santos2023gymhpa`、`nguyen2020hpa`、`serracanta2025hpastability`、`joyce2024hpaml` (19 件)。書誌の確認: SHOWAR・Serracanta・Nguyen・Gym-HPA・CPU-Limits・NimbusGuard は Crossref で DOI と著者を確認。その他の arXiv 論文は arXiv API の著者・題・日付を確認 (掲載先の有無は未確認)。

#### 13.10.7 検索の記録 (2026-11-12)

- **arXiv API** (https://export.arxiv.org/api/query): `all:"Horizontal Pod Autoscaler" AND all:microservices` (5 件)、`all:"Kubernetes HPA" AND all:autoscaling` (2 件)、`abs:"Horizontal Pod Autoscaler"` (13 件)、`abs:HPA AND abs:Kubernetes AND abs:microservice` (6 件)、`abs:"Kubernetes" AND abs:autoscaling AND abs:"Online Boutique"` (1 件)、`abs:autoscaler AND abs:"Train-Ticket"` (0 件)、`abs:autoscaling AND abs:"TeaStore"` (1 件、HPA 無し)、`abs:autoscaling AND abs:"Sock Shop"` (1 件)、`abs:"proactive autoscaling" AND abs:Kubernetes AND abs:microservices` (2 件)、`abs:"reinforcement learning" AND abs:HPA AND abs:Kubernetes` (3 件)、`abs:autoscaling AND abs:"DeathStarBench"` (3 件)、`abs:"autoscaling" AND abs:"Bookinfo"` (1 件)、`abs:"autoscaling" AND abs:"Kubernetes" AND abs:"Alibaba"` (0 件)。**arXiv API は abstract のみの検索が中心で、本文に OB 等の名前しか出ない論文は拾えない**。
- **WebSearch** (extended): 『Kubernetes HPA microservices experimental evaluation baseline benchmark』『proactive horizontal scaling ... Train-Ticket OR TeaStore OR Hipster Shop ...』『HPA custom metrics versus CPU ... Sock Shop OR TeaStore OR Online Boutique』。(standard): 『HPA CPU threshold analysis ... TeaStore OR Train Ticket OR Online Boutique』、『Gym-HPA ... NOMS 2023』、『Nguyen "Horizontal Pod Autoscaling in Kubernetes for Elastic Container Orchestration"』、『HPA stabilization window tolerance configuration study ...』。ヒットは Smart HPA／ScalerEval／PBScaler／STaleX が繰り返し出て、**既存 §13.1 の標本と大きく重なった** (= 同じ論文群が検索で上位に出る偏りがある)。新規に拾えたのは Gym-HPA、Nguyen 2020、Serracanta 2025、Joyce 2024、AutoSLO、KARMA、CPU-Limits、NeuroScaler、Platformatic など。
- **出なかったもの**: (i) TeaStore × HPA の新しい論文 (Waterfall・Horn 以外)、(ii) Train-Ticket × HPA の arXiv abstract 検索 (0 件、本文には出る)、(iii) 同居 (Pod 内の複数コンテナ) × HPA の論文。**ただし (iii) の空白の根拠は WebSearch と arXiv abstract 検索に限る。IEEE Xplore・ACM DL・Google Scholar は未使用。**
- **取得できなかった／しなかった**: GRAF の全文、Springer の RL 章、ResearchGate の SLA 論文。

#### 13.10.8 次に読む (優先順)

1. **`shetty2025cpulimits` (CPU-Limits kill Performance) の §3〜§5 通読**。HR で HPA しきい値・requests・limits を掃引した唯一の論文。HR を 3 つ目にするなら実験設計 (負荷・EC2 の構成・SLO) の参考になる。
2. **`santos2023gymhpa` の実験環境の節** (今回は環境の記載を grep で見つけられなかった)。『HPA は Deployment 単位で依存関係を知らない』という出発点が本研究と同じで、OB の requests／limits／min／max の表 (表 V) もある。
3. **`nguyen2020hpa`** (HPA の指標取得周期と遅れの一次資料。本研究の『ウォームアップ中の増やし遅れ』の説明に使える可能性)。
4. **MAS-H2・Punniyamoorthy の対象アプリ**。名前が本文に無いので、引用するなら著者の公開コードで確認が要る。引用には不向きと判断。
5. **Horn (`horn2022moha`) の本文**。TeaStore と推定のまま。

### 13.11 ベンチマーク別の研究の概要: Sock Shop／Social Network／Train-Ticket／Bookinfo を使った 14 本 (2026-11-13、依頼: §13.10 の評価対象の集計のうち 4 つのベンチマークを使った論文の概要)

**範囲**: §13.10.2 の表で該当する論文を特定した (SS 6・SN 5・TT 3・BI 2 = 延べ 16、重複を除くと 14 本)。新規の検索はしていない。既存の PDF (§13.1・§13.8・§12.8 で取得済みのもの) を pdftotext し、**今回は各論文の概要・主な結果・ベンチマークの使い方を原文で再確認した** (表の数値は PDF の抽出テキストから。図の目盛りは読めていない)。Buzato & Goldman は §7.3・§13.4 の記述を引き継いだ (本誌版 PDF で abstract の数値のみ再確認)。bib key は全て既存 (`fose2026.bib`) で、今回の bib 追記は無い。
**確認度の記号**: ★本文 = 原典 PDF の本文を読んだ (全文精読ではなく、概要・実験節・結果を読んだ。範囲は各カードに記載)。
**用語 (初学者向け)**: SLO = サービス品質の目標 (例: 応答時間の 95 パーセンタイルが 500 ms 以下)。SVR = SLO を破った割合。KHPA = K8s 標準の HPA。HPA は Pod の CPU 利用率が目標 (例 50%) を超えると台数を増やす。

#### 13.11.0 結論 (先に)

1. **衝突 (既出) は無し。** 14 本のうち、Pod 内に複数コンテナを同居させる／Pod の粒度を変数にする論文は 0 本。最も近いのは Buzato & Goldman (SS、1 コンテナ内の束ね) で、判定は §13.4 のまま相補。
2. **SS・SN・TT・BI を使う論文の HPA の扱いは大多数が『基準 (比較相手)』で、提案は予測型 (LSTM・GNN)、依存関係を見る、強化学習、制御理論、ボトルネック特定など。** 負荷は総量 (QPS・ユーザ数) を変える設計が主で、リクエスト型の**配合**を振るのは ADASCALE (SN) だけ (3 つの root 操作の混合比)。Morphis は呼び出しグラフの変化を扱うが、配合を実験の軸にしてはいない。
3. **評価指標は SLO 違反率・応答時間・総 CPU (コア数や core-minutes)・レプリカ数・費用が中心。softirq やリクエストあたりの通信 CPU を指標にした論文は 14 本中 0 本。** (14 本全ての抽出テキストを 2026-11-13 に grep し、『softirq』は 0 件。)
4. **SS で HPA 基準の改善を言う 5 本 (COLA・ScalerEval・Dashtbani・STaleX・MS-RA) は、SS の Java の起動 CPU を除去も議論もしていない** (Dashtbani のみ対処、§12.8)。SS の COLA の費用削減は 1.34% と、OB の 33.11% に比べて小さい (COLA 表 1)。SS では HPA を置き換える利得が小さい可能性があるが、原因は本文に無く推測にとどまる。
5. **環境は複数ノード (3〜25 ノード) が大多数。ScalerEval (ワーカー 1 台・32 コア) と Dashtbani (1 台の物理機を VM で分割) だけ単一機に近い。** 同居の効果を通信経路の差として切り出す本研究の単一ノード設計は、比較先が無い (限界節に書く。§9.20 と同じ)。
6. **訂正 (§13.10 の 1 点)**: SHOWAR (`baarzi2021showar`) の評価対象は SN だけでなく **SN・TT (41 サービス)・OB (10 サービス) の 3 つ**で、『結果は 3 つで一貫していたので紙面の都合で SN のみ報告』と本文に書く (§5.1)。§13.10.1 では OB・TT は『言及のみ』としたが、評価には使っている (結果の図は SN のみ)。集計は OB 9 本・TT 4 本に直る。

#### 13.11.1 Sock Shop (SS) を使う 6 本 (うち COLA は 4 ベンチマーク全て。重複は 1 回だけ詳述)

| 論文 (bib key) | 何をするか | 主な結果 | 本研究との関係 |
|---|---|---|---|
| COLA (`sachidananda2022cola`、★本文) | サービスごとに独立に台数を決めず、アプリ全体で VM 数を最適化 | HPA 系を含む 5 基準に対し、費用 −19.3% (63 負荷中 53 で目標達成) | 背景 |
| ScalerEval (`xie2026scalereval`、★本文) | オートスケーラの評価基盤 (1 回の操作で評価を実行) | HPA の CPU 目標 20/50/80% を比較 (閾値が高いほど SVR 高・資源少) | 背景 |
| Dashtbani & Tahvildari (`dashtbani2025`、★本文) | 実運用に近い落とし穴 (起動 CPU・probe 等) の整理 | 落とし穴を直したうえで 6 手法を比較。PBScaler が最良 | 背景 (現象の先行例) |
| STaleX (`dashtbani2025stalex`、★本文) | サービスごとの PID 制御を時空間特徴で重み付け | HPA 比で資源 −26.9% (abstract) | 背景 |
| MS-RA (`nunes2024`、★本文) | SLO を入力に台数・資源を自動調整 | HPA 比で CPU 時間 −50% 以上、メモリ −87%、レプリカ −90% | 背景 |
| Buzato & Goldman (`buzato2026ijnc`、★本文) | サービスの束ねと HPA の相乗効果 | HPA 有りで throughput +66%、応答時間 −32% (all-in-one、中負荷) | **相補 (最重要)** |

**COLA** (Sachidananda & Sivaraman、arXiv:2112.14845 v3、公刊版は EuroSys '24 と推定で未照合。§13.1 と同じ)。
- 何を解くか: K8s は各マイクロサービスの台数を独立に増減するが、応答時間の合計には複数サービスが効くので、全サービスの割当を**まとめて**決めて費用を下げる、という研究。
- 手法: 学習ベース (サービスごとの利用率で混んだサービスを見つけて VM を足す。学習した政策を補間)。基準は 5 つ (K8s の自動スケール系 2 つ + 機械学習系 3 つ。HPA は CPU 10〜90% を掃引)。**台数は VM (ノード) 単位**で考えている点に注意。
- ベンチマーク: Simple Web Server (1 サービス)、**Bookinfo (4)、Online Boutique (11)、Sock Shop (14)、Train-Ticket (64)** の 5 つ。Locust、GKE (Standard と Autopilot)。表 1 の費用削減は Simple Web Server 13.95% / **Bookinfo 18.01%** / OB 33.11% / **Sock Shop 1.34%** / **Train-Ticket 26.25%**。
- 主な結果: 63 負荷のうち 53 で目標を満たし、次に安い基準より費用 −19.3%。残り 10 では、目標を満たす最安の政策が COLA より +69.9%。訓練費用は 1 日〜1 週間で回収と記述。
- 関係: 配合を振る実験ではなく (負荷は RPS)、同居・Pod 粒度は扱わない。SS・BI・TT・OB を 1 本で使う貴重な例で、**アプリごとに利得が大きく違う** (SS 1.34% 対 OB 33.11%) 点が本研究の『アプリを 2 つ以上使う』根拠になる。群: C (背景)。

**ScalerEval** (Xie ほか、arXiv:2504.08308、FSE Companion '26、4 頁の短報)。
- 何を解くか: オートスケーラの評価は、観測・スケール操作・負荷注入の準備が大変で、手作業の差でぶれる。**評価を自動化する基盤**を作る。
- 手法: 規則も ML も提案しない。評価の道具。実験は PBScaler・SHOWAR・KHPA (CPU 20/50/80% の 3 変種) と何もしない NoneScaler を比べるもの。
- ベンチマークの使い方: **OB と SS**。Wiki-Pageviews (2015-03-16) 由来の 20 分の動的負荷、同時ユーザ数の上限 740。SLA は 500 ms。ワーカー 1 台 (32 コア・96 GB) + master、K8s + Istio。
- 主な結果: 全スケーラが NoneScaler より SVR を大きく下げる (本文: 『少なくとも 0.85』)。OB では SHOWAR が SVR わずかに最低だが資源が多い。KHPA は閾値が上がるほど SVR が悪化し資源が減る (逆相関)。表 II の OB の CPU (×10² コア) は NoneScaler 6.23、KHPA-20/50/80 が 20.95/19.14/18.39、PBScaler 17.89 (抽出テキストの読み取り。SS 側の値は切れていて未確認)。
- 関係: 背景。ただし**ワーカー 1 台 + Istio** は本研究に近い構成で、『単一ノードは非標準』の反例になる (サイドカー有り、同居は無し)。

**Dashtbani & Tahvildari "Key Considerations"** (arXiv:2510.02585、§12.1.1 の記述を引き継ぐ。今回 abstract・結果節を再確認)。
- 何を解くか: オートスケール論文は理想的な条件を仮定しがちなので、SS に 6 手法を当てて、**アーキテクチャ・実装・配備の 3 段階の落とし穴 (10 個)** を整理する。
- 手法: 手法の提案ではなく経験的研究。6 手法 = 閾値 (KHPA)・制御理論・学習・ブラックボックス最適化・依存関係考慮。
- ベンチマーク: SS (13 サービス) の **/login のみ**、Locust + WorldCup98 の 10 時間。SLO 150 ms。物理 1 台 (2×EPYC 7742) を VM で分割 (制御 1 + ワーカー 2)。BI・OB・SS・TT を導入して課題を比較。
- 主な結果: 落とし穴 (Carts の JVM 起動 CPU で KHPA が暴走、probe、cgroup) を直したうえで、PBScaler が応答時間・総 CPU とも最良、HEAT と SHOWAR は SLO 違反が多い、KHPA は CPU は少ないが違反あり (Fig. 9・10)。直す前の基準結果は『オートスケール不能のため省略』と本文に明記。
- 関係: 背景 (§12 のとおり)。SS の Java 暴走を本研究の新発見と書かない。

**STaleX** (Dashtbani & Tahvildari、arXiv:2501.18734)。
- 何を解くか: サービスごとに別々の HPA 閾値が要るので、鎖状の依存 (front-end → user → carts) を見て調整する。
- 手法: サービスごとの PID 制御器の重みを、依存・起動時間・負荷の時間変化 (時空間特徴) で動的に調整 (制御理論 + 機械学習 + 経験則)。
- ベンチマーク: SS の /login、SLO 200 ms、Locust + WorldCup98、自前 K8s。予備実験で HPA の閾値を一律 25/50/60/70% にすると、25→70% で資源 4039→1110 core/min、SLO 違反は 0→212760 ms と**閾値は資源と違反のトレードオフ**を示す。サービスごとに変えた閾値の組 (4 通り) も試す。
- 主な結果: HPA 比で資源 −26.9% (abstract。図表の個別値は未確認)。
- 関係: 背景。サービスごとに閾値を変える発想は、本研究の『同居すると閾値が Pod 単位になる』損の別の形 (§13.10.4 の HPA 設定の幅の一例)。

**MS-RA** (Nunes ほか、arXiv:2403.08798、SEAMS '24)。
- 何を解くか: 性能最大化でなく、**SLO を満たす最小の資源**にそろえる自己適応型のオートスケール。
- 手法: 規則ベース (MAPE-K ループで SLO の達成度を 3 段階 (満たす・超過・不足) に判定し、垂直・水平に増減)。SLO は 2 つ (X% の呼び出しが 2.5 秒以内、失敗率 Y% 未満)、3 設定 (A・B・C)。
- ベンチマーク: SS、JMeter、front-end を複製して業務サービスにだけ負荷が届くようにした。単一ベンチマークと本人が限界に書く。
- 主な結果: 高く変動する負荷で、HPA に比べ CPU 時間 −50% 以上、メモリ −87%、レプリカ −90% (§1)。基準 HPA が台数を 20 まで増やす現象を『安定化時間』で説明 (§12.8)。
- 関係: 背景。HPA の台数膨張は本研究のウォームアップ中の増やし遅れ (§9.16) に近い現象だが、原因の議論は異なる。

**Buzato & Goldman** (`buzato2026ijnc`、IJNC 16(1)、DOI 10.15803/ijnc.16.1_52、★本文。§7.3・§13.4 を引き継ぐ。今回は abstract の数値を再確認)。
- 何を解くか: 複数サービスを 1 つのコンテナ (イメージ) に束ねると、HPA 下でスループットや費用はどう変わるか (SS)。
- 手法: 実験分析 (規則も ML も無し)。4 通り (Benchmark / All-in-one / By-dependencies / By-stack) × HPA 有無。HPA の目標は CPU/メモリ 150%、1〜4 Pod。
- ベンチマーク: SS (Java／Go／Node.js)、Locust (閉ループ)、AWS EKS、t3.xlarge。HPA 無しはシナリオごとに 1 ノード、有りは 2 ノード。各条件 6 サイクル。
- 主な結果: HPA 有りで throughput が最大 +66% (All-in-one、中負荷。By-stack は +33%)、応答時間 −32%/−24% (中負荷)。代償はディスク使用量と運用の複雑さ。
- 関係: **相補 (最重要)**。束ねの単位が『1 コンテナ内のプロセス』で、Pod 内の別コンテナは今後の課題と本人が書く。指標は絶対 CPU・スループットで、予約枠・softirq/req は無し。

#### 13.11.2 DeathStarBench Social Network (SN) を使う 5 本

| 論文 (bib key) | 何をするか | 主な結果 | 本研究との関係 |
|---|---|---|---|
| ADASCALE (`chen2026adascale`、★本文) | 配置とスケールを同時に決める | NetMARKS Scale 比で応答時間が最大 1.93 倍速い (読み出し) | 背景 (配合を振る点で参考) |
| SHOWAR (`baarzi2021showar`、★本文) | 水平・垂直・配置のヒントを一括で決める | 資源 −22% (最大)、p99 −20% | 背景 (相関で同居ヒント) |
| SLO-Scaler (`wang2026sloscaler`、★本文) | ベイズ LSTM で予測し、ボトルネックだけ増やす | 突発負荷で SLO 違反 −29〜56%、レプリカ −18〜33% | 背景 |
| ARBITER (`habibi2026arbiter`、★本文) | 故障時の是正を安全に自動化 (LLM 可) | 悪い画像のとき HPA は増やすだけ、ARBITER は 5/5 で巻き戻し | 無関係寄りの背景 |
| CPU-Limits kill Performance (`shetty2025cpulimits`、★本文 一部) | limits を外すべきだと主張し、HPA 上の YAAS で示す | limits 除去で CPU 38%、YAAS で 51% 削減 (HR) | 背景 (limits 方針の裏付け) |

**ADASCALE** (Chen・Islam・Read・Buyya、arXiv:2607.15681、2026-07)。
- 何を解くか: クラウドとエッジにまたがる環境で、ノード間の遅延や**リクエスト型の混合比の変化**があると、どのサービスを何台にどこへ置くべきかが変わる。台数と配置を一緒に決める。
- 手法: 規則 + 最適化 (MAPE ループ。分散トレースから呼び出しグラフを推定し、SLO を満たす台数を求め、遅延が小さくなるよう配置)。2 つの時間尺度 (定常のスケール・即時の配置修正)。
- ベンチマーク: SN (27 サービス) の 3 つの root 操作 (compose-post・read-user-timeline・read-home-timeline) を wrk2 で。QPS と混合比を変える。16 VM の研究用クラウド、ノード間遅延を人工的に付与。
- 主な結果: NetMARKS Scale (配置系) 比で応答時間が最大 1.56 倍 (compose)・1.93 倍 (home)・1.34 倍 (user)。HPA 比は『latency と throughput を改善』(abstract) とあり、数値は図にあり未抽出。
- 関係: 背景。**配合の変化で支配的なサービスが変わる**という問題意識が本研究 (buy/view の配合) に最も近い。ただし対象はノード間の配置で、Pod 内の同居は扱わない。

**SHOWAR** (Baarzi & Kesidis、SoCC '21、DOI 10.1145/3472883.3486999)。
- 何を解くか: 各サービスの台数 (水平) と CPU・メモリの量 (垂直) を決め、さらにスケジューラへ『同じノードに置け／置くな』のヒントを渡す。
- 手法: 規則 + 制御理論。水平の信号は CPU 利用率ではなく**カーネルのスケジューラの待ち行列遅延 (eBPF の runq latency)**。垂直は使用量の経験的分散。affinity／anti-affinity はサービス対の**使用量の相関 (Pearson)** で生成し、相関が 20% 超変わると取り消す。
- ベンチマーク: SN (36 サービス)、TT (41)、OB (10) の 3 つを評価に使い、『結果は 3 つで一貫』として SN のみ報告 (本文 §5.1)。Wikipedia アクセストレース、Locust (別 VM から)、AWS m5.xlarge × 25 台 (24 時間の実験は 30 台)。基準は K8s 既定のオートスケーラ (HPA と VPA の組) と Google Autopilot。
- 主な結果: 資源配分が平均で最大 22% 改善 (= 費用 22% 節約と本文)、p99 エンドツーエンド遅延 −20%。Fig. 8 の費用は SHOWAR $59.23、K8s $71.76、Autopilot $76.22 の並び (図の対応は未精査)。
- 関係: 背景。相関で『同じノードに置く』相手を選ぶ点は §6.2 の負荷相関による統合と近いが、置く先は同一ノードで Pod 内ではなく、実験は複数ノード。

**SLO-Scaler** (Wang ほか、arXiv:2608.18390)。
- 何を解くか: 突発負荷では HPA が遅い (30〜90 秒) ので、予測し、かつ予測の不確かさを見て過剰・振動を避ける。
- 手法: ML (ベイズ LSTM で短期のリクエスト率・尾部遅延・SLO 違反確率を予測) + 依存グラフでボトルネックだけ増やす。
- ベンチマーク: SN (12 サービス)、Alibaba 2022 トレース由来の周期・突発・長裾の 3 パターン、各 60 分 (うち 10 分はウォームアップ)。ワーカー 5 台。基準は HPA (CPU 目標 60%)、KEDA、LSTM-Pred。
- 主な結果 (突発、表 I): SLO 違反率 HPA 15.3% → 本手法 6.7%、平均レプリカ 4.8 → 3.2、スケール回数 87 → 36、p99 347 → 238 ms。abstract は違反 −29〜56%、レプリカ −18〜33%。
- 関係: 背景。HPA の目標 60% は §13.10.4 の設定幅の一例。

**ARBITER** (Habibi & Leon-Garcia、arXiv:2607.19182)。
- 何を解くか: 負荷でなく**故障 (悪い画像の配備、下流の遅延)** に対する SLO 維持。HPA は CPU を見るので、悪い画像を増やすだけで直せない。
- 手法: 規則 (決定的な計画) と LLM の両方。OpenTelemetry の因果グラフから診断して、安全な操作の枠内で実行。
- ベンチマーク: SN (主) と OB (移植性)、4 ノード。SN は各条件 5 回、OB は 3 回。目標 400 RPS。
- 主な結果: CPU を食う悪い画像で、HPA は悪い画像を増やすか動かず、ARBITER は 5/5 回で巻き戻し。下流の故障で、HPA・資源のみの制御は下流の対象を選べない。
- 関係: HPA を負荷の追従でなく『故障対応の比較相手』に使っていて、本研究の主題 (資源効率) とは別。群: 無関係寄りの背景。

**CPU-Limits kill Performance** (Shetty ほか、SoCC '25、arXiv:2510.10747)。
- 何を解くか: CPU limits (使用量の上限) はスロットリングで性能を悪化させるので、外すべきではないか。
- 手法: 主張と実測。HPA の上に自作の autoscaler (YAAS) を載せて requests と HPA の閾値 (100 − 余裕) を管理。
- ベンチマーク: **Hotel Reservation (HR) と SN**、EC2 クラスタ。SLO は HR で 20 ms。負荷ツール・ノード数は読んだ範囲で見つからず。
- 主な結果: HR で、limits を外すだけで SLO を満たす CPU が平均 38% 減り、YAAS で 51% 減 (Fig. 4 近傍)。limits を requests に合わせると余裕のぶん requests が 25〜45% 増える (SN)。
- 関係: 背景。本研究の『limits は据え置き、requests だけ縮める』方針の傍証。**通読は未** (§3 と §4.1 の一部のみ)。

#### 13.11.3 Train-Ticket (TT) を使う 3 本 (+ SHOWAR は 13.11.2)

| 論文 (bib key) | 何をするか | 主な結果 | 本研究との関係 |
|---|---|---|---|
| COLA | (13.11.1 を参照。TT は 64 サービスで費用削減 26.25%) | | 背景 |
| PBScaler (`xie2024pbscaler`、★本文) | ボトルネックだけを見つけて台数を決める | TT で SLO 違反率が基準より平均 4.96 pt 低い | 背景 |
| Morphis (`tang2026morphis`、★本文) | 呼び出しグラフの変化に合わせて資源を配分 | HPA 比で総 CPU −38% (最大)、SLO 達成 98.8% | 背景 (配合・構造変化の参考) |

**PBScaler** (Xie ほか、arXiv:2303.14620、IEEE TSC 17(2))。
- 何を解くか: 性能悪化は呼び出しを伝って複数サービスに広がり、どれが根本のボトルネックか分かりにくいので、**ボトルネックだけ**を増やして過剰なスケールを避ける。
- 手法: 規則 + 最適化。TopoRank (トポロジに基づくランダムウォーク) でボトルネックを特定し、オフラインの最適化で台数を決める。基準は KHPA、MicroScaler、SHOWAR。
- ベンチマーク: OB と TT (40 超)。SLO は OB 500 ms、TT 200 ms。各サービス最大 8 レプリカ。負荷は Wikipedia 由来の実負荷 + 5 つの模擬負荷の計 6 種。3 台 (計 44 コア・220 GB)。
- 主な結果: 『6 負荷のうち OB で 4 つで SLO 違反が最小、3 つの模擬負荷で資源が最小』(OB の記述)。TT で SLO 違反が平均 4.96 pt 低く、費用が平均 0.24 ドル減。
- 関係: 背景。KHPA の定義『しきい値 T を資源 R に設定』は §13.10.2 のとおり。

**Morphis** (Tang ほか、arXiv:2602.01044、2026-02)。
- 何を解くか: 実運用では負荷・故障・配備で呼び出しグラフが絶えず変わる。ByteDance の 50 万本超のトレースを分析すると、実行経路は少数の**繰り返しパターン**に集中していた。これを使い、構造の変化に合わせて資源を前もって配分する。
- 手法: 機械学習 + 最適化。パターンを DBSCAN でクラスタリング、季節 ARIMA で予測し、遺伝的アルゴリズムで CPU を最小化。結果は K8s の Deployment と HPA の仕組みで適用。
- ベンチマーク: TT (41 サービス)。Locust で 3 つの負荷シナリオ (漸増・高負荷持続・スパイク + 高原)。物理 3 台 (各 64 コア・128 GB)、10 Gbps。
- 主な結果: 最新手法比で CPU −35〜38%、SLO 達成 98.8% (abstract・§1)。Fig. 12 は『HPA 比で総 CPU 最大 −38%』。
- 関係: 背景。『負荷の状態で支配するサービスや経路が入れ替わる』点は本研究の配合変化と同じ問題意識だが、扱うのはグラフ構造の変化で、Pod 内の同居ではない。

#### 13.11.4 Bookinfo (BI) を使う 2 本

| 論文 (bib key) | 何をするか | 主な結果 | 本研究との関係 |
|---|---|---|---|
| COLA | (13.11.1 を参照。BI は 4 サービスで費用削減 18.01%) | | 背景 |
| Graph-PHPA (`nguyen2022graphphpa`、★本文) | LSTM と GNN で負荷と資源を予測して台数を先に決める | 規則ベースの HPA より資源を節約 (数値は要約に無し) | 背景 |

**Graph-PHPA** (Nguyen・Zhu・Liu、arXiv:2209.02551、2022-09)。
- 何を解くか: HPA は事後対応 (リアクティブ) で、サービス間の依存を見ない。依存を考えて**先回りして**台数を決める。
- 手法: ML。負荷予測 (LSTM)、サービス間の依存を使った資源使用量の予測 (GCN)、両者を統合して Pod 数を計算。
- ベンチマーク: Bookinfo (4 サービス)。AWS 上で Kubernetes、Prometheus・Grafana。実データ由来のリアルタイム負荷。基準は規則ベースの K8s HPA (CPU 70% と 90% の 2 つ)。
- 主な結果: 『資源節約で優れる』と書くが、abstract・結論に %は無く、図 4 (productpage の Pod 数、90% と 70%) の比較のみ。HPA を 90% にすると Pod は減るが、過負荷の危険が高いと本人が記述。
- 関係: 背景。規模が小さい (4 サービス) 点で、本研究の OB・SS の代用にならない。

#### 13.11.5 全体で分かったこと

1. **衝突はなく、同居を扱う論文もない。** 14 本は『台数・配置・資源量をどう決めるか』の研究で、1 Pod 内のコンテナ構成は変数ではない。
2. **HPA は 14 本中ほぼ全てが『比較の基準』。** HPA を土台にして仕組みを分析するのは Buzato & Goldman と CPU-Limits (YAAS)。ARBITER は HPA を故障対応の比較に使う。
3. **配合 (リクエスト型の比) を変えるのは ADASCALE だけ。** 同じ問題意識 (配合が変わると主役のサービスが入れ替わる) は ADASCALE・Morphis・SHOWAR (相関) にあるが、いずれも同居の損得には結びつけていない。本研究の配合軸は、ここで先行例が薄い領域に当たる。
4. **指標は SLO 違反・応答時間・総 CPU・レプリカ数が中心で、softirq やリクエストあたりの通信 CPU は無い。**
5. **アプリで利得が大きく違う (COLA: SS 1.34% 対 OB 33.11%)。** 2 つのアプリを使い、結果をアプリごとに分けて書く本研究の方針 (OB・SS) は妥当で、アプリ間の差を限界に書く価値がある (原因は推測であり断定しない)。

**検索の範囲**: 新規検索なし (§13.10.7 と同じ)。今回は既存 PDF の再読のみ。SHOWAR は `pdf/showar.pdf` を新たに抽出して確認した (以前の抽出は壊れていた)。Buzato の thesis (修士論文) は再取得していない。

### 13.12 HPA の増設窓・減少窓・同期周期などの設定は、先行研究の本文に書かれているか (2026-11-13、依頼: 本研究の増設窓 30 s／減少窓 60 s が先行例から見て妥当かを知る)

> **読んだ範囲 (2026-11-13 追記、担当への追加質問の回答)**: 全文通読 0 本。27 本すべて「pdftotext の文字列を grep し、ヒットした段落の前後だけ読んだ」段階。図・表の画像は 1 つも見ていない。arXiv 版の版番号・公刊版との同一性は未照合。Horn 2022・gym-hpa は本文未取得 (手元の gym.pdf は別論文)。したがって本節の「記載なし」は「本文の grep と該当段落に無かった」の意味で、「窓を設定していない」の意味ではない。見落としの恐れが大きいもの: 付録・公刊版で増補の可能性 (COLA・PBScaler・SHOWAR・CPU-Limits・MS-RA・Punniyamoorthy)、設定が表/図にある可能性 (ScalerEval・Dashtbani・STaleX・Morphis・ADASCALE・SLO-Scaler)、語のゆれ (Joyce・KARMA・Graph-PHPA)、layout 抽出のまま (Serracanta)、ファイルの同定未確認 (Waterfall = goli2.pdf)。公開コード (yaml) は全論文で未確認。

**範囲**: 新規検索なし。§13.10 の 29 本のうち、PDF／本文を取得できた 27 本 (Horn・gym-hpa の 2 本は未取得) を `pdftotext` し、語 (stabiliz, cooldown, cool-down, downscal, upscal, scale-down, sync-period, scaleUp, scaleDown, tolerance, hysteresis, polling, interval, behavior, delay、数値 + s／min) で grep し、ヒット箇所の前後を読んだ。**全文精読ではない。** 確認度は「★本文 grep (2026-11-13)」。公開コード (GitHub の yaml) は**今回は見ていない**ので、『記載なし』は『論文本文に無い』の意味で、『論文が窓を既定のまま使った』とは限らない。
**用語 (初学者向け)**: HPA は 15 秒ごとに『必要台数』を計算する。**減少窓** (scaleDown の stabilizationWindowSeconds、既定 300 s) = 台数を減らすとき、過去この秒数のうち**最大**の必要台数に合わせる (すぐ減らさない)。**増設窓** (scaleUp の同、既定 0 s) = 増やすときの同様の平滑化 (既定は無し = すぐ増やす)。**許容幅** (tolerance、既定 0.1) = 目標との比が 1±0.1 の内側なら何もしない。

#### 13.12.0 結論 (先に)

1. **HPA の増設窓・減少窓を数値で明記した論文は、確認できた 27 本のうち 2 本だけ。14 本 (§13.11) では 1 本だけ。** (a) NimbusGuard (`wanigasooriya2026nimbusguard`、**§13.11 の 14 本には入らない**。自作アプリ・KinD 1 台) = 『HPA: CPU 70% または メモリ 80%、**30 秒の stabilization window**。KEDA: polling 30 s・cooldown 30 s』(Table の説明)、(b) MS-RA (`nunes2024`、SS) = 『HPA の stabilization-time を HPA-A・B は **2 分未満**、HPA-C は **1 分未満**』と書く (厳密な値は無い。しかも『台数が 20 のまま下がらなかった』と報告)。
2. **増設窓 (scaleUp) に触れた論文は 0 本。** 減少窓の数値も上の 2 本だけ。**policies (Pods／Percent per period)、HPA の同期周期の変更、metrics-server の解像度の変更、`behavior` の語は、14 本では 0 本** (grep)。
3. **『既定のまま』と言葉で書いたものは 3 本**: AutoSLO (`li2026autoslo`) 『CPU 利用率を固定の目標値 (80%) で、**default, unmodified Kubernetes controller**』、SHOWAR (`baarzi2021showar`) 『default Kubernetes autoscalers』(目標 65% は『よく推奨される値』)、Nguyen 2020 (`nguyen2020hpa`) 『新しい Pod は少なくとも downscale delay (**5 分**、既定) 動かし続ける』と既定として記述。**残りの大多数は窓の語がそもそも無い** = 既定のまま使ったと推定されるが、論文は何も言っていない。
4. **台数に影響する他の設定は少し書かれている**: 目標 CPU% (10〜90%、20/50/80%、25/50/60/70%、50%、60%、65%、70%、80%、150% (Buzato) など。各論文で違う)、max レプリカ (Dashtbani 20、Buzato 1〜4、ARBITER 5〜6、Platformatic 4〜20、Joyce 2〜50、Nguyen 2020 4〜24)。**目標値は不揃いで、標準値は無い。**
5. **自作スケーラ側の制御周期・クールダウン (比較用)**: SLO-Scaler = クールダウン 60 s、scale-down は 3 窓連続が条件、Prometheus 5 s／NimbusGuard = 15 s 周期 + stabilization、HPA に合わせた KEDA 30 s／Platformatic = HPA・KEDA の polling 15 s (KEDA の既定 30 s を 15 s に下げたと明記)／AutoSLO = 1 分周期／MAS-H2 = 300 s 周期／COLA = メトリクス取得 1 分／SHOWAR = runq 1 s 採取・5 分窓。
6. **本研究の 30 s (増設) ／60 s (減少) は、先行例の中では『短い側だが外れていない』。ただし先行研究は理由を述べていない (ので『先行例が支持』とまでは言えない)。** 比較できる数値は NimbusGuard の 30 s (HPA、増設・減少の別は不明)、MS-RA の 1〜2 分未満 (減少)、SLO-Scaler の 60 s (自作の cooldown) の 3 つで、いずれも『既定 (減少 300 s) より短く、1 分前後』という点で本研究と同じ大きさ。これは先行例の『分布』ではなく**事例が 3 つある**という水準なので、書き方は §13.12.3 のとおり。

#### 13.12.1 論文ごとの表 (§13.10.2 の番号順。HPA の位置 = 基準／改良／土台)

凡例: 「記載なし」= 本文の grep (上の語) とヒット箇所の読みで窓・policies・同期周期の記述が見つからなかった。確認度の ★本文 = pdftotext + grep + 該当段落を読んだ (2026-11-13)。「未取得」= PDF が手元に無く、または別の論文だった。

| # | 論文 (bib key) | HPA の位置 | 増設窓 | 減少窓 | policies／同期周期／取得周期 | 目標%・min/max | 窓の扱い・出所 | 確認度 |
|---|---|---|---|---|---|---|---|---|
| 1 | COLA (`sachidananda2022cola`) | 基準 (CPU 10〜90% を掃引) | 記載なし | 記載なし | 自分の metrics agent は 1 分ごと (§4.1)。『負荷が変わってから台数が反応するまで 60〜90 秒』(評価の議論の段落) | 10/30/50/70/90% | 窓の記述なし。60〜90 秒の遅れは窓でなく測定上の遅れとして記述 | ★本文 grep |
| 2 | PBScaler (`xie2024pbscaler`) | 基準 (KHPA = n=⌈ΣU/T⌉ と定義、4.1.4) | 記載なし | 記載なし | Prometheus 5 s (自作の観測)、トポロジ更新 15 s。HPA の周期の記載なし | しきい値 T を掃引 (『既定は CPU』)。台数範囲の記載なし | 窓なし。`tolerance to noise α` は**PBScaler 自身のパラメータで HPA の許容幅ではない** | ★本文 grep |
| 3 | Smart HPA (`ahmad2024smarthpa`) | 改良 | 記載なし | 記載なし | 記載なし (metrics-server の語のみ) | 資源しきい値 (TMV) と minR／maxR をサービスごとに指定 | 窓なし | ★本文 grep |
| 4 | SecureSmart HPA (`ahmad2025securesmart`、bib 未登録) | 改良 | 記載なし | 記載なし | 記載なし | CPU 50% (5R-50% 等の表記)、サービスごとの minR／maxR | 窓なし (『stabilizes』は結果の語) | ★本文 grep |
| 5 | ScalerEval (`xie2026scalereval`) | 基準 (KHPA 20/50/80%) | 記載なし | 記載なし | 記載なし | 20/50/80% | **4 頁の短報で、HPA の設定は 3 つの目標値だけ** | ★本文 grep |
| 6 | Dashtbani 2025 (`dashtbani2025`) | 基準 (KHPA 他 6 手法) | 記載なし | 記載なし | 記載なし。**起動 CPU を避けるため boot／health check を設定**したと書く (G3) | 目標 50%、max pods 20 (KHPA)、requests 100m／limits 300m | 窓なし。JVM 起動の暴走は窓ではなく probe で抑えたと記述 | ★本文 grep |
| 7 | STaleX (`dashtbani2025stalex`) | 基準 | 記載なし | 記載なし | PID の制御周期をサービスの起動時間に合わせて調整 (自作側)。監視窓 5 分 (入力) | 一律 25/50/60/70% | HPA の窓なし | ★本文 grep |
| 8 | MS-RA (`nunes2024`) | 基準 | 記載なし | **HPA-A・B は 2 分未満、HPA-C は 1 分未満** (『stabilization-time parameter … delay between a scale-down trigger and the execution』、結果の段落、Fig. 2(c) の説明) | 記載なし | HPA-A/B/C の 3 設定 (しきい値の違い)、台数は『20 のまま』 | **窓を明記。ただし数値は上限のみ (『less than』)。『窓を過ぎても 20 台から下がらなかった』と報告**。K8s の既定 300 s とは別の値を使った例 | ★本文 grep |
| 9 | Waterfall (`goli2021waterfall`) | 基準 | 記載なし | 記載なし | 『monitoring interval』の語は多数あるが**値の記載なし** (自作と HPA の双方に共通) | CPU しきい値を共通に設定 (値は図に) | 窓なし | ★本文 grep (goli2.pdf) |
| 10 | Horn ほか (`horn2022moha`) | 基準 | — | — | — | — | **PDF 未取得 (abstract のみ)。未確認** | abstract のみ |
| 11 | Buzato & Goldman (`buzato2026ijnc`) | 土台 | 記載なし | 記載なし | 『K8s の増設・減設アルゴリズムは公式 doc を参照』と注 9 (kubernetes.io HPA ページ、閲覧 2024-10-06) | 目標 CPU／メモリ 150%、**1〜4 Pod** (§4.2) | 『公式 doc 参照』= 既定のまま使ったと読めるが**明記はない** | ★本文 grep・該当段落読了 |
| 12 | ADASCALE (`chen2026adascale`) | 基準 (K8s HPA) | 記載なし | 記載なし | 記載なし (自作は steady-state autoscaling loop と配置 loop の 2 段で、周期の数値は読んだ範囲で未確認) | 記載なし | HPA は『制御ループが台数を需要に合わせる』という説明のみ | ★本文 grep |
| 13 | Graph-PHPA (`nguyen2022graphphpa`) | 基準 (『ルールベースの HPA』) | 記載なし | 記載なし | 取得 1 分 (自作)。HPA の周期の記載なし | 記載なし | 窓なし | ★本文 grep |
| 14 | SHOWAR (`baarzi2021showar`) | 基準 (default Kubernetes autoscalers = HPA／Autopilot) | 記載なし | 記載なし | 本文に**一般論として cool-down を説明** (『一部の自動増減は直近の操作後しばらく操作しない cool-down を持つ』、脚注 3 に hysteresis)。自作は runq 1 s 採取・5 分窓・β=10% 刻み・α=20% の不感帯 | 目標 65% (『よく推奨される』と書く) | **HPA 自身の窓の記載なし。自作側の α=20% 不感帯が K8s の許容幅 0.1 に相当する発想** | ★本文 grep |
| 15 | SLO-Scaler (`wang2026sloscaler`) | 基準 (HPA 目標 60%、KEDA、LSTM-Pred) | 記載なし | 記載なし | Prometheus 5 s。**自作の cooldown 60 s、scale-down は 3 窓連続** (式の説明) | 60% | HPA の窓の記載なし。自作の cooldown は 60 s | ★本文 grep |
| 16 | ARBITER (`habibi2026arbiter`) | 基準 | 記載なし | 記載なし | 自作は制御周期ごと・レート制限 | 50% (nginx-thrift)、max 5〜6 | 窓なし | ★本文 grep |
| 17 | Morphis (`tang2026morphis`) | 基準 (HPA 80%) | 記載なし | 記載なし | 自作の予測は 5 分ごと更新 | 80%、『各ベースラインは推奨パラメータで設定』 | 『推奨パラメータ』= 既定と読めるが窓は書かない | ★本文 grep |
| 18 | MAS-H2 (`hamzeh2026mash2`) | 基準 (HPA + Cluster Autoscaler) | 記載なし | 記載なし | 自作は 300 s 周期 (『Sleep(300)』) | 80% | 窓なし | ★本文 grep |
| 19 | NimbusGuard (`wanigasooriya2026nimbusguard`) | 基準 (HPA、KEDA、DQN) | 『30 秒の stabilization window』(増設・減少の別は**書かれていない**) | 同左 | 自作は 15 秒周期 + stabilization period + 必須の cool-down、Prometheus scrape 15 s。KEDA は polling 30 s・cooldown 30 s で『HPA に合わせた』と明記 | HPA は CPU 70% または メモリ 80% | **窓を数値で明記 (30 s)**。ただし増設／減少の別が不明で、HPA の `behavior` に設定したのかは不明 | ★本文 grep・段落読了 |
| 20 | KARMA (`soule2025karma`) | 基準 (KHPA 他) | 記載なし | 記載なし | 記載なし | 記載なし | 窓なし | ★本文 grep |
| 21 | NeuroScaler (`chaves2026neuroscaler`) | 基準 | 記載なし | 記載なし | 記載なし (『polling interval』は NeuroScaler 側の設定語) | 記載なし | 窓なし | ★本文 grep |
| 22 | Platformatic (`tymoshenko2026platformatic`) | 基準 (HPA 70%、KEDA、自作 ICC) | 記載なし | 記載なし | **Table 10: HPA の polling = 15 s (『HPA default』)**。KEDA は既定 30 s を 15 s に下げたと明記 | CPU 70%、**min 4 / max 20**、新 Pod は Envoy の 30 s linear slow start で徐々に流す | 窓の記載なし。『HPA は既定の 15 s』と明記した数少ない例。自作側に stabilization weight や『cooldown を使わない理由』の議論 | ★本文 grep・表を読了 |
| 23 | Punniyamoorthy ほか (`punniyamoorthy2025slocost`) | 基準 (既定の HPA と調整済み HPA) | 記載なし | 記載なし | 『調整済み HPA = 手作業で**しきい値と stabilization parameters** を調整』と書くが**値なし**。自作側は『stabilization windows、step limits、cooldown』を安全策とする | 記載なし | **窓を調整したと書くが数値なし** (『Baselines』節)。窓の値を知るには著者の追加資料が要る | ★本文 grep |
| 24 | CPU-Limits (`shetty2025cpulimits`) | 土台 (HPA の上に YAAS) | 記載なし | 記載なし | 記載なし。『hysteresis が必要』と一般論のみ | しきい値 = (100 − margin) を掃引。requests・limits を掃引 | 窓なし | ★本文 grep |
| 25 | AutoSLO (`li2026autoslo`) | 基準 | 記載なし | 記載なし | 自作は 1 分周期 (2 分以内に是正と記述) | **CPU 80%**。『Nguyen らに従い、固定の目標値と **default, unmodified Kubernetes controller**』 | **『既定のまま』と明記** (3 本のうちの 1) | ★本文 grep・段落読了 |
| 26 | gym-hpa (`santos2023gymhpa`) | 基準 | — | — | — | — | **手元の PDF は別の論文 (RL の負荷分散) で、gym-hpa の本文は未取得。未確認** | 未取得 |
| 27 | Nguyen 2020 (`nguyen2020hpa`、Sensors) | 土台 (HPA の挙動分析) | 記載なし | **既定 5 分** (『each newly created pod is kept running for at least a downscale delay period … set at 5 min』) | 同期 15 s (『By default, HPA checks the metric value every 15 s』)。**metrics-server の取得周期を 15/30/60 s で振る実験**あり (既定 60 s と記述、K8s 1.15.1) | 目標 60m (CPU)、台数 4〜24、実験 300 s | **既定値を数値で記述。取得周期の実験があり、最も詳しい**。ただし K8s 1.15 の時代の記述 (現行 v1.32 とは取得周期の既定が異なる) | ★本文 (HTML) grep・段落読了 |
| 28 | Serracanta ほか (`serracanta2025hpastability`) | 土台 (制御理論モデル) | 記載なし | 記載なし | 記載なし (モデルの時間刻みの語なし) | 記載なし | 窓なし | ★本文 grep |
| 29 | Joyce & Sebastian (`joyce2024hpaml`) | 土台 | 記載なし | 記載なし | **『horizontal-pod-autoscaler-sync-period の既定 15 秒』と説明 (§4)**。変更したかは不明 | min 2 / max 50 (replicas)、CPU request=limit=100m | 同期周期の既定を述べるのみ | ★本文 grep |

(注) **数え直し (27 本を grep、#10 Horn・#26 gym-hpa は未取得)**: 窓を数値で明記 = 2 本 (MS-RA の減少窓 < 2 分／< 1 分、NimbusGuard の 30 s)、窓を調整したと書くが数値なし = 1 本 (Punniyamoorthy)、既定値を数値で記述 = 1 本 (Nguyen 2020 の減少 5 分)、『既定のまま』と言葉で書く = 3 本 (AutoSLO・SHOWAR・Nguyen 2020 の既定への言及)、同期周期を数値で記述 = 3 本 (Nguyen 2020・Platformatic・Joyce、いずれも 15 s)、残りは窓・周期の記載なし。**§13.11 の 14 本の中では、窓の数値を書いたのは MS-RA の 1 本のみ。**

#### 13.12.2 本研究の設定との比較

| 設定 | K8s 既定 | 本研究 | 先行例 (本文で確認できたもの) |
|---|---|---|---|
| 増設窓 (scaleUp) | 0 s | 30 s | **0 本** (NimbusGuard の『30 s stabilization window』は増設・減少の別が不明) |
| 減少窓 (scaleDown) | 300 s | 60 s | MS-RA < 2 分／< 1 分 (SS)、NimbusGuard 30 s (自作アプリ)。Nguyen 2020 は既定 5 分と記述。SLO-Scaler の自作 cooldown 60 s |
| 同期周期 | 15 s | (既定) | Platformatic・Nguyen 2020・Joyce が既定 15 s と記述 |
| 許容幅 | 0.1 | (既定、v1.32 は変更不可) | HPA の許容幅に触れる論文は 0 本 (SHOWAR の自作 α=20% が類似) |
| 目標% | 80% が例示 | 70% | 20〜150% で不揃い。70% は Platformatic・NimbusGuard (CPU)、60% は SLO-Scaler、65% は SHOWAR、80% は Morphis・AutoSLO・MAS-H2 |
| min/max | 1〜∞ | 1〜12 | max 4〜50 (Dashtbani 20、Platformatic 20、Joyce 50 ほか) |

#### 13.12.3 査読で聞かれたときの答え方 (私の整理。論文の主張ではない)

1. **事実 (一次資料)**: K8s の既定は『減少 300 s、増設 0 s』。公式 doc の原文 (§13.12.4) と API リファレンスで確認した。**本研究は既定から外している**ので、設定として方法節に明記する (§9.22)。
2. **理由 (本研究の実験設計から。論文にも書ける)**: 計測窓が 240 s、ウォームアップが 180 s なので、既定の減少窓 300 s のままだと、**計測窓の中で台数が減るかどうかを観測できない** (一度増えた台数が窓の間ずっと保たれる)。台数の増減の応答を見るために短くした、と書く。(これは計算上の事実で、他の論文は同じ理由を書いていない。)
3. **先行研究との関係**: 『窓を短くした先行例が多数ある』とは**言えない**。言えるのは『先行研究の大多数は窓を書かない (既定と推定)。書いた少数 (MS-RA の < 1〜2 分、NimbusGuard の 30 s、SLO-Scaler の cooldown 60 s) は 1 分前後で、本研究と大きさは同程度』まで。
4. **外れ値でないことの根拠と限界**: 事例が 3 つで分布とは呼べない。窓の値は結果 (台数の増え方・SLO 違反) に効くので、**限界節に『窓を既定から変えたこと、窓を変えたときの感度は測っていないこと』を書く** (測るなら窓だけ振る追加実験が要る。ここでは提案のみ)。
5. **想定される追及**: 『減少窓が短いと台数が揺れる (flapping) のでは』→ 公式 doc は窓を『flapping を抑える』ものと説明する (§13.12.4)。本研究の減少窓 60 s は『既定の 1/5』で、flapping の抑制は弱まる。計測窓中の台数の時系列を示して、揺れが結果に効いていないことを示す。

#### 13.12.4 Kubernetes 公式ドキュメントの原文 (★原文を取得して確認 2026-11-13。技術資料であり学術文献ではない)

出所: `https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/` (2026-11-13 に curl で HTML を取得し、本文を抽出して確認。ページには『Stable since Kubernetes v1.37』の表示があり、**今の版のページ。本研究は v1.32**。`behavior` は v1.23 から stable、**設定可能な tolerance は v1.33 で初出なので v1.32 には無い** (doc の Tolerance 節の記述))。API リファレンス: `https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/horizontal-pod-autoscaler-v2/`。

- **Stabilization window**: 『The stabilization window is used to restrict the flapping of replica count when the metrics used for scaling keep fluctuating. The autoscaling algorithm uses this window to infer a previous desired state and avoid unwanted changes to workload scale.』／『When the metrics indicate that the target should be scaled down the algorithm looks into previously computed desired states, and uses the highest value from the specified interval. In the above example, all desired states from the past 5 minutes will be considered. This approximates a rolling maximum, and avoids having the scaling algorithm frequently remove Pods only to trigger recreating an equivalent Pod just moments later.』
- **Default behavior**: 『For scaling down the stabilization window is 300 seconds (or the value of the `--horizontal-pod-autoscaler-downscale-stabilization` command line option, if provided). There is only a single policy for scaling down which allows a 100% of the currently running replicas to be removed … For scaling up there is no stabilization window. When the metrics indicate that the target should be scaled up the target is scaled up immediately. There are 2 policies where 4 pods or a 100% of the currently running replicas may at most be added every 15 seconds till the HPA reaches its steady state.』(YAML: scaleDown `stabilizationWindowSeconds: 300`、Percent 100 / 15 s。scaleUp `stabilizationWindowSeconds: 0`、Percent 100 / 15 s と Pods 4 / 15 s、selectPolicy Max)
- **Algorithm details (旧フラグ)**: 『The controller considers all recommendations within a configurable window choosing the highest recommendation from within that window. You can configure this value using the `--horizontal-pod-autoscaler-downscale-stabilization` command line option, which defaults to 5 minutes.』
- **同期周期**: 『The interval is set by the `--horizontal-pod-autoscaler-sync-period` parameter to the kube-controller-manager (and the default interval is 15 seconds).』
- **許容幅**: 『The control plane skips any scaling action if the ratio is sufficiently close to 1.0 (within a configurable tolerance, 0.1 by default).』
- **初期化期間 (起動直後の CPU の扱い、§12.2 に関連)**: 『--horizontal-pod-autoscaler-cpu-initialization-period … its default is 5 minutes』(Ready の状態や測定時刻によって除外される条件付き。詳細は §12.2)。
- **API リファレンスの `stabilizationWindowSeconds`**: 『the number of seconds for which past recommendations should be considered while scaling up or scaling down. … must be greater than or equal to zero and less than or equal to 3600 (one hour). If not set, use the default values: - For scale up: 0 (i.e. no stabilization is done). - For scale down: 300 (i.e. the stabilization window is 300 seconds long).』

**注意**: 公式 doc は『減少窓が過去の最大を使う』とは書くが、『増設窓が過去の最小を使う』とは (今回取得した版では) 書いていない。増設窓の意味 (最小を使う) は私の理解で、**引用する前に K8s のソース (`pkg/controller/podautoscaler/horizontal.go` の stabilizeRecommendationWithBehaviors) で確認すること。未確認。**

#### 13.12.5 確認できなかったもの

- Horn 2022 (#10)、gym-hpa (#26) の本文 (PDF 未取得。手元の `gym.pdf` は別の論文)。
- 公開コード (GitHub の yaml) での窓の設定 (全論文で未確認)。論文に書かれていなくても、リポジトリに `behavior` がある可能性がある。優先して見るなら Buzato (SS)、Dashtbani (SS)、MS-RA (SS、PBScaler の公開コード)。
- 有料・IEEE・ACM の版との差 (arXiv 版を読んだ論文は、公刊版で設定の記述が増えている可能性)。
- 増設窓が『最小』を使うことの一次資料 (上の注意)。
- grep が語の出現に基づくため、図・表の中の画像として書かれた数値は見ていない (図の中の凡例など)。

**検索の記録**: 新規の文献検索なし。WebFetch と curl で kubernetes.io の 2 ページを取得した。


#### 13.12.6 読み直しが要る論文の一覧 (2026-11-13、ユーザ指示でまとめた。§13.12 の「記載なし」を論文に書く前に片付ける)

全 27 本は「grep でヒットした段落の前後だけ」読んだ段階 (見出し直下の注記)。とくに次の 19 本は、窓の値などを見落とした恐れが大きいか、本文が無い。終わったら [x] にし、結果を §13.12.1 の表に反映する。全論文共通で、公開コード (GitHub の yaml の `behavior`) も未確認。

| 済 | 理由 | bib key | 題名 | 確かめること |
|---|---|---|---|---|
| [ ] | 付録・公刊版で増補の可能性 | `sachidananda2022cola` | COLA: Collective Autoscaling for Cloud Microservices | 公刊版 (EuroSys '24 と推定) と付録の HPA 設定 |
| [ ] | 付録・公刊版で増補の可能性 | `xie2024pbscaler` | PBScaler: A Bottleneck-Aware Autoscaling Framework for Microservice-Based Applications | IEEE TSC 版の実験設定 |
| [ ] | 付録・公刊版で増補の可能性 | `baarzi2021showar` | SHOWAR: Right-Sizing And Efficient Scheduling of Microservices | SoCC '21 公刊版の HPA 設定 (65% 以外) |
| [ ] | 付録・公刊版で増補の可能性 | `shetty2025cpulimits` | CPU-Limits kill Performance: Time to rethink Resource Control | SoCC '25 版、§3〜§5 の通読 |
| [ ] | 付録・公刊版で増補の可能性 | `nunes2024` | Self-adaptive, Requirements-driven Autoscaling of Microservices (MS-RA) | SEAMS 版、図 2(c) を画像で |
| [ ] | 付録・公刊版で増補の可能性 | `punniyamoorthy2025slocost` | An SLO Driven and Cost-Aware Autoscaling Framework for Kubernetes | 「stabilization parameters を調整」の値 (付録) |
| [ ] | 設定が表・図にある可能性 | `xie2026scalereval` | ScalerEval: Automated and Consistent Evaluation Testbed for Auto-scalers in Microservices | 表 II を画像で |
| [ ] | 設定が表・図にある可能性 | `dashtbani2025` | Key Considerations for Auto-Scaling: Lessons from Benchmark Microservices | 図 1・9・10 と設定表 |
| [ ] | 設定が表・図にある可能性 | `dashtbani2025stalex` | STaleX: A Spatiotemporal-Aware Adaptive Auto-scaling Framework for Microservices | 予備実験の表の値 |
| [ ] | 設定が表・図にある可能性 | `tang2026morphis` | Morphis: SLO-Aware Resource Scheduling for Microservices with Time-Varying Call Graphs | 「recommended parameters」の中身 |
| [ ] | 設定が表・図にある可能性 | `chen2026adascale` | ADASCALE: An Adaptive Scaling and Placement Framework for Microservices Under Dynamics | 設定表の有無、HPA 比の図 5 |
| [ ] | 設定が表・図にある可能性 | `wang2026sloscaler` | SLO-Scaler: Uncertainty-Aware SLO-Driven Autoscaling for Microservices | HPA ベースラインの設定表 |
| [ ] | 語のゆれで検索漏れの可能性 | `joyce2024hpaml` | An Experimental Evaluation of Horizontal Pod Autoscaler for Diverse Machine Learning Workloads in Kubernetes | scale-in / cool off / delay で再検索 |
| [ ] | 語のゆれで検索漏れの可能性 | `soule2025karma` | Streamlining Resilient Kubernetes Autoscaling with Multi-Agent Systems via an Automated Online Design Framework (KARMA) | 同上 |
| [ ] | 語のゆれで検索漏れの可能性 | `nguyen2022graphphpa` | Graph-PHPA: Graph-based Proactive Horizontal Pod Autoscaling for Microservices using LSTM-GNN | 同上 |
| [ ] | 抽出が不十分 | `serracanta2025hpastability` | On the Stability of the Kubernetes Horizontal Autoscaler Control Loop | raw 抽出で再検索 |
| [x] (2026-11-14: 手元 goli2.pdf の表題・DOI 10.5220/0010407701900198 が一致) | ファイルの同定が未確認 | `goli2021waterfall` | A Holistic Machine Learning-based Autoscaling Approach for Microservice Applications (Waterfall, CLOSER 2021) | 手元 goli2.pdf がこの論文か |
| [ ] | 本文未取得 | `horn2022moha` | Multi-objective Hybrid Autoscaling of Microservices in Kubernetes Clusters (Euro-Par '22) | 本文の入手 (手元 gym.pdf は別論文) |
| [ ] | 本文未取得 | `santos2023gymhpa` | gym-hpa: Efficient Auto-Scaling via Reinforcement Learning for Complex Microservice-based Applications in Kubernetes (NOMS '23) | 本文の入手 |


### 13.13 SN + HPA の先行研究は、スケーリングの対象外・入口 (nginx-thrift)・HPA 設定をどう扱ったか (2026-11-16、依頼: 本研究の SN 試し (§9.25) で入口 nginx が詰まったことの先行例)

**結論 (先に)**: 読んだ 5 本 + 4 本 (計 9 本) のうち、**「DB・キャッシュ・jaeger をスケーリングの対象から外した」と明記した論文は 0 本**。入口 nginx-thrift を「台数固定にした」「枠を大きくした」「keep-alive を切った」と書いた論文も **0 本**。HPA を実際に K8s 上で動かした 3 本 (SHOWAR・SLO-Scaler・Shetty) も、min/max replicas・requests/limits・stabilization の値は大半が **記載なし**。例外は ARBITER (入口 nginx-thrift **だけ**に HPA、CPU 50%、max 5 または 6) と SHOWAR (K8s 基準の目標 65%、「全マイクロサービスに適用」と読める) くらい。つまり『SN で HPA を回すなら全部に掛ける』が暗黙の既定で、本研究の「処理用 12 サービスだけ・DB 等は対象外」は先行研究では**明示されていない選択**。入口が詰まる問題に触れた論文は 0 本、ただし **SHOWAR は K8s 基準が nginx を 16 台まで増やしたと書いており (p.438 付近)、入口にも HPA が掛かり増台できていた**。

確認度は全て ★原典 PDF (pdftotext + 全文 grep + 該当節の精読)。図・表の画像中の数値は読んでいない。**「記載なし」= 本文テキストの grep で出なかった (付録・公開コード・図の中は未確認)**。

| 論文 (bib key) | 対象外にしたもの | 入口 (nginx-thrift) の扱い | HPA／オートスケーラ設定 | 記載箇所 | 読んだ範囲 |
|---|---|---|---|---|---|
| ADASCALE (`chen2026adascale`、arXiv:2607.15681、2026-07) | **記載なし**。DB・cache に関する明示的な除外は無い (§III で stateless/stateful 両方を `S` に含めると定義、§IV-B で「stateful services があるので byte counter を使う」とだけ) | **記載なし**。root 操作の入口 S0 を通常のサービスとして扱う。台数固定とも増設とも書かない。wrk2 の接続数・keep-alive も記載なし | HPA 基準の設定 (指標・目標・min/max・requests/limits) は**全て記載なし**。HPA の説明は §VI-D-1 に 1 文 (『Deployment/StatefulSet の Pod 数を需要に合わせる制御ループ』) のみ。自法の目標は ρmax (例 0.7、CPU)、下限 x_min は記号のみで値なし (§V-B、Alg. 1) | §VI-A (16 VM、K8s v1.27/1.28、Calico、Istio 1.20.3)、§VI-D-1、§V-B | 全文 (15 頁相当、主に §III–§VI) |
| SHOWAR (`baarzi2021showar`、SoCC '21) | **記載なし** (SN の Fig. 1 に Memcached・MongoDB・Nginx が出るが、どれを自動調整の対象外にしたかの記述は無い)。垂直・水平の実験は「各マイクロサービス」と書く | **Nginx にも HPA が効いた**。『K8s と Autopilot は nginx (front-end) に通常 16 台を設定、SHOWAR は 10 台』(§5.5 付近、Fig. 9 の直後、p.438)。増台の阻害 (接続の固定) には触れない | K8s・Autopilot とも**目標 CPU 65%** (§5.3。『よく勧められる値』、脚注 2『通常 60–75%』)。基準の式は P95 利用率の合計 ÷ 目標 (§2.1)。**min/max replicas・requests/limits・stabilization は記載なし**。評価は SN のみ報告 (OB・TT でも一貫と述べるが数値なし)、locust を別 VM から、AWS m5.xlarge × 25 台 (24 時間実験は 30 台) | §2.1 (基準の式・脚注 2)、§5.1、§5.3、§5.5 | 全文 (15 頁) |
| SLO-Scaler (`wang2026sloscaler`、arXiv:2608.18390) | **記載なし**。『SN の 12 マイクロサービス』とあるが**どの 12 かは書かれていない**。baseline HPA は『全サービスにほぼ一様に命令を出す』(§V-C、Fig. 3) → 全 12 に HPA | **記載なし**。Fig. 3 で compose-post が最多 (39 命令中 22) と書くのみ。Locust (120–280 RPS) | **HPA: CPU 目標 60%** (§IV-B)。KEDA は RPS 100/pod。**min/max replicas・requests/limits・stabilization は HPA 側は記載なし**。自法は cooldown 60 s、x_min 記号のみ、scale-down は 3 窓連続 (§III-D)。ワーカー 5 台 (8 vCPU・16 GB)、各 60 分、うち 10 分ウォームアップ | §IV-A、§IV-B、§V-C、§III-D | 全文 (約 10 頁) |
| ARBITER (`habibi2026arbiter`、arXiv:2607.19182) | **HPA を掛けたのは nginx-thrift だけ** (§8.1『HPA (50 % CPU target on nginx-thrift, max 5 replicas)』)。他サービス・DB には HPA なし (『HPA と resource-only 制御は露出した frontend workload に作用する』、§8.2)。DSB の約 25 サービスのうち 1 つ | **入口だけが HPA の対象**。台数: 開始 1 台 (§8.3『one clean nginx-thrift replica』)、max 5 (回帰実験)・max 6 (配置実験、§8.3)。CPU 負荷の悪い画像で『毎回 max の 5 台まで増える』(§8.1)。**接続・keep-alive は記載なし** (wrk2 は 400 RPS、配置実験は 800 RPS。スレッド数・接続数は書かれていない) | 目標 CPU 50%、max 5 (または 6)、min は開始 1 台から 1 と読めるが明記なし。**requests/limits・stabilization は記載なし**。4 ノードの K8s。なお OB の実験は frontend の request/limit を 100m ずつ増やす (§8.6) | §7 (評価の方法)、§8.1、§8.2、§8.3、§8.6 | 全文 (15 頁)。ただし設定表・付録は無し |
| CPU-Limits kill Performance (`shetty2025cpulimits`、arXiv:2510.10747、SoCC '25) | **記載なし**。『HR の 19 Pod の 1 つに limits を付ける』(§3.2) 以外、対象外の話なし | **入口にも HPA**。Fig. 2c で『nginx-thrift の Pod は余裕 30%、user-timeline-service は 45% 必要』と**サービスごとに余裕を調整**、HPA の目標は『100 − 余裕』(§3.2 Case A)。増台の阻害は記載なし | 目標は **サービスごとに 100 − 余裕 (= nginx-thrift 70%、user-timeline 55%。引き算は私の導出で、本文は『100 − 余裕』と余裕の値のみ)**、Fig. 3c は SN で全体の閾値 60/70/90% を比較。**min/max・初期台数・stabilization は記載なし**、EC2 の台数・型も記載なし (『EC2 clusters』のみ、§3.1)。負荷ツール (wrk2 か)・接続も記載なし。YAAS は HPA の上に載せた自作 (§4) | §3.1 (Setup)、§3.2 (Case A、Fig. 2c、Fig. 3c)、§4 | 全文 (9 頁) |

**参考: 余力で読んだ 4 本**

| 論文 (bib key) | SN か | 対象外にしたもの・入口・HPA 設定 | 記載箇所 | 読んだ範囲 |
|---|---|---|---|---|
| COLA (`sachidananda2022cola`、arXiv v3) | **SN は使っていない** (Simple Web Server・BI・OB・SS・TT の 5 つ。§13.11.1 のとおり)。依頼文の「SN を使う K8s 系」には含まれない | **ingress gateway と load balancer 専用 Pod は別の node pool** に置く (費用は別計上、§5 末の訓練費用)。各 deployment は 1 台から N_i 台 (§8.17.1)、1 Pod = VM 1 台分の枠 (要求 600 mCPU・2400 MB。§5.1)。HPA の基準は deployment ごとに CPU 閾値、メモリ閾値は『性能が悪いか不安定』なので省略 (§8.x) | §5.1、§2.1、§8.17.1 | 全文を grep (39 頁。付録の表は読んでいない) |
| GRAF (`park2021graf`、CoNEXT '21) | SN (post-compose の連鎖のみを制御対象として図示、Fig. 10) と OB | **NGINX は制御グラフの節点として含まれる**。DB (MongoDB 等) の語が本文に**出ない** (記載なし)。基準の K8s autoscaler は『**全体で 1 つの閾値**を実験で決めて全サービスに適用』(§5.3)。台数 = ceil(CPU quota / CPU unit) (式 7)。Vegeta で post-compose のみ、7 台構成 (master 1 + worker) | §4 (負荷生成)、§5.1 (Experimental setup、7 台)、§5.3 (Resource saving)、式 7 (§3.7)、Fig. 10 | 全文 (14 頁、今回は完全な PDF を取得) |
| FIRM (`qiu2020firm`、OSDI '20) | DSB 全般 (SN 含む) | 基準『K8s autoscaling』と AIMD は**コンテナごとに**適用 (§4.2、『rule-based』)。設定 (閾値・min/max) は**記載なし**。DB・入口の除外は記載なし。wrk2 は『multithreaded, multiconnection』とだけ | §4.2、§3.6 (injector・wrk2) | grep + 該当段落 (20 頁。全文精読ではない) |
| Autothrottle (`wang2024autothrottle`、NSDI '24) | SN (28 サービス、Sinan の変種)、HR、TT | **K8s-CPU は HPA ではない**: 使用量 ÷ 閾値で『**CPU limit を設定**』する垂直方式 (§5.1、15 秒ごと、300 秒の最大)。台数は固定: TT・HR は各サービス 1 台、SN は media-filter-service 3 台、**大規模実験 (512 コア) のみ nginx-thrift 3 台・media-filter 6 台** (Appendix D)。閾値は 0.1–0.9 から手動で最良を選ぶ (Appendix F、表 4)。→ **水平オートスケールの先行例ではない** | §5.1、§5.5、Appendix D・F | grep + 該当節 (18 頁) |

**位置関係と本研究への示唆**
1. **本研究の「処理用 12 サービスだけに HPA」は先行研究と同じでも違ってもいない**: 対象外を明示した論文が無いので、**比べる先例が無い**。ARBITER が『入口だけ』、SHOWAR・SLO-Scaler・Shetty が『全部』と読めるので、**どちらも先例がある**と書ける。ただし DB・cache への HPA の有無は 5 本とも**記載なし**で、『先行研究も DB を除いた』と書いてはいけない。
2. **入口が詰まる問題**: 5 本とも、入口の増台が効かない (接続の固定) ことに触れていない。SHOWAR は『nginx が 16 台に増えた』、ARBITER は『入口が max (5) まで増えた』と書くので、**先行研究の環境では入口の増台は動いた**。差は負荷側の接続の張り方と推定されるが、**どの論文も wrk2/Locust の接続数・keep-alive を書いていない** (ARBITER・SHOWAR・SLO-Scaler・Shetty とも記載なし)。Locust は 1 ユーザ 1 接続で、ユーザ数が多ければ接続が分散する (Locust の仕様。論文では未確認)。k6・wrk2 の少数接続との違いは仮説。
3. **HPA の既定の枠**: 5 本とも requests/limits を書かない (ARBITER が OB で +100m と書く以外)。本研究の『Helm 既定 100m/100m で入口が上限に張り付く』は先行研究では見えない。Shetty の『nginx-thrift は余裕 30%』は、**入口は他より余裕を小さくできる (= 目標を高くできる)** と読める一方、枠の絶対値は不明。
4. **Autothrottle の K8s-CPU は HPA ではなく垂直** (§13.10 の表で『HPA そのものかは未確認』とした点を今回確認して訂正)。HPA の台数を競った論文として引用してはいけない。

**検索の記録**: 新規の文献検索なし。手元の PDF (§13.11 で取得済みの arXiv・USENIX・ACM のもの。ADASCALE 2607.15681、SLO-Scaler 2608.18390、ARBITER 2607.19182、Shetty 2510.10747、SHOWAR・COLA・GRAF 2008.08509 [FIRM]・Autothrottle) を pdftotext (`-layout` なし) で全文変換し、`nginx|stateful|mongo|redis|memcache|jaeger|keep-alive|connection|minReplicas|maxReplicas|exclud|helm|manifest|stabiliz|HPA|threshold|limit|wrk2` で grep して該当節を精読。**未確認**: 付録・補足資料・公開コード (GitHub の yaml、特に `minReplicas`・`behavior`・manifest の出所)、図・表の画像中の数値、SHOWAR の公刊版との差。ADASCALE・SLO-Scaler・ARBITER は arXiv 版で、査読後に設定が増える可能性。


#### 13.13.1 付録・補足資料・公開コードの確認 (2026-11-16、§13.13 の「記載なし」を覆せるか)

方法: (1) PDF 本文の `github|gitlab|artifact|appendix|supplement|available at` を grep、(2) arXiv の abs ページ (Code タブ・Ancillary files の有無)、(3) GitHub API (リポジトリ・ユーザ検索)・WebSearch、(4) 見つかったリポジトリを scratchpad に浅く clone して grep (**コードは読むだけで実行していない**)。

| 論文 | 付録・補足 | 公開コード | 見つかった設定 | 前回からの変更 |
|---|---|---|---|---|
| ADASCALE (`chen2026adascale`) | PDF に Appendix なし。arXiv の Ancillary files なし | **なし**。本文に URL なし。GitHub 検索 (adascale)・WebSearch で 0 件。著者の博士論文 (Ming Chen、Melbourne、2025) に ADASCALE の章があるが、コードの記載なし (WebSearch の要約。**論文本体は未読**)。同著者の前作 TraDE のコードは `github.com/MingCHEN-Github/TraDE` (公開、2026-10-08 更新)。同アカウントに DSB のフォークがあるが、中身は upstream の helm-chart README・jaeger の values の編集のみで、HPA や ADASCALE の設定は無い (commit 一覧と README を確認)。**ADASCALE の実験との対応は確認できない** | なし | 変更なし (記載なし のまま) |
| SHOWAR (`baarzi2021showar`) | PDF に Appendix なし | **著者公式のコードは見つからず** (GitHub 検索 `showar autoscaler` で公式なし、WebSearch でも 0 件)。第三者の再現 `SZU-AdvTech-2023/232-SHOWAR-...` (Go、2024-01-24、中国の大学の授業課題の再現、README は中国語) を clone。**論文の実験とは対応しない** (著者が別、Prometheus + Istio の再実装、nginx・minReplicas・65% の設定は grep で 0 件) | なし | 変更なし |
| SLO-Scaler (`wang2026sloscaler`) | PDF に Appendix なし。Ancillary なし | **なし**。arXiv に URL なし、GitHub 検索 (`slo-scaler`) は無関係のリポジトリのみ | なし | 変更なし |
| ARBITER (`habibi2026arbiter`) | 本文 §7.2 が『supplement に run manifest・RemediationPlan CR・controller log・resource samples・wrk2 histograms・スクリプトを収めた』と明記。**supplement の実体は PDF に含まれず、arXiv にも Ancillary なし** | **URL は abstract と §7 に明記: `https://github.com/pooyan/arbiter`。2026-11-16 時点で 404** (GitHub API でも not found。著者アカウント `pooyan` (Pooyan Habibi) の公開リポジトリは 0 件 → 非公開か未公開)。WebSearch でも見つからず | なし (中身は見られず) | 『記載なし』は覆らない。**「公開と書かれているがリンク切れ」と書く** (確認日 2026-11-16)。後日再確認する価値あり (HPA の yaml・wrk2 の -c/-t が入っているはずの唯一の候補) |
| Shetty ほか (`shetty2025cpulimits`) | PDF に Appendix なし。arXiv コメント欄は『Vision Paper accepted to SoCC 2025』 | **なし** (自作 YAAS のコード・artifact 記載なし。GitHub 検索 (`yaas`) も無関係)。本文 Table 1 では他社の研究のコードの有無 (NP** = 非公開) を整理している | なし | 変更なし。『vision paper』= 実験の詳細が短いのは仕様、と書ける (arXiv のコメント欄、確認 2026-11-16) |
| GRAF (`park2021graf`) | CoNEXT 版 14 頁に Appendix なし。**ToN 拡張版**: `https://ina.kaist.ac.kr/assets/bibliography/GRAF_ton.pdf` (IEEE ToN 2024、16 頁、題 "Graph Neural Network-Based SLO-Aware Proactive Resource Autoscaling Framework for Microservices") を取得して grep: 設定の追加情報なし (Vegeta・Locust のスレッド数 250→500 など負荷の説明が増えたのみ) | **なし** (本文に URL なし、GitHub 検索 0 件) | ToN 版: Locust の追加記述 (サージ時 250→500 スレッド、別実験で 600 ユーザ・5,100 ユーザ) は OB 側。SN の HPA 設定は追加なし | 変更なし。ToN 版の存在を追加 (未精読、grep のみ) |
| FIRM (`qiu2020firm`) | arXiv 版に付録なし (grep) | **あり**: `https://gitlab.engr.illinois.edu/DEPEND/firm` (本文の結論近くに URL (節番号は未確認))。**この環境からは接続できず (curl 000、WebFetch 接続拒否) 中身は未確認**。GitHub の mirror は見つからず。Shetty の Table 1 脚注も `.../firm//blob/master/actions.py` を引く | 未確認 | 『コードあり・未確認』に更新。**自分のネットワークで clone して、K8s autoscaling の基準の設定を見る価値あり** |
| Autothrottle (`wang2024autothrottle`) | PDF に Appendix A–G あり (§13.13 で参照済み) | **あり**: `https://github.com/microsoft/autothrottle` (本文の実装の節に URL (節番号は未確認))。HEAD = d237d7f (2023-09-16)。clone して確認 | 下記 | 下記のとおり『記載なし』の一部が埋まった |

**Autothrottle のコードで見つかったこと** (ファイル・行は clone 時点 d237d7f):
- `social-network/generate-json.js` 39 行: Deployment の `replicas: 1` が既定。**HPA の YAML はリポジトリ全体で 0 件** (`grep -ri 'hpa|HorizontalPodAutoscaler|minReplicas'` が空)。→ 本文の『台数固定』をコードも裏づけ。
- 同 260 行: `media-filter-service` だけ 3 台 (worker1〜3 に 1 台ずつ)。本文 Appendix D の『3 台』と一致。大規模実験の『nginx-thrift 3 台』はリポジトリの既定では **1 台のまま** (README 107 行『replicas を変えたければ generate-json.js を編集』)。
- 同 209–222 行: `nginx-thrift` は `nodeName: worker4` (= `autothrottle-5`) に固定、`serviceType: NodePort` (8080 → 30001)。`evaluation.py` 427–430 行のコメント『autothrottle-5: nginx-thrift (see section A.3 in the paper)』。→ **入口は専用ノードに 1 台だけ置かれ、他のサービスと CPU を取り合わない**。本研究の『入口が 100m で詰まる』とは設計が違う。
- 同 105–254 行: DB・cache は `mongodb(...)`・`redis(...)`・`memcached(...)` 関数で、ほぼ全て `worker3` に固定配置 (1 台)。jaeger も `worker3` (192 行)。→ **DB・cache・jaeger は『スケールの対象外』ではなく、そもそも誰も台数を動かさない構成** (K8s-CPU 基準も垂直=CPU limit の調整のみ)。
- `generate-json.js` に `resources:`・`requests`・`limits` の記述なし (grep 0 件)。CPU limit は実行時に `worker-daemon.py` 54 行 `set_cpu_limit` が cgroup を直接書く。→ nginx-thrift の requests は**設定していない** (BestEffort 相当、私の推定)。
- 負荷: `social-network/locustfile.py` 167 行 `SocialMediaUser(FastHttpUser)`、168–171 行 `wait_time` は指数分布 (平均 `mean_iat = 1` 秒、163 行)、296–306 行 `CustomShape` が **ユーザ数 = その秒の RPS** (`user_count = RPS[int(run_time)]`、spawn_rate 100)。→ **Locust のユーザ数 ≒ RPS (1 ユーザ ≒ 1 req/s)** で、接続数は RPS に比例して増える (FastHttpUser は 1 ユーザ 1 接続のはずだが、**接続の再利用の挙動は確認していない**)。wrk2 は使っていない。
- マニフェストの出所: 自作 (JS から JSON を生成)。SN は DSB 本家ではなく **Sinan の `socialNetwork-ml-swarm` のフォーク** (`.gitmodules`: `SmartHypercube/autothrottle-social-network-src`、README 122 行)。ML 推論サービス 2 つを含む 28 サービスの変種で、本研究の DSB 6ecb097 とは別物。
- 対応の確認: コミット日 2023-09-16 は論文 (NSDI '24、2024-04) より前で、README は『evaluation を再現する』と明記。Appendix D の台数 (media-filter 3) とコードが一致。ただし**論文の数値とコードの設定の対応表はなく、「コード = 論文の実験」は部分的な確認にとどまる**。

**覆ったもの・覆らなかったもの (表)**

| 項目 | 前回 (§13.13) | 今回 |
|---|---|---|
| ADASCALE・SHOWAR・SLO-Scaler・Shetty の HPA の対象外・min/max・requests/limits・接続数 | 記載なし | **記載なしのまま**。付録なし・公式コードなしを 4 本とも確認 (範囲: PDF grep・arXiv abs・GitHub API 検索・WebSearch) |
| ARBITER | 記載なし | 記載なしのまま。**公開を謳うリポジトリがリンク切れ (404)**。supplement に入っているはずの設定は見られず |
| FIRM | 記載なし | コードの存在を確認 (GitLab)。**内容は未確認** (接続不可) |
| Autothrottle | 『K8s-CPU は HPA ではない』『台数固定』 | **コードでも確認**。DB・cache・jaeger は 1 台固定の配置、入口は専用ノードに 1 台、requests 設定なし、Locust ユーザ数 ≒ RPS。HPA ではないので『HPA の対象外』の先例にはならない |

**結論の更新**: SN で HPA を回した先行研究の「対象外・入口・requests・接続数」は、**論文本文・付録・公開コードのどこからも取れなかった** (SN+HPA の 5 本のうちコードが公開されているものは 0 本、ARBITER のみ URL を示すが 404)。Autothrottle のコードは SN 構成の実例として唯一読めるが、HPA ではなく垂直の制御で、SN の変種・専用ノードに入口を置く設計。**本研究の方法節には、設定を全て自前で書く (§9.26) のが唯一の選択肢**。

**未確認**: FIRM の GitLab (環境から接続不可)、ARBITER の supplement (リンク切れ)、ADASCALE の博士論文の章 (本文未読)、SLO-Scaler・ADASCALE の ICDCS 等の公刊版 (arXiv 版のみ)、Autothrottle の SN 変種 submodule (`autothrottle-social-network-src`) の nginx 設定 (worker_connections 等) の中身。

#### 13.13.2 SN + HPA の 5 本は負荷の種類と量をどう書いたか (2026-11-17、依頼: どの負荷をどれだけ与えたか。scratchpad の pdftotext 済み本文を grep + 該当段落を読んだ。図の中の数値は未読)

| 論文 | 負荷ツール | 種類 (compose / home / user の配合) | 量 | 時間 | 出典 (pdftotext の行、節) |
|---|---|---|---|---|---|
| ADASCALE | wrk2 | 3 種類を別々に、および混合。混合比の例は **1 : 3 : 6** (compose : user : home の順と読める、記号 λ1:λ2:λ3) | 種類ごとに QPS を上げて「膝」を探し、**約 400 / 1300 / 400 QPS** (λ1, λ2, λ3)。評価の QPS の値は図のみ | 混合は 5 分 | §V (Fig. 4)、§VI、Table I/II の前 |
| SHOWAR | Locust (別 VM から分散) | **記載なし** (Fig. 1 に composePost・readTimeline の経路図があるだけ) | Wikipedia のアクセストレース (1 時間、24 時間の実験もあり)。回/s の絶対値は図のみ | 1 時間 / 24 時間 | §5.1 "Workload and Load Generation" |
| SLO-Scaler | Locust | **記載なし** (ボトルネックが compose-post と書くので投稿を含むことだけ分かる) | Alibaba 2022 トレース由来。周期 (正弦波 **120–280 RPS**)、突発 (30–44 分に 3 倍)、長裾 (5 倍の小突発) | 60 分 (うち 10 分はウォームアップ) | §IV-A |
| ARBITER | wrk2 | 読み取り (図の経路は read-home-timeline)。配合の記載なし | **400 RPS** (特記なき場合) | 360 秒 (悪い画像のシナリオ) | §7 Benchmarks and load、§8.3 |
| Shetty ほか | **記載なし** | **記載なし** | Fig. 2c の横軸が 2000–6000 RPS (SN)。Fig. 3c は「負荷を 25% 上げる」 | 記載なし | §3 Setup、Fig. 2c・3c の説明 |

- 結論: **種類の配合を数字で書いたのは ADASCALE だけ** (1:3:6)。量は 4 本が書く (ADASCALE の膝・SLO-Scaler の範囲・ARBITER の 400・Shetty の横軸)。公式の mixed-workload (60:30:10) をそのまま使うと明記した論文は 0 本。接続数は全て記載なし (§13.13)。
- [ ] 本研究で SN を使うなら、種類の配合 (例: 公式 60:30:10)・回/s・時間・接続の張り方を全部書く。ADASCALE の「種類ごとの膝」を測る手順は、OB の buy/view の容量測定と同じ形なので方法節で並べられる。


### 13.14 計測方法が似ている HPA 研究 (2026-11-17、依頼: 目的は問わず、HPA 実験の「測り方」が本研究に似ているものを (A)(B)(C) で探し、原典で確かめる)

**対象の測り方 (ユーザ指定の 3 つ)**: **(A)** 一定の負荷をかけ、HPA が落ち着いた台数と収束時間を測る。**(B)** HPA の設定 (目標・指標・同期周期・安定化窓・min/max・requests) を変え、台数がどう変わるかを調べる (特性評価)。**(C)** 負荷を段階的に増やし、台数・遅延・失敗/取りこぼしを測る。softirq・同居の測り方は対象外。
**本研究の測り方 (比較の基準)**: k6 開ループの一定レートをウォームアップ後の計測窓だけで評価し、レートを段階的に振る / HPA 利用率と台数を 15 s ごとに時系列で記録し、窓内の台数と予約量 (requests × 台数) を出す / 同条件を 3〜12 回反復し、落ち着いた台数の一致回数 (HPA の許容幅 10% による整数閾値効果) を見る / 取りこぼし・p50/p99・増やし遅れも見る / requests を実測から決め、それで台数が決まる / 単一ノード MicroK8s 16 コア (K8s v1.32)。

**範囲の限定 (最初に)**: 系統的サーベイではない。WebSearch (extended 3・standard 6)、arXiv API (abs 検索 9 本、ほぼ既知の論文に収束)、Crossref (書誌 4 件)、既存 §13 の手元 PDF の再 grep。IEEE Xplore・ACM DL・Google Scholar は引いていない。MDPI は 403 で本文が取れなかった (Electronics 2024 は下表で「未読」)。「記載なし」= 本文テキストの grep で出なかった、の意味。

#### 13.14.0 結論 (先に)

1. **衝突 (既出) は無し。** (A)(B)(C) の測り方は、HPA の特性評価として先行例が複数ある。ただし**本研究の測り方を全部満たす論文は 0 本**。部分的に似るものが各項目に 1〜3 本ずつある (13.14.3)。
2. **最も近い 3 本 (査読あり)**: ① Nguyen ほか 2020 (`nguyen2020hpa`、Sensors) = HPA の設定を変えて台数・失敗数を時系列で見る、同条件 10 回反復、単一物理機。② COLA (`sachidananda2022cola`、OB) = 一定レートを段階的に振り、HPA の目標 10〜90% を変えて、台数と遅延を見る。③ Buzato & Goldman (`buzato2026ijnc`、SS) = 負荷 3 水準、HPA 有無、6 回反復、台数の増加率。**査読なしで最も特徴が近い**のは Wijaya (GitHub、k6 開ループ、5 回反復、HPA 目標 50/80%、time to scale)。
3. **先行例が見つからなかった部分** (13.14.4): (a) 「落ち着いた台数が N 回中 M 回同じ」と回数で数える反復の使い方、(b) HPA の許容幅 (10%) による整数台数の閾値効果、(c) 予約量 (requests × 台数) を主指標にして HPA 下の台数を比べること、(d) 台数の時系列を 15 s で記録し計測窓内の台数を取る手順の明記 (台数の採取間隔を書く論文自体が少ない)、(e) 「落ち着くまでの時間」の定義 (settling time) を明示した HPA 論文。
4. **本研究の測り方は、先行例と比べて「単一条件を厳密に反復し窓で切る」側に寄っている**。先行例の反復は 3〜10 回が多く (Nguyen 10、Buzato 6、Nilsen 3、Wijaya 5、Henning 3)、本研究の 3〜12 回は同水準。
5. **注意**: 先行例の HPA は古い K8s (Nguyen は v1.15・metrics-server 60 s)・クラウド・複数ノードが多く、**数値は比べられない**。使えるのは手順の骨格だけ。

#### 13.14.1 論文ごとの表 (近い順。(A)(B)(C) は上の定義)

凡例: 読んだ範囲 = ★本文 (PDF/HTML を pdftotext/抽出し、方法・結果の該当節を読んだ) / ★本文 grep (該当段落のみ) / README のみ / 未読。「台数の測り方」は、本文に書かれた頻度・窓。

| # | 論文 (bib key) | (A)(B)(C) | 負荷の形 | 台数の測り方 | 何を変えたか | 反復 | 環境 | 読んだ範囲 |
|---|---|---|---|---|---|---|---|---|
| 1 | Nguyen, Yeom, Kim, Park, Kim, Sensors 20(16):4621, 2020 (`nguyen2020hpa`、DOI 10.3390/s20164621) | **B・A** | **開ループ** (Gatling) の 2 段階: 最初の 100 s は約 1800 req/s、次の 100 s は約 600 req/s、残りは無負荷 (計 300 s) | 台数と平均 CPU の時系列図 (採取間隔の記載は読んだ範囲に無し。metrics-server の取得周期 60 s が値の更新周期と明記) | **metrics-server の取得周期 15/30/60 s**、指標 (CPU/メモリ vs Prometheus カスタム: HTTP 数)、クラスタ規模 (ワーカー 2 vs 4)、readiness probe の有無 (計 7 実験) | **各実験 10 回** (『精度のため』。平均か個別かは未確認) | **物理 1 台 (i7-8700) に 5 VM** (master 1 + worker 4)、K8s v1.15.1、requests 100m/limits 200m、台数 4〜24 | ★本文 (PMC7471989、方法・結果節 5.1〜5.2.7) |
| 2 | Sachidananda & Sivaraman COLA (arXiv:2112.14845、`sachidananda2022cola`) | **B・C** (+A の一部) | 「一定レート」を複数水準 (OB で 400・600 rps など)。各レート 10 分 (定常遅延の推定には 30〜60 s の標本で足りる、と付録図を参照して記述) | 台数 = VM 数 (**1 レプリカ = 1 VM 全体を要求**)。採取間隔の記載なし | **HPA の CPU 目標 10/30/50/70/90%** × 負荷水準。『目標 50% は 400 rps で 50 ms を満たすが、600 rps では 30% が要る』『OB の中央値遅延 37〜202 ms、400 rps で 88 台と 13 台』 | 記載なし (読んだ範囲) | GKE、VM 単位。OB・BI・SS・TT・単純 Web | ★本文 grep + 該当段落 (§2 HPA Shortcomings、§5 Workloads。図は未読) |
| 3 | Buzato & Goldman (`buzato2026ijnc`、IJNC) | **C** | **閉ループ** (Locust): 300/2400/4500 ユーザ (spawn 1/8/15 人/s)。10 分 = 前半 5 分で増やし後半 5 分は最大人数で保持 | 『台数の増加率』= (増えた Pod 数 − 初期 Pod 数)/初期 Pod 数 (式 (1))。Grafana の CSV。採取間隔は記載なし | HPA の有無 × 束ね 4 通り。HPA は min 1 / max 4、CPU・メモリ目標 150% | **各負荷 6 回** (箱ひげ図、『標本が少なく正規性が無いため』) | AWS EKS、t3.xlarge、2 ノード/シナリオ、K8s 1.22、SS | ★本文 (§3.1・4・4.2・5。§13.4 で既読、今回再 grep) |
| 4 | Shetty ほか CPU-Limits (`shetty2025cpulimits`、SoCC '25) | **A・B** | **段階的**: SN の負荷を「25% 上げる」 (ステップ)。到達までの時間を測る | 『スケール操作の回数』と『SLO を満たすのに要る CPU 量』(Fig. 3c) | **スケール閾値 60/70/90%**、limits の有無 | 記載なし (vision paper) | EC2、DeathStarBench SN・HR | ★本文 (§3.2 の該当段落。**Fig. 3c の数値は図なので未読**。『60% から 70% で SLO 達成までの時間が 4 倍』は本文の記述) |
| 5 | **Wijaya** (GitHub `Ignatius-Kevin-Wijaya/k8s-autoscaling-hpa-vs-keda`、2026、学部論文) | **B・C** | **開ループ** (**k6 の ramping-arrival-rate**)。『緩やか・スパイク・振動』の 12 分スケジュール。auth 2→30 req/s、shipping 10→105 req/s。評価は k6 時刻 120〜540 s | 記載なし (Prometheus 15 s 取得。HPA の CPU 値は約 1 分ごとにしか変わらないと書く)。『time to scale』・replica-seconds | **HPA の CPU 目標 80% (既定) vs 50% (速い)、指標 (CPU vs リクエスト率)、エンジン (HPA vs KEDA)**。台数 1〜5 | **5 回/条件** (計 180 run)。中央値 + 順位和検定 | AKS 3 × D4as_v5、K8s 1.33.7、自作の 2 サービス | **README のみ** (WebFetch 2026-11-17)。**査読の有無不明 (自己公開の学部論文)**。論文として引用は不向き、方法の参考 |
| 6 | Nilsen (KTH 修士論文 2023、DiVA diva2:1783247、TRITA-EECS-EX-2023:510、`nilsen2023gke`) | **C** | **閉ループ** (Locust): 最大負荷 250/500/750 rps × 立ち上げ 1/2/3 分 | 『desired replicas』の時系列 (付録 D の図)。採取間隔は未確認 | HPA (CPU 75%・リクエスト率 100 rps)、VPA、Hybrid。minReplicas = ベースラインの台数/2、maxReplicas = ベースライン台数 | **各シナリオ 3 回** (平均と標準偏差) | GKE、6 ノード n2-standard-4、Nordnet の実サービスを模した生産級マイクロサービス | ★本文一部 (要旨・方法・実装節。結果の数値は未読) |
| 7 | Serracanta ほか (`serracanta2025hpastability`、IEEE Access) | **A** | k6、20→22 VU で 20 分 (閉ループ) | CPU 使用率とアクティブ Pod 数 (縦線) の時系列図 | なし (HPA v2・CPU 80% (requests 100m)・3 段カスケード、8 ms の演算) | **1 回** (反復の記載なし) | 実機テストベッド (規模不明) | ★本文 (§V-B 全文)。『過渡期の後に CPU 利用率が目標に落ち着く』を示すが、収束時間は数値化していない |
| 8 | Podolskiy, Jindal, Gerndt (AMCS 29(2):227–244, 2019、DOI 10.2478/amcs-2019-0017、`podolskiy2019scalex`) | **A・C** | **開ループ** (自作 ScaleX): 線形増加・線形増加+一定・ランダム・三角。20 分、起点 1 req/s、増分 3 | **autoscaling latency** (必要台数 DAI と実台数 CAI が食い違う区間の長さ、t_end − t_start) を**定義**。台数は時系列 | 仮想マシン autoscaler (AWS/GCE/Azure) と K8s HPA の組合せ (多層) | 『複数回実施』し**図では 1 回分のみ**表示 (MCT 法) | クラウド VM、計算集約アプリ | ★本文 (§3 指標定義、§5.1 設定)。HPA は VM 層の後段で、HPA 単体の特性評価ではない |
| 9 | Casalicchio (Cluster Computing 22:995–1006, 2019、DOI 10.1007/s10586-018-02890-1、`casalicchio2019perf`) | **B (シミュレーション)** | 乱数生成の需要。50 制御周期 (30 s) | シミュレータが計算する台数 (最大 2000) | **Utarget 75/80/85%**、相対 vs 絶対 CPU 指標 (KHPA vs KHPA-A) | **20 回** (Matlab 乱数) | **Matlab のシミュレーション** (実 K8s ではない) | ★本文 (§2、§5.1〜5.2)。**実機の HPA ではない**ので (B) の「実測」には数えない |
| 10 | Henning & Hasselbring (JSS 2024、arXiv:2303.11088、DOI 10.1016/j.jss.2023.111879、`henning2024theodolite`)。手法は Empirical Software Engineering 2022 (DOI 10.1007/s10664-022-10162-1、未読) | **C (HPA ではない)** | **一定負荷を水準ごとに** 5 分 (最初の 2 分はウォームアップ。UC4 は 10 分・4 分) | 台数は**実験者が固定**して振る。**各負荷で SLO を満たす最小台数**を探す (resource demand metric) | 負荷水準 × 台数 | **各 3 回** (『時間と統計の妥協点』) | K8s、プライベートクラウド | ★本文 grep + 該当段落。**HPA は使わない**。本研究の「固定台数スイープ」(`fixed-replica-k6.md`) と同型の手順の先例 |
| 11 | Joyce & Sebastian (`joyce2024hpaml`、Research Square プレプリント) | A (弱い) | JMeter 100 スレッド × 200 ループ (一定、閉ループ) | 台数 (2→8 など) と CPU の図 | なし (min 2/max 50、requests=limits=100m) | 記載なし | 3 ノード、ML 推論 3 種 | ★本文 (§5)。**査読前、特性評価としては弱い**。引用は避ける |
| 12 | Dashtbani & Tahvildari STaleX (`dashtbani2025stalex`) | B | Locust + WorldCup98 | 記載なし | HPA 目標 25/50/60/70% (一律) vs サービスごと | 記載なし | 自前 K8s、SS | ★本文 grep (§13.12・本節で再 grep)。目標を振った結果、70% で応答時間 200 ms 超過 |
| 13 | Nunes ほか MS-RA (`nunes2024`、SEAMS '24) | B | JMeter | 台数 (20 のまま下がらない) | HPA-A/B/C の 3 設定 (減少窓 2 分未満/1 分未満) | 記載なし | SS | ★本文 grep (§13.12)。窓を書いた数少ない例 |
| 14 | Pozdniakova, Mažeika, Cholomskis, Electronics 13(7):1242, 2024 (DOI 10.3390/electronics13071242、`pozdniakova2024slahpa`) | B (閾値調整) | **未読** | **未読** | HPA の閾値を SLA に合わせて調整する提案 | **未読** | **未読** | **abstract/検索要約のみ**。MDPI が 403 で本文を取得できなかった。**引用前に原典を読むこと** |
| 15 | Sivko, Coroot ブログ (2022-04-19、https://coroot.com/blog/how-quickly-can-the-kubernetes-hpa-scale-your-app/、**技術資料**) | A (遅れの測定) | 同時 HTTP 要求を徐々に増やす | チャートから読み取り (取得方法の記載なし) | **metrics-server の解像度 60 s → 10 s**。HPA 同期周期 15 s は既定 | **各 1 回** (2 ラウンド) | EKS、HPA v1、目標 50%、min 2 / max 3 | WebFetch で本文確認 (2026-11-17)。**学術論文ではない**。『目標 50% に達してからスケールまで 2 分 5 秒 (既定) → 約 30 秒 (10 s)』 |

#### 13.14.2 最も近い 3 本 (方法節で「〜と同様の手順で」と書けるか)

**① Nguyen ほか 2020 (`nguyen2020hpa`) — (B)(A)**
- **似ている点**: HPA の設定 (取得周期・指標・クラスタ規模・readiness probe) を 1 つずつ変え、**台数と失敗数を時系列で比べる**。**同条件を 10 回反復**する。**単一の物理機の上**で K8s を動かす (VM 5 台。本研究の単一ノードに近い)。負荷は Gatling で、リクエスト率を指定する**開ループ**。
- **違い**: (i) 負荷は 1800→600→0 req/s の 2 段階で、**一定負荷ではなく、定常の台数を取る窓も無い** (台数の増え方と最大台数を図で見る)。(ii) 変えたのは取得周期・指標など**サイド**で、**requests は固定 (100m)**。本研究は requests を変えて台数を決める。(iii) K8s 1.15・metrics-server 既定 60 s。本研究は v1.32 で値の更新周期も違う。(iv) 10 回の結果をどう集約したか (平均か個別か) は本文を読んだ範囲では不明。
- **書き方**: 『HPA の設定を 1 つずつ変え、台数と失敗数の時系列を比べる手順は Nguyen らと同様 [`nguyen2020hpa`]。ただし本研究は一定レートの窓で定常台数を読み、requests を変数とした』。これは言える。「同じ測定窓」とは言えない。

**② COLA (`sachidananda2022cola`) — (B)(C)**
- **似ている点**: **一定レートを段階的に変え** (400・600 rps など)、各水準で HPA の CPU 目標 10〜90% を振り、**台数と遅延の関係**を OB で示す。本研究の「レートを振って台数を見る」と同じ形。『最適な目標はアプリと負荷による』という主張が、本研究の「requests と負荷で台数が決まる」と同方向。
- **違い**: (i) **1 レプリカ = 1 VM 全体**を要求し、台数 = 支払う VM 数 (本研究の requests × 台数とは単位が違う。ただし「予約量」に近い量を数えている点は似る)。(ii) 窓・ウォームアップ・反復の記載は読んだ範囲に無い。(iii) 目的は自作オートスケーラの提案で、HPA 特性評価は動機づけの図 (Fig. 1)。
- **書き方**: 『一定レートを段階的に変えて HPA が選ぶ台数を読む手順は COLA の評価と同型 [`sachidananda2022cola`]』。ただし「COLA は反復で台数のばらつきを見た」とは書けない (記載なし)。

**③ Buzato & Goldman (`buzato2026ijnc`) — (C)**
- **似ている点**: SS で**負荷を 3 水準**に変え、HPA 下の**台数の増加率** (式 (1)) と応答時間・失敗を見る。**各水準 6 回反復**して箱ひげ図で示す (「標本が少ない」と明記)。立ち上げ 5 分 + 最大人数の保持 5 分で、後半を評価に使う点が本研究のウォームアップ + 窓に近い (ただし本文が「後半だけを集計する」と明示したかは今回の grep では未確認)。
- **違い**: (i) **閉ループ** (Locust のユーザ数)。(ii) HPA は min 1/max 4・目標 150%、**台数の上限で頭打ちになる設計**。(iii) 台数は「増加率」の 1 つの指標で、**窓内の台数の時系列は示していない**。(iv) 2 ノードの AWS、1 コンテナ内の束ね (§13.4)。
- **書き方**: 『負荷水準ごとに数回反復し、HPA 下の台数と性能を比べる手順は Buzato & Goldman と同様 [`buzato2026ijnc`]。ただし本研究は開ループ・計測窓・台数の時系列である』。

**参考 (査読なし／HPA でない)**: **Wijaya (GitHub)** は k6 の `ramping-arrival-rate` (開ループ)、5 回反復、HPA の目標 80% vs 50%、time to scale を測り、**特徴の一致数では 1 位**。ただし学部論文 (査読の有無不明)・README のみ読了なので、**引用ではなく方法の参考にとどめる**。**Henning & Hasselbring (`henning2024theodolite`)** は HPA を使わず、台数を固定して負荷ごとの最小台数を探す。**『ウォームアップ 2 分 + 3 回反復』の正当化 (「時間と統計の妥協点」)** は、本研究の固定台数スイープ (HPA 無し) の方法節に引ける。

#### 13.14.3 項目別: 本研究の測り方のどの部分に先行例があるか

| 本研究の測り方 | 先行例 | 確認度・注意 |
|---|---|---|
| k6 開ループの一定レート | Wijaya (k6 ramping-arrival-rate、README)、Nguyen (Gatling、レート指定)、COLA (一定レート。ツールは本文の別の箇所)、Podolskiy (自作、レート指定) | 査読ありで「開ループ」と明記して HPA を測るのは Nguyen・Podolskiy。**閉ループ (Locust・JMeter・k6 VU) が多数派** (§13.10.4 と同じ) |
| ウォームアップの後の窓だけで評価 | Henning (2 分/4 分の warm-up、HPA ではない)、Wijaya (k6 時刻 120〜540 s、README) | HPA 論文で**窓を切って評価**すると本文に書いたのは、読んだ範囲では Wijaya のみ (査読なし) |
| 段階的にレートを変える | COLA (400/600 rps…)、Nilsen (250/500/750 rps)、Buzato (3 水準) | **(C) は先行例が多い** |
| HPA の設定を変える (目標・取得周期・指標) | Nguyen (取得周期・指標)、COLA (目標 10〜90%)、STaleX (25〜70%)、Shetty (60/70/90%)、Wijaya (50/80%)、MS-RA (3 設定) | **(B) の先行例は多い** |
| 台数の時系列を一定間隔で記録 | Nguyen (図)、Nilsen (desired replicas)、Podolskiy (CAI/DAI)、Serracanta (図) | **採取間隔を数値で書いた論文は読んだ範囲で 0 本** (Nguyen は metrics-server の周期のみ) |
| 収束時間・落ち着くまでの時間 | Podolskiy (autoscaling latency の**定義**)、Shetty (time to meet SLO)、Wijaya (time to scale)、Coroot (2 分 5 秒、1 回、技術資料) | **台数が帯の内に入って留まるまでの時間 (settling time) を定義した HPA 論文は見つからなかった** (WebSearch で同様に出ず) |
| 同条件を 3〜12 回反復 | Nguyen 10、Buzato 6、Nilsen 3、Wijaya 5、Henning 3、Casalicchio 20 (シミュレーション) | 回数は同水準。**ただし反復の使い道は「平均・箱ひげ図・標準偏差」で、台数の一致回数ではない** |
| 予約量 = requests × 台数 | COLA (VM 数 = 費用)、Shetty (Fig. 3c の『要る CPU 量』、図は未読)、Buzato (増加率) | **requests × 台数を主指標にした論文は見つからなかった** |

#### 13.14.4 先行例が見つからなかった部分 (空白。検索範囲を限定して書く)

- **(a) 「落ち着いた台数が N 回中 M 回同じ」と回数で数える**: Nguyen・Buzato・Nilsen・Wijaya の反復は、遅延や台数の**平均・分布**を示すためで、台数が**整数のどこに落ちたかを数えた**記述は読んだ範囲に無い。Wijaya は台数の中央値を出すが、一致回数ではない。
- **(b) HPA の許容幅 (±10%) による整数閾値効果**: 本節の 15 本のうち許容幅に触れたものは 0 本 (§13.12 の 29 本でも 0 本)。Serracanta はモデル化するが許容幅は扱わない (グラフを読んだ範囲)。
- **(c) 予約量 (requests × 台数) を HPA 下の主指標にする**: 上表のとおり COLA (VM 数)・Shetty (CPU 量) が近いが、**requests × 台数と定義した論文は見つからなかった**。
- **(d) requests を実測から決め、それで台数が決まる (requests を変えると台数が変わる)**: Shetty の requests・limits・閾値の掃引が最も近い (Fig. 3c は図、未読)。他は requests を固定 (Nguyen 100m、Joyce 100m、Serracanta 100m)。**requests を操作変数として振った論文は Shetty のみ** (主題は limits の是非で、台数の決まり方ではない)。COLA は 1 レプリカ = VM 1 台全体を要求するので、requests を振っていない。
- **(e) 窓内の台数 (落ち着いた台数) を HPA 論文が定義して使うこと**。
- **検索範囲**: WebSearch (extended 3・standard 6、クエリは 13.14.6)、arXiv API (abs 検索 9 本)、既存 §13.10〜13.13 の 29 本。IEEE Xplore・ACM DL・Google Scholar・Semantic Scholar は引いていない。**「空白」は『この範囲で出なかった』であり、存在しないことの証明ではない**。

#### 13.14.5 位置関係の判定

- **衝突 (既出): 無し。**
- **相補 (測り方が近い)**: Nguyen 2020、COLA、Buzato & Goldman、Shetty (§13.14.2)。どれも**手順の一部が同じ**で、窓・開ループ・反復の使い道・requests の扱いが違う。
- **背景**: Serracanta (制御理論による安定性)、Podolskiy (autoscaling latency の定義)、Nilsen、Casalicchio、Henning (Theodolite)、Coroot、Joyce。
- **無関係 (混同注意)**: Chan ほか "Automatic Adjustment of HPA Parameters and Attack Prevention in Kubernetes Using Random Forests" (arXiv:2601.13515) = 検索語『HPA parameters』で出るが、攻撃トラフィックの比率で maxReplicas を調整する**セキュリティ**の論文。HPA の「しきい値」は攻撃割合のことで、特性評価ではない (本文の方法を読んで確認)。Rodriguez & Buyya (arXiv:1812.00300) = 検索語『autoscaling elasticity』で出るが、独自のスケーラの提案 (HPA の特性評価ではない、冒頭のみ確認)。

#### 13.14.6 検索の記録 (2026-11-17)

- **WebSearch (extended)**: 『Kubernetes HPA characterization experiments target utilization replica count convergence time constant load』→ 公式 doc と実務ブログのみ (論文 0)。『performance evaluation Kubernetes Horizontal Pod Autoscaler microservices increasing load number of replicas response time CPU threshold experiments paper』→ Electronics 2024、Sensors 2020、Joyce、MOHA、STaleX、Casalicchio が出る (**新規は Electronics 2024・Casalicchio 2019**)。『comparison HPA CPU memory custom metrics ... ramp-up load』→ Nguyen、Smart HPA、IARAS 2025 (未取得、評価の記述が薄いと判断し表に入れず)。『Kubernetes autoscaling HPA KEDA empirical comparison open-loop constant request rate replica count over time repeated runs』→ **Wijaya の GitHub が出る**。
- **WebSearch (standard)**: 『Casalicchio absolute versus relative metrics ...』(Springer 版 PDF を取得)、『HPA stabilization window sync period impact ... empirical evaluation』(実務ブログのみ、論文 0)、『elasticity benchmarking Kubernetes autoscaler step load time to scale out ...』(Dashtbani・Coroot・Rodriguez & Buyya・Podolskiy 周辺)、『Kubernetes HPA control-theoretic analysis oscillation stability ...』(Serracanta、Kivi、edge serverless RL)、『impact of CPU requests on HPA ... experiments』(**論文 0。実務ブログのみ**)、『Theodolite scalability benchmarking ...』(Henning)、『autoscaler "settling time" ...』(**settling time を定義した論文 0**)、『"Horizontal Pod Autoscaling based on Kubernetes with Fast Response and Slow Shrinkage"』(題名では引けず、書誌未確認 → 表に入れない)。
- **arXiv API (abs)**: `"Horizontal Pod Autoscaler" AND evaluation` (5 件、既知)、`... AND stabilization` (1 件、edge serverless RL)、`... AND threshold` (3 件、既知)、`HPA AND Kubernetes AND settling`・`Kubernetes AND autoscaling AND control theory`・`... empirical study`・`... load test`・`... configuration AND replicas`・`HPA AND CPU utilization AND response time` (**0 件**)。→ **arXiv の abstract 検索では HPA の特性評価論文はほぼ出ない** (査読誌・学位論文・GitHub に分散)。
- **取得できなかった/しなかった**: MDPI Electronics 2024 の本文 (403)、Springer 版 Casalicchio の ICCAC 2017 版 (別版、未読)、Henning の ESE 2022 (手法の本体、未読)、IARAS 2025 の論文 (評価記述が薄い)、Wijaya の repo の個別ファイル (README のみ)。
- **ポリシー上の注記**: ブラウザを装う取得 (User-Agent 偽装) は権限で拒否されたため行っていない。書誌確認の Unpaywall 照会も行っていない。

#### 13.14.7 次に読む (優先順)

1. **Nguyen 2020 (`nguyen2020hpa`) の図 3〜8 と 10 回の集約方法** — 最も近い査読あり論文。10 回を平均したのか個別かが分かれば「反復」の書き方が決まる。
2. **COLA (`sachidananda2022cola`) の Fig. 1 と付録 (定常遅延を 30〜60 s で推定する図)、公開コードの HPA 設定** — 一定レート × 目標の掃引を OB で行った唯一の例。反復と窓を確認。
3. **Shetty の Fig. 3c (図)** — 25% 段階負荷の収束時間。図の数値を読めば (A) の例になる。
4. **Henning & Hasselbring ESE 2022 (DOI 10.1007/s10664-022-10162-1)** — 「ウォームアップ長と 3 回反復」の統計的根拠 (方法節の正当化に直結)。
5. **Electronics 2024 (`pozdniakova2024slahpa`)** — 本文未読。HPA 閾値を変えた評価の可能性があるが、要約のみ。
