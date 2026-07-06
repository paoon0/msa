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

**HPAスイープ第一歩=完了(normal+全アプリHPA CPU70%/1-4, users80/240/480 rate40, 各1計測=スモーク級, 2026-07-06, km2/all/hpa-sweep-softirq.sh/results-hpasweep.csv):結論=HPAがスケールしても softirq/req はほぼ一定(フラット)。** 実測: users80→240→480 で rps239→648→909, 総レプリカ11→19→28(約2.5倍), しかし **softirq/req 0.950→0.916→0.906(微減=実質フラット)**。app/req~10.7, node/req~12 も安定。p99は780→850→1400msでusers480は単一ノード飽和onset。**∴softirqは本質per-request(per-packet)コスト。HPAスケールアウト=同じパケットを複数Podに分散するだけ→エンドポイント/コネクション増は softirq/req を悪化させない(当初の"微増"予想は否定)。** 注意:①ライブのpromq Prometheusクエリが高負荷でタイムアウト→全NA→履歴クエリ(time=)で復元(netmeasureと同手)。**次のHPAスクリプトはprom_scalarにリトライ必須。** ②各レベル1計測のみ(反復なし)=トレンドは確かだが本走より低精度。③この0.92はRATE40/複数レプリカ条件でRATE1/1レプリカ本走normal1.18とは直接比較不可(スイープ内トレンドで解釈)。HPA設定はkubectl autoscaleで実行時作成(normalは個別マニフェスト構成ゆえ。front4はyaml同梱)。

**HPA比較(束ね vs 分離)=完了・強い結果(2026-07-07, km2/all/hpa-compare-softirq.sh/results-hpacompare.csv):** 束ね=front3(frontend+reco+catalog の3ステートレスを1Pod, HPAは束ねPodのみ) vs normal(同3サービス個別HPA)。cart+redisは両arm分離・固定1(redis分裂回避のためユーザ指示でcartごと束ねから外した。frontrecocatalogcart.yamlはcart/redis抜き3コンテナに改修+cartservice.yaml追加, front CART_ADDR=cartservice:7070)。HPA CPU70%/1-4, users80/240/480 rate40, 各1計測(スモーク級)。**結果(front3 vs normal): softirq/req 80:0.809vs0.911(-11%)/240:0.545vs0.941(-42%)/480:0.631vs0.905(-30%)=束ねが全レベル低く高負荷で差拡大。★スループット 240:712vs618(+15%)/480:965vs656(+47%)=束ねが高負荷で圧倒(normalは656rpsで飽和頭打ち、束ねは965まで伸びる)=通信softirqに食われるCPUを空けた分を実仕事に回せる→「co-locationで資源効率↑」をHPA=ノードあたり容量で実証。Pod数 240:束ね2 vs 分離8=束ねは少Pod(粗い粒度)。** fails全0。留保:各点1計測(要3cycle反復), 束ねはfrontend単体を過少配置しがち(粒度損), users480のp99は処理rps違うので単純比較不可, normal frontendがmax4中3止まり理由(飽和throttleでHPA誤認?)要精査。**prom_scalarはリトライ+promq死活確認を入れてNA全滅を防いだ(前回の教訓)。**

**3サイクル反復で確度確認=完了(2026-07-07, users240/480のみ, 毎cyc+arm再デプロイでレプリカ1リセット, results-hpacompare.csv 12点):**
- **①softirq/req削減=堅い(3cyc一貫): u240 束ね0.595±0.024 vs 分離0.933±0.034(−36%), u480 束ね0.561±0.081 vs 分離0.916±0.010(−39%)。差はsdの4〜15倍=明確有意。co-locの通信削減はHPA下でrobust。** これが確定主結果。
- **②スループット優位=実在するがHPA依存: 平均 u240+12%/u480+29%。ただしu480束ねは cyc1/2=965/956rps(+46%) vs cyc3=634rps と大ばらつき(sd154)=cyc3でHPAが束ねを2レプリカで止めた(スケールアップ失速)。束ねはHPAがちゃんとスケールすれば+46%、失速で優位消失。**
- **③Pod数=束ね2〜4 vs 分離常に8(束ね圧倒的少)。**
- **④新論点=堅牢性vs効率トレードオフ: 分離は毎回確実に8Podまで増える(堅牢だが飽和で~660rps頭打ち=非効率)。束ねは1つのHPA判定依存=効率高いが判定ミスに弱い(脆い)。=「束ね=効率↑だがスケール粒度粗く判定ミスに弱い」co-locationの本質トレードオフが数字化。**

**次:** ①束ねのHPAスケール失速(cyc3)の原因精査(単一HPA判定の脆さ, スケール判定閾値/安定化窓) ②偏り負荷での粒度損(C案) ③論文化: 主張=「co-locはsoftirq(HPA不可視)を削り, HPA下でノードあたり容量↑(softirq/req -36〜39%堅い, スループット+最大46%だがHPAスケール依存), 代償はスケール粒度と単一HPA判定の脆さ」。
- **C(裏面):** 片側だけ負荷が偏るワークロードで束ねPodの粒度損を測る=トレードオフ定量(廃止した案B需要相関ρとは別。メリット前提でなくコスト測定なので可)。

計測の型は softirq 実験と同じ(exp ns, Istio無し, resources=all値, USERS/RATE, promq経由Prometheus)。実験資産は `km2/all/`。

関連: [[softirq-cpu-metric]] [[bundling-merit-question]] [[coloc-resource-efficiency-study]] [[related-work-coloc]]
