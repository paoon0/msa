---
name: softirq-cpu-metric
description: 【現行・主指標】Pod集約の通信コストは node CPU の softirq モードで測る。userノイズを物理的に回避。
metadata: 
  node_type: memory
  type: project
  originSessionId: 4454391e-ace3-4402-a08c-ddd1287462a6
---

2026-06-30。CPU/req 本走の前に**主指標を「node全体CPU」から「softirq モードCPU」へ変更**した。経緯と根拠：

**なぜ node 全体CPUがダメか(実証):** ノード `mizuki-nuc12wshi7` は単一ノードのワークステーション。node非idle CPU の**約75%が非Kubernetes背景**(kubelite=MicroK8s制御系15%, VS Code `code`/`node`系~11%, Claude本体+私のkubectl/python計測ツール, dqlite/calico/containerd)で、これが**数分で0.3コア揺れる**(無負荷基線を3回測ると 0.41/0.71/0.72 と range0.3)。基線を引いても per-req に直すと rps92で sd1.5 mc/req=拾いたい信号と同オーダー→使えない。

**鍵=CPU時間はモード別に別カウンタ(/proc/stat)。** 背景ノイズは全部 **user**モード(プログラムの計算)。**通信のkernel処理(NAT/conntrack/bridge通過)は softirq モード**で、しかも**どのコンテナcgroupにも計上されない**(送信スレッドは手を離し、後でksoftirqd等が非同期処理→CPU単位の softirq カウンタへ。pod名ラベル無し)。実測でモード分解: 無負荷で **softirq=0.0053⇄0.0056(不動)** に対し user=0.27⇄0.49(大揺れ)。負荷をかけると softirq 0.005→0.255(50倍)。**softirqを見ればuserノイズと物理的に隔離**できる。`mpstat -P ALL` の %soft 列と同じ標準手法(MeshInsight arXiv:2207.00592 はさらにperf/flamegraphで関数分解)。

**重要な含意:** コンテナ別CPU(cgroup)は安定だが**通信コストが入っていない**(softirqはcgroup外)→だから app CPU は経路差を映さず「対照群(公平性チェック)」にしかならない。主指標にはできない。softirqが「cgroup外の通信コストをuserノイズ無しで拾える唯一の場所」。

**本走完了(3cycle, WARMUP3m/MEASURE5m, ~208rps, exp ns, Istio無し, 2026-06-30):結論=co-location で softirq/req 約半減。** `km2/all/results-cpu.csv`:
- **softirq/req: normal 1.181±0.023 vs mega 0.564±0.017 = −52.2%。** 差0.617 mc/req はアーム内sd≈0.020 の**31倍**=圧倒的有意・3cycle一貫。指標は超安定(node全体±0.4〜0.9と対照的)。
- 対照群 app/req: 13.26 vs 12.47(−6.0%)=softirqの−52%と桁違いに小=差は通信由来。system −6.3%同方向(syscall/serialize漏れ)。node全体 −9.3%(背景userに薄められる=主指標にしない理由)。
- 絶対量: 208rpsで softirq normal 0.246→mega 0.117 cores=約0.13コア節約。単一ノード低負荷ゆえ絶対量は小。主張は「通信スタックCPU/req 約半減」(総CPU大幅減ではない)。
- スモーク(1cycle 161rps)でも softirq normal1.193/mega0.589=−51%で本走と一致。

**実装:** `km2/all/compare.sh` に softirq/system 取得を配線済(CSV22列, softirq_mc_per_req/system_mc_per_req 追加, 基線も softirq/system 取得)。基線測定は**ウォームアップ後の温まったアイドル**で行う([[megapod-latency-experiment]]の基線ドリフト対策, 起動スパイク回避)。本走 `CYCLES=3 WARMUP=3m MEASURE=5m` → `km2/all/results-cpu.csv`。

**同居だけの対照(paymail)=切り分け成功(3cycle, 本走と同条件 CYCLES3/WARMUP3m/MEASURE5m/USERS80/RATE1/~208rps, 2026-06-30):** email+payment を1Pod(paymentservice)に同居させるが checkout は依然 `paymentservice:5000/:50051`=ClusterIP で呼ぶ(localhost化せず)。結果 **paymail softirq/req=1.222±0.044 ≒ normal 1.181(+3.4%=誤差内)**、mega 0.564 の−52%とは桁違い=paymail は normal 側に張り付く。app/node/system も paymail≈normal。**∴ softirq半減の原因は「Pod同居」ではなく「通信を localhost 経路へ切替えたこと」**。これが mega 主張の決定的ヌル対照。資産 `km2/all/paymail-softirq.sh`(3cycle化済, CSVに cycle列), 結果 `km2/all/results-paymail.csv`。罠: paymail/ マニフェストは旧世代で requests/limits が桁違いに小・checkout が upstream イメージ→**全コンテナ resources を all.yaml と同値に, checkout を mizuki0118/mygo:bunpupaymail に揃えてから測る(cpu/memのみ書換, EMAIL_SERVICE_ADDR=paymentservice:5000 は同居先なので維持)**。compare.sh は USERS/RATE を注入せず loadgen-csv.yaml の値(USERS80/RATE1)をそのまま使う(本走の実体は env で MEASURE=5m 上書き, スクリプト既定10mは未使用)。

