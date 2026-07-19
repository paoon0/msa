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

**option A 完了(既存 results-sweep.csv だけで算出):** 盲点=softirq/app。負荷スイープ rps239/476/595/677 で normal 8.7→7.8→6.9→6.9% / mega 4.6→4.2→4.1→3.9%。**co-locが盲点を毎レベル約半分(1.7-1.9倍)に、飽和近く677rpsまで持続**(低負荷限定でない)。softirq/nodeでも normal6.3→5.4%/mega3.2→3.1%。図=`km2/experiments/hpa-blindspot.svg`(matplotlib/pip無い環境ゆえ手書きSVG生成)。

**HPAスイープ第一歩=完了(normal+全アプリHPA CPU70%/1-4, users80/240/480 rate40, 各1計測=スモーク級, 2026-07-06, km2/experiments/hpa-sweep-softirq.sh/results-hpasweep.csv):結論=HPAがスケールしても softirq/req はほぼ一定(フラット)。** 実測: users80→240→480 で rps239→648→909, 総レプリカ11→19→28(約2.5倍), しかし **softirq/req 0.950→0.916→0.906(微減=実質フラット)**。app/req~10.7, node/req~12 も安定。p99は780→850→1400msでusers480は単一ノード飽和onset。**∴softirqは本質per-request(per-packet)コスト。HPAスケールアウト=同じパケットを複数Podに分散するだけ→エンドポイント/コネクション増は softirq/req を悪化させない(当初の"微増"予想は否定)。** 注意:①ライブのpromq Prometheusクエリが高負荷でタイムアウト→全NA→履歴クエリ(time=)で復元(netmeasureと同手)。**次のHPAスクリプトはprom_scalarにリトライ必須。** ②各レベル1計測のみ(反復なし)=トレンドは確かだが本走より低精度。③この0.92はRATE40/複数レプリカ条件でRATE1/1レプリカ本走normal1.18とは直接比較不可(スイープ内トレンドで解釈)。HPA設定はkubectl autoscaleで実行時作成(normalは個別マニフェスト構成ゆえ。front4はyaml同梱)。

**HPA比較(束ね vs 分離)=完了・強い結果(2026-07-07, km2/experiments/hpa-compare-softirq.sh/results-hpacompare.csv):** 束ね=front3(frontend+reco+catalog の3ステートレスを1Pod, HPAは束ねPodのみ) vs normal(同3サービス個別HPA)。cart+redisは両arm分離・固定1(redis分裂回避のためユーザ指示でcartごと束ねから外した。frontrecocatalogcart.yamlはcart/redis抜き3コンテナに改修+cartservice.yaml追加, front CART_ADDR=cartservice:7070)。HPA CPU70%/1-4, users80/240/480 rate40, 各1計測(スモーク級)。**結果(front3 vs normal): softirq/req 80:0.809vs0.911(-11%)/240:0.545vs0.941(-42%)/480:0.631vs0.905(-30%)=束ねが全レベル低く高負荷で差拡大。★スループット 240:712vs618(+15%)/480:965vs656(+47%)=束ねが高負荷で圧倒(normalは656rpsで飽和頭打ち、束ねは965まで伸びる)=通信softirqに食われるCPUを空けた分を実仕事に回せる→「co-locationで資源効率↑」をHPA=ノードあたり容量で実証。Pod数 240:束ね2 vs 分離8=束ねは少Pod(粗い粒度)。** fails全0。留保:各点1計測(要3cycle反復), 束ねはfrontend単体を過少配置しがち(粒度損), users480のp99は処理rps違うので単純比較不可, normal frontendがmax4中3止まり理由(飽和throttleでHPA誤認?)要精査。**prom_scalarはリトライ+promq死活確認を入れてNA全滅を防いだ(前回の教訓)。**

