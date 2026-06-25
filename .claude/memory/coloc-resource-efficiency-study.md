---
name: coloc-resource-efficiency-study
description: Container co-location experiment — why comm-time shows no difference and the pivot to resource-efficiency metrics
metadata: 
  node_type: memory
  type: project
  originSessionId: d2cea3bd-2c2c-4109-8e64-b9f6f7d126fa
---

修士研究: K8s で複数アプリコンテナを1 Pod に同居(localhost 通信)させると、細分化(1 Pod 1 サービス, ClusterIP DNS 通信)より計算資源効率が上がる、を示す。checkout↔email ペアで検証中。

**2026-06-15 の判明事項:** 現在のクラスタは**単一ノード**(mizuki-nuc12wshi7)で **Envoy 未注入**(default ns に istio-injection ラベル無し)。この条件では同居 vs 分離で email RPC の**通信時間がほぼ変わらないのが物理的に正しい**。理由: ①単一ノードなので分離でも同一ノード内 veth+bridge+iptables(kube-proxy DNAT)で完結しサブms、②gRPC は永続接続(checkout の emailSvcConn は起動時1本)なので DNAT は接続確立時のみ、リクエストあたりでは localhost と経路コストがほぼ同一、③計測値は emailservice の Jinja2 render(GIL 直列, CPU 200/300m)に支配される。

**方針転換(ユーザー選択):** 主指標を通信時間 → **資源効率**へ。単一ノード・Envoy 無しのまま、CPU/req を2層で測る → ①アプリ CPU(`container_cpu_usage_seconds_total` cgroup, 両トポロジで≒同じ=対照群)と ②ノード全体 CPU(`node_cpu_seconds_total` softirq 込み, 同居の削減はここに出る)。主張は「②−①=通信に費やす kernel CPU/req」が同居で下がること。サブ指標=飽和前の最大スループット(負荷スイープ)。軽負荷(80req/s, ノード3%)では差が小さい懸念があり、飽和近くまで負荷を上げるのが事実上必須。資源の少ないマシン(`kubernetes-manifests/`)で CPU を絞ると差が際立つ。

計測の核: `src/checkoutservice/main.go` の `sendOrderConfirmation` が email RPC を time計測し `grpc_client_latency_seconds`(独自 Histogram, labels=source/destination/method)に記録。分母= `grpc_client_latency_seconds_count{destination="emailservice"}` = 成功 PlaceOrder 数。

**実験 namespace は `exp`**(default ではない)。exp に全スタックが常駐、現在は分離トポロジ(emailservice 独立 Pod, Envoy 無し)。スクレイプは `exp` の ServiceMonitor `checkoutservice-monitor`(selector app=checkoutservice, port metrics=9464, /metrics, 5s)経由で**機能確認済み**(`up{service="checkoutservice"}=1`)。loadgen は Job/Pod として走り Completed で終わる。exp ns に istio-injection ラベル無し。

**初回計測結果(2026-06-15, results.csv, 各1回):** 負荷条件は揃った(separated/colocated とも RPS≒79.5, req≒47.7k, 窓600s)。app CPU/req ≒同じ(41.9 vs 43.0=対照群OK)。**node CPU/req(背景差引)は colocated が約2%低い(40.885 vs 41.736 mCPU·s/req)= 仮説どおりの向き**。ただし(a)1回ずつでノイズ判定不能、(b)baseline が 0.74 vs 0.70 と 0.04 cores ずれ差の半分を説明しうる、で**まだ非結論的**。

**スクリプトの既知バグ:** `net_cpu_per_req`(=node−app)列は両方負値で使い物にならない。原因=node 側は idle baseline(アプリ Pod の idle CPU 込み)を引くのに app 側は負荷時フルを引く二重差引。**見出し指標は net ではなく node_cpu_per_req のトポロジ間比較を使う**こと。

**次回の TODO(優先順):** ①measure_cpu_per_req.py の net 定義修正 + 「同一RPSでの総ノードCPU(cores, 背景差引なし生)」列を追加 → ②各トポロジ3〜5回反復で平均±ばらつき → ③負荷を飽和近くまで上げるスイープ(サブ指標=最大スループット)。loadgen は exp に `kubectl apply -f km2/loadgenerator.yaml -n exp`、同居切替は `km2/outmail/outmail.yaml`。計測は run 完了後に `--port-forward measure --topology <sep/colo> --baseline <①の値>`。

関連: [[monitoring-stack]] [[exact-window-measurement]]
