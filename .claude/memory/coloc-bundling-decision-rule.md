---
name: coloc-bundling-decision-rule
description: 【設計則の主軸 2026-07-07】どのコンテナを束ねるべきかを「通信量(便益)×HPA粒度(コスト)」で決める枠組み。A=構造相関/B=便益コスト、木構造(専属/共有)、専属でも粒度損は残る。
metadata:
  type: project
---

**2026-07-07 セッション。テーマ=「どのコンテナを束ねるべきか」を通信量とHPAの2軸で一般化。** [[hpa-scaling-angle]] の続き。ユーザ要望: 記号/横文字を急に使わない・言葉で説明、勝手に判断せずソース/実測で裏取り、可能な限り一般化。

**2軸フレーム(束ね候補の評価):**
- **便益=softirq削減**。削減は加算的(各エッジ単独削減の和≒束ね全体)で、**バイト量/req に比例**([[softirq-cpu-metric]]で確立)。手持ちデータで前もって見積もれる。
- **コスト=HPA粒度損**。HPAはPod単位でしか増やせない→束ねると中の複数サービスが一緒にしか増えない→片方だけ忙しいと暇な方まで増えて無駄。
- ⇒ 設計則: **重いバイトのエッジ**を、**需要が連動する**サービス間で束ねる。ICTer(便益/バイトのみ)にHPAコスト軸を足すのが novel。

**先行研究の位置(検索裏取り 2026-07-07):**
- **ICTerはスケーリング/HPAを一切扱わない=静的配置(Binary Knapsack, Docker Swarm)**。負荷変動もオートスケーラも射程外→「動的にすると束ねが脆くなる」は空白。cyc3失速は静的世界では起こり得ない現象。
- **予測オートスケール(HGraphScale arXiv:2511.01881 / STaleX 2501.18734 / "power of prediction"(workload learning) / DeepScaler GCN)は活発だが全て別Pod前提**でスケール判断を賢くするだけ=束ね粒度の決定には使わない。**★反論=別Podを協調スケールしても softirq(ネット経路のカーネルCPU)は消えない。localhost化=束ねだけがsoftirqを削る→予測と束ねは競合でなく相補的。** これらの予測器は「需要相関を計算する道具」として借用可(方法論の再発明不要)。要精読=HGraphScale, "power of prediction"。

**需要相関(=一緒に忙しくなるか)は予測不要、コールグラフで導出できる(A):**
- 各サービスの忙しさ=Σ(各入口の使用ペース × その入口がそのサービスを呼ぶ回数)。呼出回数はコードで固定。
- **予測以外の方法**: A=構造/待ち行列(呼出比から導出, 一発計測, 我々の主), B=プロファイリング+解析的便益コスト最適化(静的・ML不要・再現可能=ICTer Knapsackにコスト項追加), C=制約回避(VPA/In-place resize で縦スケール→軽い方を複製せず容量増。ただしHPA ContainerResource v1.30は"どのコンテナで測るか"を選べるだけでPod複製単位ゆえ粒度損は消えない=要注意), D=実行時re-bundling(Hassan2020の空白だが重い), E=制御理論リアクティブ。**推し=B(主)+A(入力)。設計時に決めるので予測は本質的に不要。**

**このappのコールグラフ(ソース確定: frontend/handlers.go, checkoutservice/main.go, locustfile.py):**
- 負荷ツールは `tasks=[checkout]` のみ。1周=①GET /product/{id} ②POST /cart ③POST /cart/checkout を **1:1:1 でロック**(on_startのGET /は初回のみ)。
- **★重要=今の負荷は全サービスをρ=1(完全相関)に固定**。だから前回front3束ねが良かったのは自然、かつ**このままでは粒度損(コスト軸)が構造的にほぼゼロで測れない**。コストを測るにはlocustfileを「見るだけの人/買う人」に分けて比率を振る改造が必須(=C案の前提条件)。
- 呼出構造: 「買う」でしか呼ばれない=checkout,payment,email,shipping。「見る/カート操作」で呼ばれる=productcatalog,currency,cart,recommendation,ad。実測パケット順位(payment/email最少, catalog多)と整合=裏取りOK。