**3サイクル反復で確度確認=完了(2026-07-07, users240/480のみ, 毎cyc+arm再デプロイでレプリカ1リセット, results-hpacompare.csv 12点):**
- **①softirq/req削減=堅い(3cyc一貫): u240 束ね0.595 vs 分離0.933(−36.2%), u480 束ね0.561 vs 分離0.916(−38.8%)。差は sd の約3.6〜8倍(標本sd: u240束0.029/分0.041→~8倍, u480束0.099(cyc3失速で大)/分0.013→~3.6倍)=有意。co-locの通信削減はHPA下でrobust。** これが確定主結果。(当初"4〜15倍"は過大表現, 2026-07-07にPythonで全数再検算し訂正。%も-36.19/-38.76で一致確認。)
- **②スループット優位=実在するがHPA依存: 平均 u240+12%/u480+29%。ただしu480束ねは cyc1/2=965/956rps(+46%) vs cyc3=634rps と大ばらつき(sd154)=cyc3でHPAが束ねを2レプリカで止めた(スケールアップ失速)。束ねはHPAがちゃんとスケールすれば+46%、失速で優位消失。**
- **③Pod数=束ね2〜4 vs 分離常に8(束ね圧倒的少)。**
- **④新論点=堅牢性vs効率トレードオフ: 分離は毎回確実に8Podまで増える(堅牢だが飽和で~660rps頭打ち=非効率)。束ねは1つのHPA判定依存=効率高いが判定ミスに弱い(脆い)。=「束ね=効率↑だがスケール粒度粗く判定ミスに弱い」co-locationの本質トレードオフが数字化。**

**★しきい値方式=コンテナ別HPA(ContainerResource)実験=完了(2026-07-10, 3アーム×3cyc×u240/480, km2/experiments/hpa-percontainer-softirq.sh / results-hpapercont.csv / hpa-percontainer.yaml):** cyc3失速の正体を特定+解決。束ねPodのHPAを既定 Pod平均(Resource cpu=全コンテナ使用量÷requests合計) から **コンテナ別(ContainerResource, server/reco/catalog を各70%個別判定)** に替えると何が起きるか。3アーム= f3avg(束ね+Pod平均) / f3perc(束ね+コンテナ別) / normal(分離)。**scale_replicasは3cyc全てsd=0で完全安定。**
- **【正体】Pod平均HPAの"薄まり"を数値裏取り: u480でfrontend単体=758m=76%(>70%)なのに冷たいreco46%/catalog58%に薄められPod平均59%(<70%)→2レプリカで停止(frontend過負荷放置)。これがcyc3失速の機構。** コンテナ別なら frontend単体76%を直接見て**3レプリカへ増えfrontend52%に低下**(目標70%を守る)。=落とし穴#8の正体確定+ContainerResourceで解決。
- **【但し効果限定】この2→3レプリカ差はスループットをほぼ変えない(u480: 628→634rps, +0.8%誤差内)。理由=負荷が「1ユーザ≒1req/s」でoffered load律速→Pod増やしても捌く総量頭打ち。コンテナ別が得るのはスループットでなく「ヘッドルーム/安全マージン」(frontendを過負荷にしない, p99は1500→1300と微改善)。**
- **【粒度損の実データ化=おいしい】コンテナ別は frontend under-scale(熱いまま)を直す代わりに、冷たいreco(u480で30%)/catalog(39%)まで3台目に引き上げる over-scale を生む。Pod平均は2台で済むがfrontendが熱い。=「Pod平均=少台数だが熱いコンテナ我慢／コンテナ別=熱いコンテナ守るが冷たい相棒が無駄増殖」。決定則メモ[[coloc-bundling-decision-rule]]の「専属でも必要台数は揃わない=粒度損」を実測化。ContainerResourceは測定の薄まりは直すがPod単位複製ゆえ粒度損自体は消えない、を裏取り。**
- 束ねvs分離の大枠は不変で強い: softirq/req 束ね−38%(u240)/−56%(u480)、Pod数 2-3 vs 8。fails≈0。※前回cyc3のような失速は今回f3perc/f3avgとも起きず(3cyc安定)=再現条件はPod平均HPA×高負荷。

