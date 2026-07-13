---
name: plana-echo-comm-time
description: エコー法で localhost vs ClusterIP の通信時間差を確認する手法と初回結果。
metadata: 
  node_type: memory
  type: project
  originSessionId: 03f972f9-2813-47a4-98bb-6d36bc73ef35
---

研究の核は「**1 つの Pod に複数コンテナ(直接通信するサービス)をまとめることが資源低減・性能向上に
つながるか否か**」。2026-06-24〜25 はその原点として「Pod 同居で通信が速くなるか」を最小実験で確認した。
現 `research_plan.md` がこのフェーズの計画書。
（※需要相関 ρ を軸にした旧「案B(トレードオフ τ モデル)」は 2026-06-29 にユーザ指示で完全停止・関連ファイル削除済み。サイドカー同居をメリット前提で精緻化する方向は採らない。）

**エコー法(なぜこの形か):** 以前 checkout→email で差が出なかったのは、測定時間に email の重い処理
(Jinja2, ms級)が混じり通信差(数十µs)が埋もれたため。→ **処理ゼロの gRPC ping** を相手にして
「測定時間≒通信時間」にする。A/Bは**宛先アドレスだけ**変える: `localhost:8079`(集約=同一Pod2コンテナ)
vs `echo-server:8079`(分離=別Pod+Service=ClusterIP経路)。

**ツール:** サーバ・ドライバとも単一イメージ `fortio/fortio`。サーバ=`fortio server -grpc-port 8079`、
ドライバ=`fortio load -grpc -ping -qps 200 -c 1 -n 30000 <addr>:8079`(分位点を直接出力)。
※当初の `moul/grpcbin`+`ghz` は ghz に公式配布イメージが無く(bojand/ghz:latest 破損)断念。
集約アームはサーバを initContainer+`restartPolicy: Always`(ネイティブサイドカー, k8s v1.32)で先に起動、
startupProbe で listen 待ち→ドライバ終了で Pod Completed。マニフェスト一式 `km2/echo/`、結果 `km2/echo/results.csv`。

**初回結果(各3回, exp ns, Istio未注入, 単一ノード):差は実在。** p50/p90/p99 は**3回とも例外なく localhost が低い**。
3回平均: p99 1.812→1.521ms(**−16%**, 裾が最大差), p90 −2.9%, p50 −3.6%。物理(loopbackは veth+bridge+conntrack を
通らない)と整合。**ただし avg は信頼度低**(run2 で localhost avg だけ逆転、まれな遅延スパイクが平均を押上げ)
→ **見出し指標は avg でなく分位点(特に p99)**。差の絶対値は小さい(数十〜数百µs)=低負荷・単一ノードでは当然。

**次の一手:** ①負荷スイープ(qps↑で飽和近く→ClusterIP側の softirq/conntrack CPU が効き差拡大か)
②ペイロード増 ③CPU/req(案②, [[coloc-resource-efficiency-study]])へ接続 ④Istio注入版で差の上限。

**2026-06-27〜28 進展: echo を使わず "本物の" outmail/paymail で通信差を可視化する段階へ。**
障害=checkout の `grpcLatency`(`src/checkoutservice/main.go` `sendOrderConfirmation`)が測る値は **通信+email処理(Jinja2 ms が支配)**、かつヒストグラムが `DefBuckets`(最小5ms)で µs 盲目。
- **実装済み(要 `docker build mygo:exp`+`rollout restart` で反映, ローカルに go 無し):**
  ①バケットを `prometheus.ExponentialBuckets(50e-6, 1.5, 30)`(50µs〜約6.4s)に変更=分布が見えるように。
  ②`chargeCard` に payment 計測を追加(同一 `grpcLatency`, `destination="paymentservice"`, `method="Charge"`)。payment は処理が軽い(Go・カード検証のみ)ので email より「測定時間≒通信時間」に近く差が出やすい見込み。
- **可視化3手法:** (A)ペイロード掃引=locust の addToCart アイテム数で email/payment へのメッセージを膨らませ通信分を ms 域へ押上げ(低コスト初手)。(B)分解法 `T通信≒RTT−サーバ処理`: 相手側に処理時間メトリクスを足し `_sum/_count` で **真の平均(バケット非依存)** を取って引く→処理スパイクが相殺し平均でも頑健。(C)負荷掃引。
- **Istio レバー:** outmail は inject=true。localhost 経路は iptables がループバックを捕捉せず **Envoy を通らない**が、ClusterIP 経路は **Envoy2枚+mTLS** を通る→Istio注入下では差が増幅し見えやすい(未注入=純カーネル差で echo と整合)。
- PromQL: `histogram_quantile(0.99, rate(grpc_client_latency_seconds_bucket{destination="..."}[5m]))` と 平均=`rate(_sum)/rate(_count)`。

**2026-06-28 本走結果(自動・8走=分離/同居 交互4サイクル, 各6分80users, Istio未注入, exp ns):結論=co-location の通信短縮効果は検出限界以下。**
イメージ `mizuki0118/mygo:bunpupaymail`(細バケット+payment計測込み, 別PCでビルド済)。分離=`km2/normal/checkoutservice.yaml`(EMAIL=emailservice:5000), 同居=`km2/outmail/outmail.yaml`(EMAIL=localhost:8080)。payment は両アームとも ClusterIP のまま=**ラン内対照群**。cycle3 は loadgen Error+throughput 79→66rps+payment p99=3912ms の異常走で除外。
- **絶対値は罠:** email 同居 mean −15.8%/p99 −40% に見えるが、**経路不変の payment 対照も mean −32%/p99 −69% "改善"** = ラン間共通ノイズ。mean のラン間ばらつき 2〜3ms が通信差(サブms)を覆う。
- **ノイズ除去後:** email/payment ラン内比 p50 −1.6%/p90 −10.9%/mean +8.5%(向き不定)。**DiD(mean)=+0.278ms**(email変化−0.659 − payment変化−0.936)=正味効果なし(むしろ微負)。
- **収穫=payment 対照群設計が "偽の勝ち" を棄却できた。** echo(処理ゼロ)で p99 −16% が見えたのと整合: 実サービスでは処理(ms)+ノイズが µs 通信差を隠す([[coloc-resource-efficiency-study]] の物理予測どおり)。
- **次の感度up:** ①ペイロード掃引(locust アイテム数↑) ②Istio注入(Envoy2+mTLS で増幅) ③案②=予約CPU/req へ転換 ④反復増+背景負荷固定でσ低減。
- 自動化資産: `scratchpad/orchestrate.sh`(apply→rollout→loadgen→Prometheus分位点をCSV追記, port-forward 9091), `loadgen-run.yaml`(RUN_TIME可変)。Grafana は CrashLoopBackOff だが Prometheus 直クエリで代替可。

**記憶の置き場所:** `/home/mizuki/.claude/projects/.../memory` は repo の `.claude/memory` への **symlink**(実体1つ)。手動同期不要、git commit で共有。

関連: [[coloc-resource-efficiency-study]] [[related-work-coloc]] [[exact-window-measurement]]
