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

**残:** ①済(本走3サイクルで差>ノイズ確認) ②済→**paymail(同居のみ)+outmail(軽ホップlocalhost)で「同居だけ/軽ホップlocalhostでは減らない・mega半減は重ホップ束ねの効果=用量反応」を実証** ③/proc/softirqs の NET_RX/NET_TX で種別裏取り ④Istio注入で増幅(Envoy税) ⑤重ホップ(frontend同居など)の中間バリアントで用量反応を定量化。論文枠: softirq=通信コストの下限, app=対照, paymail/outmail=切り分け対照(同居/localhost/トラフィック量の分離), エコー法(p99-16%)を傍証, 限界(node単位ゆえ差で取り出す)を明記。

関連: [[bundling-merit-question]] [[megapod-latency-experiment]] [[coloc-resource-efficiency-study]] [[plana-echo-comm-time]] [[related-work-coloc]]