**★u480スループット崩落の正体=emailservice律速(2026-07-12, km2/experiments/bottleneck-diag.sh で特定):** ユーザが「今回rpsが前回より低い」と指摘→調査。**負荷の実体=locustタスクはcheckoutのみで1周=3req(GET /product+POST /cart+POST /cart/checkout), constant_throughput(1)ゆえ rps上限=users×3(u240:720/u480:1440)。u240は705≒上限で追随, u480は628=上限の44%で崩落。** 崩落原因=固定1レプリカの**emailservice(CPU制限300mと最小)が96.7%スロットリング**。checkoutはPlaceOrder内でemailのSendOrderConfirmationを同期gRPC呼び出し(エラー無視するが応答は待つ)ゆえ、emailが詰まると全checkoutが待たされconstant_throughputで offered rpsごと崩落。**checkout自身49%/frontend52%/ノード6-16コアと全部余裕なのに詰まる**のはこのため。診断法=負荷中に per-container の usage/limit/**CFSスロットリング率**を採取(container名衝突に注意=frontend/currency/cart/ad/shippingは全部"server"名で合算される。email/payment/checkout/redisは固有名)。前回の"当たり枝965"の正体もこれ=email律速が偶然緩んだ瞬間。

**★全サービスHPA化(SCALE_ALL)=ユーザ発案・スモーク検証済(2026-07-12):** 「他のコンテナもHPAできるように」→ email手動増資より筋が良い(現実的/自動で律速解消)。実装=hpa-percontainer-softirq.sh に `SCALE_ALL=1`。両アーム共通の固定サービス(checkout/cart/currency/payment/shipping/email/ad)に個別HPA(CPU70%/1-4)追加。**redisのみ除外=ステートフル固定(両アーム)。** reco/catalogは束ねでは独立HPA無し=frontendと連動スケール(co-locの定義)。**スモークf3perc u480: rps 634→962(+52%)!** email等がスケール(email2/checkout2/cart3/currency2/payment2/shipping2/ad3, total_reps20), スロットリング解消, 束ねfrontendも4レプリカ・server862m=86%まで正しく熱化しボトルネックが固定サービス→本来のスケール対象へ移動。**この962は前回の当たり枝965に一致=SCALE_ALLで再現的に到達可(運でなく)。** → 本走完了(3アーム×3cyc×u240/480, SCALE_ALL=1, results-hpapercont-allscale.csv)。**結果:**
- **u240(飽和前)=クリーンな束ね勝ち(再現性あり,sd小): rps 束ね705/703 vs 分離639(+10%), softirq/req −32%, 総Pod 12-14 vs 18。**
- **u480(飽和近く)=束ねは大勝ちできるが双安定(バイモーダル): f3perc 852±153/f3avg 749±153 vs normal 664±33。各cycで束ねは「高い枝~960」と「低い枝~630」を行き来(f3perc u480=964/636/956, f3avg=643/966/638), normalは常に~664安定。**
- **★分岐=frontend束ねHPAが4レプリカ到達したか(到達→低遅延→960, 停止→崩落→630)。コンテナ別は高い枝を3回中2回掴む(frontend4到達しやすい), Pod平均は薄まりで1回だけ=前回の"薄まり"効果がSCALE_ALL下では「高い枝を掴む確率」差として顕在化。**
- softirq/req 束ね −32%(u240)〜−46%(u480)一貫。fails=束ね112-270 vs normal0(高い枝を攻めると取りこぼし)。

**★failsの正体=多数回で確定(2026-07-13, km2/experiments/fail-capture.sh + fail-capture-multi.sh + loadgen-csv-fail.yaml で locust _failures.csv 採取):**
- 束ねのfailsは**接続リセットでなくHTTP 500**(GET /product, POST /cart, POST /cart/checkout 全て LocustBadStatusCode(code=500))。frontendが下流gRPC呼び出しに失敗して返す500。frontend自身は再起動0/Ready維持=下流の一過性欠落が原因。
- **【確定=毎回再現】下流の弱いサービス(まずemailservice, 制限300m/単スレッドPython/checkoutが同期呼び)のReadiness/Livenessプローブが1s期限にtimeout(context deadline exceeded)→一瞬NotReady→Endpoints欠落。原因はCPU不足(email 300m張り付き96.7%スロットリング=手一杯で1s以内に返事できない)。5回中5回でemailフラップ。**
- **【確率的=間欠】実際の500発生は間欠(強化前=0,0,0,4,21 fails/5runs≈2/5)。プローブフラップは常時だが、500になるのは"リクエストが一瞬NotReadyの唯一のready代替なしエンドポイントに当たった時"だけのレース。★1回だけでは「毎回出る」と誤認する=多数回必須(ユーザ指示で複数回実施し判明)。**
- **★訂正:当初「scale-upのPod入れ替えで接続リセット」は誤り。クリーンなscale-up(単発6m連続)は0 fails。**
- **★email CPU増強実験(2026-07-13, 300m→limits800m/requests600m, km2/normal/emailservice.yaml と km2/frontrecocatalogcart/emailservice.yaml 両方編集済=現在この値):結果=①emailフラップ完全消失(3/3, CPU不足がフラップ原因と確定)②スループット+20%(rps950→1150, email外すと全体が速くなる=emailは働けても詰まっていたボトルネック)③但し500は消えず"犯人が移動"(ITER1で30 fails, フラップがpayment/adに移った)=モグラ叩き。** ⇒ 500の一般原因=「小サービスの"CPU小+1sプローブ"が混雑ピークで揺れる」。**per-service CPU増はモグラ叩き、プローブtimeoutSeconds 1→5緩和が全サービス一発の general fix**(未実施, 次の候補)。probe変更前に切り分けのためCPUのみ変更した。

**★normalのrpsが伸びない理由(2026-07-13):内部サービス呼が全部クラスタnetwork越し=1リクが遅い。u240実測 p50 束ね~40ms vs normal~300ms(約7倍)。負荷がconstant_throughput(1)(各ユーザ1周/秒, 返事待ち)ゆえ"1周が遅い→こなせる回数減る"→rps頭打ち。ノードCPUは余裕(8/16)=CPU飽和でなく待ち時間律速。束ねはfront↔catalog↔recoがlocalhostで速い。softirqも約2倍(0.92 vs 0.5)の無駄。※40ms vs 300msの内訳(どのサービス待ちか)は未特定。
- **結論: email律速を外してもなお「分離=堅牢だが頭打ち(~664固定,最多Pod)／束ね=効率高いが単一HPA判定に賭ける脆さ(双安定)」トレードオフが本質として残る=これが論文の核。** 次=u480双安定を潰す試み(warmup延長でHPA定常化/束ねmin replicas上げ/HPA目標下げ→高い枝を確定的に取れるか)or双安定自体を成果として提示。

**次:** ①偏り負荷での粒度損(C案, locustを見る人/買う人に分割してoffered load律速を外す=コンテナ別の余分台数が本当に無駄かを測る) ②論文化: 主張=「co-locはsoftirq(HPA不可視)を削り, HPA下でノードあたり容量↑(softirq/req -36〜39%堅い, スループット+最大46%だがHPAスケール依存), 代償はスケール粒度と単一HPA判定の脆さ。HPA方式(Pod平均vsコンテナ別)は under/over-scale のトレードオフを切替えるレバー」。
- **C(裏面):** 片側だけ負荷が偏るワークロードで束ねPodの粒度損を測る=トレードオフ定量(廃止した案B需要相関ρとは別。メリット前提でなくコスト測定なので可)。

計測の型は softirq 実験と同じ(exp ns, Istio無し, resources=all値, USERS/RATE, promq経由Prometheus)。実験資産は `km2/experiments/`。

**★2026-07-13〜15の重要訂正(調査記録=km2/experiments/latency-breakdown/investigation-writeup.md, ただし134%等は下記で再訂正):**
- **normalの頭打ち(664rps)=HPAの過少スケール**(通信の壁ではない)。**固定台数4台にすると normal=1022rps/p50 280ms(+54%)**。HPAはCPUしか見ず多ホップ遅延(真の律速)が見えないため追加スケールしない=HPA盲点の実例。ノードは半分空き(CPU飽和でない)。台数4台なら normal も bundle も ~1000-1100rps・p50 280msで**天井同等**。
- **co-locの確かな利点は softirq(通信CPU)約半分だけ**。①レイテンシは同台数なら normal と同じ(1ユーザ床17ms同じ, localネット1ホップは元々サブミリ秒でlocalhost化しても壁時計は変わらない, 削るのはCPUで時間でない)②Pod数削減は資源メリットでない(コンテナも予約も同じ、束ねは同ノード制約でむしろ配置不利)。softirq半減も絶対値~0.5コア/1000rps≈ノード数%と控えめ。⇒単一ノードの"効率"物語は弱い。
- **双安定は負荷モデル(constant_throughput閉ループ)由来**でHPA固有でない(固定台数でも出た)。→[[openloop-k6-capacity]] で開ループ化して真容量を測る作業に移行。
- **★catalogの"134%/159%飽和"は誤読**: hot_servicesの sort_desc が"一番熱い1台(max)"を拾っていた値。**全Pod平均(HPAが見る値)は全サービス~30-67%で飽和していない**(per-container履歴クエリで確認)。→「計算サービス飽和」でなく「70%均衡+閉ループ」が頭打ちの正体。
- 論文性: 単一ノード効率は薄く、マルチノードは自明とユーザ指摘。非自明の核候補=「HPAはCPU盲点で通信/遅延律速を過少スケール」+手法提案。開ループで真容量を先に確定するのが今の一手。
- ワークロード注意: locustは**checkoutのみ**(browse系コメントアウト)=全サービス相関ρ=1・購入偏重。/logoutコメントアウト=セッション持続(問題なし)。browse復活で非相関にすれば粒度損が顕在化(C案)。

関連: [[softirq-cpu-metric]] [[bundling-merit-question]] [[coloc-resource-efficiency-study]] [[related-work-coloc]]