**木構造での一般化(ユーザ発案, 呼び出し元の数=in-degreeで分類):**
- **専属(呼び出し元1個)=木の枝**: recommendation←frontend, ad←frontend, payment←checkout, email←checkout, checkout←frontend, redis←cart(状態持ち例外)。→親Podに機械的に吸収してよい(帰属明確・他の親が取り残されない)。**ただし状態持ち(redis)は専属でも吸収しない=上書きルール**。
- **共有(呼び出し元複数)=合流点=難しい問題の中心**: productcatalog(frontend/checkout/reco=3), currency(2), cart(2), shipping(構造2だが今の負荷ではcheckoutのみ=実質専属)。難しさ=①どの親に付けるか曖昧②付けても他の親はネット越しに残る③スケール合図が合わない。対処=(a)一番重い枝に付け残りは諦め(ICTer的) (b)複製して各親に配る(状態なし限定・計算重複コスト) (c)共有は束ねず別Pod(安全) (d)実測でトラフィックが1親に偏れば実質専属化。**→問題が縮む: 専属は自動吸収、真に難しいのは"複数親に均等に引かれる共有ノード"(このappではproductcatalogが最有力)。**

**★専属でも粒度損は残る(ユーザ指摘で訂正, 重要):** 専属は「動くタイミング」は完璧に揃うが「**必要レプリカ数**」は揃わない。例=checkout+email+paymentを1Podに→checkoutが忙しく4台にスケール→email/paymentも4台に増えるが冷えたまま→余分3台ずつ無駄。
- **無駄の定量式(言葉)= Σ_各サービス〔予約枠 ×(束ね全体の台数 − そのサービス単独で必要な台数)〕**。ゼロになるのは全サービスの必要台数が揃うとき**だけ**。
- **「重さが近ければ無駄ゼロ」は無条件の事実でない(要定量化)**。正しい条件=**全サービスが同じリクエスト数でHPA閾値に届く=「1リクのCPU ÷ 割り当て枠」の伸び方が揃う**。効くのは重さそのものでなく「重さ÷枠」。加えて①整数切り上げの無駄(低台数で相対大)②伸び方がズレると無駄は負荷に比例して増大。
- **損得はスケールで逆転**: 低負荷=束ね得(Pod数↓固定費↓, softirq↓)、高負荷で重い親が多レプリカ=束ね損(軽い専属が無駄増殖)。境目は「親と専属のCPUの重さ比」。

**B(各サービスCPU)の測定は難しくない(誤解の訂正):** 難物だったのはノード全体の通信コスト(softirq, userノイズ)で**既に測り終えた=便益側**。B が要るのは **cgroupのコンテナ別アプリCPU=安定側=HPAが実際に見る値**(合計は既取得, per-serviceはラベル内訳だけ)。しかも**「1リクで割る」必要すらなく、各コンテナの使用率カーブ(=HPAが読む値)を負荷を変えて測ればよい**。per-serviceリクエスト数が要ればAの呼出回数から導ける(A→Bの入力)。留保=軽いサービス(payment/email)の1リクCPUは極小でノイズ乗るが、無駄判定は「checkoutよりずっと遅く閾値到達」の粗い大小関係なので結論は堅い。

**実測した割り当て枠(requests/limits, 2026-07-07, 3ファイルのみ確認):** checkout=800m/1200m, email=200m/300m, payment=200m/300m。**=checkout(800m)とemail・payment(各200m)が不揃い(親が子の4倍枠), email=paymentは一致。** 残り8サービス(frontend,cart,catalog,currency,shipping,reco,ad,redis)の枠は未確認。HPA使用率=使用CPU÷枠なので、閾値到達順は使用CPUだけでなく枠にも依存→Bで実測要。

**次の一手(未実行):** ①全サービスの枠(requests/limits)一覧確認 ②B測定=各サービスのコンテナCPU使用率を負荷数段で測り閾値到達カーブを描く(スクリプト案 km2/experiments/perservice-cpu.sh はユーザが一旦保留) ③無駄の式に代入し「何レプリカで束ねが損に転じるか」算出 ④locustfileを見る人/買う人に分割し粒度損を実測(C案)。

関連: [[hpa-scaling-angle]] [[softirq-cpu-metric]] [[bundling-merit-question]] [[related-work-coloc]] [[coloc-resource-efficiency-study]]
