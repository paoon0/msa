---
name: plana-echo-comm-time
description: 案①(エコー法で localhost vs ClusterIP の通信時間差を確認)の手法と初回結果。案Bは保留。
metadata: 
  node_type: memory
  type: project
  originSessionId: 03f972f9-2813-47a4-98bb-6d36bc73ef35
---

2026-06-24〜25、方針転換。需要相関 ρ を軸にした案B([[coloc-tradeoff-model]] / [[coloc-experiment-design]])は
**保留**し、原点の「Pod 同居で通信が速くなるか」を最小実験で確認する案①へ戻った。
案Bの計画書は `km2/approach/research_plan_B_coloc_tradeoff.md` に保存(消すな)。現 `research_plan.md` は案①。

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

関連: [[coloc-resource-efficiency-study]] [[related-work-coloc]] [[exact-window-measurement]]
