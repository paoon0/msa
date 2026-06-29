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

**残:** ①本走の複数サイクルで softirq_mc の差>サイクル間ノイズ を確認 ②ヌル対照(normal vs normal で差≈0) ③/proc/softirqs の NET_RX/NET_TX で種別裏取り ④Istio注入で増幅(Envoy税)。論文枠: softirq=通信コストの下限, app=対照, エコー法(p99-16%)を傍証, 限界(node単位ゆえ差で取り出す)を明記。

関連: [[bundling-merit-question]] [[megapod-latency-experiment]] [[coloc-resource-efficiency-study]] [[plana-echo-comm-time]] [[related-work-coloc]]