**1ホップだけ localhost 化の対照(outmail)=用量反応を発見(3cycle, 本走と同条件, ~208rps, 2026-06-30):** email を checkout の Pod に同居し `EMAIL_SERVICE_ADDR=localhost:8080`(email1ホップだけ loopback)。payment等は ClusterIP。結果 **outmail softirq/req=1.177±0.03 ≒ normal 1.181(−0.3%)**=減らない。app/node も normal並み。**∴ softirq削減量は「localhost化したか否か」でなく localhost化したホップが運ぶトラフィック量で決まる**。email は checkout→1req1回の軽ホップ→loopback化しても全体softirqに出ない。mega の半減は frontend含む重いホップ(毎ページ全fan-out)を全部localhost化した効果。**用量反応=重いトラフィックのペアを束ねるほど効く**→設計指針「重い通信ペアを優先同居」。注意:outmail/ マニフェストは更新済で all 値に既に整合(paymailと違い修正不要だった)、checkout=bunpupaymail。資産 `km2/all/outmail-softirq.sh`, 結果 `km2/all/results-outmail.csv`。3アーム整理: normal 1.181 / paymail 1.222(同居のみ) / outmail 1.177(軽ホップlocalhost) / mega 0.564(全localhost)。

**outpy(payment軽ホップlocalhost)=用量反応の再確認(3cycle, 本走と同条件, ~208rps, 2026-06-30):** payment を checkout の Pod に同居し `PAYMENT_SERVICE_ADDR=localhost:50051`(payment1ホップだけloopback)、email等ClusterIP。outmail の対。結果 **outpy softirq/req=1.152±0.08 ≒ normal(−2.5%)**=減らない。outmailと並び「軽ホップlocalhostは別ホップでも無効」を確認。outpy/ も旧世代でpaymail同様に是正(全resources→all値, checkout→bunpupaymail, PAYMENT_SERVICE_ADDR=localhost:50051/EMAIL_SERVICE_ADDR=emailservice:5000 維持)。資産 `km2/all/outpy-softirq.sh`(deployリストはemail standalone), 結果 `km2/all/results-outpy.csv`。

**7アーム=用量反応曲線: normal1.181 / paymail1.222(同居のみ) / outmail1.177(email軽) / outpy1.152(payment軽) / frontcart1.123(cart+redis中,−4.9%) / frontcatalog0.996(catalog重,−15.7%) / mega0.564(全localhost,−52%)。** frontcart(frontend+cart+redis同居, CART_ADDR/REDIS_ADDR=localhost, 資産km2/frontcart/+km2/all/frontcart-softirq.sh, 結果results-frontcart.csv): 削減小で3cyc境界線(sd0.070>削減0.058, cycle3のみ下げ, SEMの1.4倍=有意性弱い)。ただし**削減量がパケット率に比例**=frontcatalog 0.185mc/7182pkts≒0.0000258 と frontcart 0.058mc/~2300pkts≒0.0000252 がほぼ同係数→「softirq削減∝loopback化パケット数」を2重ホップ実験で定量一致(パケット率予想-4.7%と実測-4.9%一致)。これが⑥バイトvsパケット反証の芽。 軽ホップ3つはnormal張り付き、**最重エッジ1本のlocalhost化(frontcatalog)で初めて−16%の肯定点**、全部入りで−52%。frontcatalog: 差0.185はsd0.05の4倍=有意, app/req13.2≒normal(対照不変), rps207/fails0, 3cyc。

**frontcatalog(効く点)実測完了(3cycle, 本走と同条件, 2026-06-30):** frontend+productcatalog を1Podに同居し frontend `PRODUCT_CATALOG_SERVICE_ADDR=localhost:3550`(最重エッジをloopback)。reco/checkout は `productcatalogservice:3550`=ClusterIP維持(productcatalogservice Service の selector を app=frontend に向ける=必須。消すとreco/checkout疎通断)。資産: `km2/frontcatalog/`(完備・全all整合・checkout=bunpupaymail), `km2/all/frontcatalog-softirq.sh`(deployリストはproductcatalogservice/frontend standalone除外の10deploy), 結果 `km2/all/results-frontcatalog.csv`。予想0.8-0.9に対し実測≈1.0(やや小)=frontendの他重エッジ(currency/cart/reco/ad)とproductcatalogへのreco/checkout経路は依然ClusterIPだから部分回収に留まる→用量反応と整合。次は閲覧パス全束ね(frontend+catalog+reco+currency+cart)でmega近くまで増えるか。

