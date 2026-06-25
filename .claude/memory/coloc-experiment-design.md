---
name: coloc-experiment-design
description: 案Bの実験設計 — ペア選定基準(call graph上で遠い=ρ独立制御)と「2点較正→未試行ペアをΔC予測」の枠組み
metadata: 
  node_type: memory
  type: project
  originSessionId: d56d9f99-7ff6-4e92-8e61-2963f48f117c
---

案B([[coloc-tradeoff-model]])の実験設計判断(2026-06-16)。

**ペア選定基準(=遠いペアを選ぶ):** 実験の生命線は**相関 ρ を −1〜+1 で自由に掃引できること**(でないと τ の反転を描けない)。ρ を振るレバーは loadgenerator のフロー比率だけ。∴ **call graph 上で互いに直接呼ばない「遠い」2サービスを選ぶ** — 片方は閲覧(`index`)、片方は購入(`checkout`)でしか駆動されないペアなら、locust の閲覧:購入比を時間変化させて2サービスの負荷の位相を独立にシフトできる。
- ❌ 近い/隣接ペア(reco→catalog): reco が呼ばれる度に catalog を必ず叩く(`recommendation_server.py:70`)→ ρ≈1 に構造固定 → ∫|a−b|≈0 → τ 探索が**測定不能**。前回「クリーンな2連鎖だから最適」と言ったのは誤り(測りたいものを測れなくする選択だった)。
- ✅ 推奨: **recommendationservice(index) ↔ paymentservice(checkout)**。代替 reco↔shipping, ad↔payment。productcatalog はハブ(全フローが叩く)で位相制御に不向き=ペアから除外。
- トレードオフ: 遠いペアは localhost 通信ホップ削減の恩恵が消える(互いに通信しない)→静的メリットの源は **Envoy 1枚化(2→1)+Pod固定費のみ**。研究主張(動的 ∫|a−b| と相関反転)には ρ 掃引が絶対条件なので遠いペアが正解、静的メリットは Istio 注入で別途載せる。

**予測の枠組み(=実験の最終目的):** 全ペアを実機で試すのは非現実的。代わりに **少数点で式を較正→残りは計算で予測**。ΔC=(fS−gM)−r∫|a−b| の入力 ρ,σ,(f−g),r は全て**集約せずに事前測定可能**(ρ,σ=Prometheus の独立稼働時の負荷履歴、f−g=Envoy/Pod OH定数、r=manifest の requests)。手順: ①各サービスの需要時系列 aᵢ(t)=req率÷1レプリカ容量 を取得 ②全ペアの相関行列 ρ_ij と σ ③ペア毎の静的メリット(隣接=通信削減+サイドカー化 / 遠い=サイドカー化のみ) ④較正済み式で予測 ΔC ⑤ΔC>0 をランキング(=先行研究 Knapsack 配置の相関考慮版)。実験の役割は g<2f・r・∫|a−b| の係数が実機と合うかの**検証**で、ρ高/低の最低2点で曲線形を確認してから外挿。
**予測が外れる条件:** ①per-サービスで r が違う(email は Jinja2 で重い)→∫|a−b| は容量重みづけ差で測る ②HPA の整数切上げ+minReplicas 床→低負荷域でモデルとズレ ③1点外挿は危険、2点で形を確認。

**コストの定義(2026-06-18, 重要):** レプリカ1枚のコストを**予約(requests)で数えるか実使用で数えるかで結論(τの存在)が逆転**する。実使用だと集約で増えた暇な相方レプリカ≒0 CPU→無駄ほぼ無料→集約ほぼ常勝。予約だと暇でも requests 確保され続け他に回せない→本物の無駄→ズレると損。**本研究は予約(requests)を主コストに採用**:①K8s は Σrequests≤容量 でスケジュール=確保済み空きCPUは他に回せない本物のムダ(資源効率=何台要るかは usage でなく requests で決まる)②HPA 自身が requests 基準(使用率=usage÷requests)でモデルの a(t),b(t) は requests に対し定義③決定論的でノイズに強い。主張は「同一SLO達成に確保すべき資源量」であって焼いたCPUサイクルではない。**前提条件=requests が右サイズ(≒目標使用率での実使用)であること**→較正フェーズ1で右サイズ化して担保(歪んだ requests だと予約コスト水増し+HPA歪む)。**実使用は副指標**で併測(右サイズ検証 + 予約−実使用ギャップ=無駄の中身)。注: [[coloc-resource-efficiency-study]] の旧主指標は実使用 node CPU だったが案Bでは予約が主・実使用は副に整理。

**負荷生成(方法2を採用, 2026-06-18):** `src/loadgenerator3/`(新規)= reco/payment へ frontend を介さず直接 gRPC を投げ、2本の正弦波の位相差で ρ=cos(PHASE_DEG) を制御(0→+1,90→0,143→-0.8,180→-1)。Job は `scaling/loadgenerator3.yaml`(分離/集約 共通、Service 名同一で宛先不変)。イメージ `mizuki0118/loadgen3:run1`。py_compile のみ通過・実走未確認(ホストに grpc 無)。詳細手順は `km2/approach/worklog.md`。未決: コンテナ名 分離`recommend` vs 集約`reccomend` の統一。

関連: [[coloc-tradeoff-model]] [[related-work-coloc]] [[coloc-resource-efficiency-study]]