**ホップ別トラフィック実測(2026-06-30, outpy負荷下, container_network packets/s, softirqの源泉ランキング):** frontend10806 > **productcatalog7182** > checkout2825 > cart2147 > reco1911 > currency1513 > shipping1049 > redis834 > ad270 > **email265(最軽)**。→email/payment が最軽=outmail/outpy無効の物理的裏付け。**最重エッジ=frontend↔productcatalog**。**効果最大の束ね方=閲覧パス(frontend+productcatalog+recommendation+currency+cart)を1Podへlocalhost化→megaの−52%の大半をcheckout側を触らず回収する見込み**。測定法: promq pod で `sort_desc(sum by(pod)(rate(container_network_receive_packets_total{namespace="exp"}[3m])+rate(...transmit...)))`。

**frontreco=バイトvsパケット判別実験(3cycle, 2026-07-06):結論=パケットでなく"バイト"寄り(私の以前のパケット説は否定された)。** frontend+reco同居, RECOMMENDATION_SERVICE_ADDR=localhost:8090(reco 8080→8090 remap, reco の Service無し=frontendしか呼ばない, reco→catalogはClusterIP)。資産km2/frontreco/+km2/all/frontreco-softirq.sh, results-frontreco.csv, fails0。**frontreco softirq/req=1.067±0.044(-9.7%, 削減0.114はsd2.6倍=有意)。** 判別: cartとrecoはパケットほぼ同(2177 vs 2050)なのにreco削減が約2倍(-4.9% vs -9.7%)=recoのバイト2倍(261K vs 544K)と一致。正規化: per-byte(2.2/2.1/1.5e-7=揃う)がper-packet(2.7/5.6/2.6e-5=reco浮く)より一貫。**→softirq削減はパケット数より"バイト量(パケットサイズ込み)"に沿う=ICTerのバイトaffinityはむしろ支持される(反証にならない)。** 留保:pod総計は実localhost化エッジ量でない(reco↔catalogはClusterIP残)+重ホップ3点のみ→エッジ単位実測が要る。**⑥の方針転換:「パケットが効く(ICTer反証)」は不成立。novel性はEnvoy税④や別軸で。**

**各サービス通信量(normal 3cyc平均, results-cpu窓, Prometheus履歴クエリ, pkts/s|bytes/s|B/pkt):** frontend10869|3.97M|365(loadgen向けHTTP込) / productcatalog7046|1243K|176 / checkout3075|369K|120 / cart2177|262K|120 / **reco2050|545K|266(パケット中・バイト大=判別対象)** / currency1538|212K|138 / shipping1058|113K|107 / redis843|116K|137 / email279|40K|143 / ad272|35K|128 / payment231|29K|127。取得=promq pod で container_network_{receive,transmit}_{packets,bytes}_total を rate[3m]、redirect(>file)は空になるのでpipe必須。km2/all/netmeasure.sh も同機能(normal張り直し版)。

**front4(閲覧パス束ね=frontend+reco+catalog+cart+redis 1Pod, 内部5ホップ全localhost, 3cycle, 2026-07-06):softirq/req=0.826±0.032(−30.1%)。用量反応上側が埋まった:frontcatalog0.996(-16%)<front4 0.826(-30%)<mega0.564(-52%)。** 全3cyc frontend replicas=1(HPA70%未満でスケールせず,fails0)。資産 km2/frontrecocatalogcart/(4サービス+redis同居, HPA同梱, catalog/cartのServiceはapp=frontend, reco 8080→8090remap, reco→catalogもlocalhost) + km2/all/frontrecocatalogcart-softirq.sh, results-front4.csv, arm=front4。**【重要発見=削減は加算的additive】** 各単独束ねの削減 frontcatalog0.185+frontreco0.114+frontcart0.058=0.357 ≈ front4の削減(1.181-0.826=0.355)に誤差0.5%で一致。物理的に自然(各エッジのbridge通過コストは独立→localhost化で各々消え足し算)。**→予測則:多サービス束ねの削減=各エッジ単独削減の和。以前の"パケット比例"より筋が良い。**(留保:加算性検証は1点+物理裏付け, ただし0.5%一致は強い) [[hpa-scaling-angle]]

**残:** ①②⑤⑥済(⑥=判別しバイト寄り) ⑦済(front4で上側+加算性発見) ③/proc/softirqs NET_RX/TX で裏取り ④Istio注入で増幅(Envoy税)=novel性の主軸候補 ⑦閲覧パス全束ねでmega近くまで=用量反応上側 ⑧エッジ単位パケット/バイト実測でバイト説を確定(同バイト・大×少 vs 小×多 で softirqがパケット数で決まることを示す=ICTerのバイトaffinityへの反証)。論文枠: softirq=通信コストの下限, app=対照, paymail/outmail/outpy=切り分け対照, パケット率=用量反応の説明変数, エコー法(p99-16%)を傍証。先行ICTer2022との差(=[[related-work-coloc]]): 指標(バイト→実CPU)/粒度(統合→分離保持Pod)/Envoy税の軸。ただし「重いペアを束ねよ」はICTerと共通=差にならない→novelにするには⑥(バイトでなくパケットが効く)か④(Envoy税)が要。

関連: [[bundling-merit-question]] [[megapod-latency-experiment]] [[coloc-resource-efficiency-study]] [[plana-echo-comm-time]] [[related-work-coloc]]
