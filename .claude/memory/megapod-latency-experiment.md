---
name: megapod-latency-experiment
description: 全部入りPod(megapod) vs 分離 の1リクエスト遅延比較 — 低負荷では正味差なし。CPU/reqへ転換中。
metadata: 
  node_type: memory
  type: project
  originSessionId: 36fe70d4-73ca-49de-8cd1-9ee9a0b6def6
---

2026-06-29。「直接通信するサービスを**全部1 Podにまとめる(megapod)**と1リクエストが速くなるか」を実機計測。資産は `km2/experiments/`。

**計測方法:** locust の**クライアント側エンドツーエンド応答時間**(loadgen→frontend の1往復、frontend が待つ下流gRPCツリー全部込み)。frontend ハンドラは**逐次** gRPC を待ってから HTML を書き出す(`src/frontend/handlers.go`)ので、全ホップ遅延が足し算で1つの数字に入る。locust `--csv` の "Aggregated" 行(p50/p90/p99/avg/rps)を取得。フローは index/product/cart/**checkout** の4種HTTP(checkoutが最も深いツリー)。

**結果(3サイクル, 各4分ウォームアップ+7分本計測, ~215rps, 単一ノード, Istio無し):正味の遅延差なし。**
- 最安定指標 **avg = normal 80.7 vs mega 81.0ms ≒ 同一**。p50 51 vs 53。
- **p99 はラン間ノイズに埋没**(normal p99 単独で 420→780→800 と振れ、mega 730–860 と範囲が重なる)。支配的ばらつきは arm間でなくサイクル間=効果でなくノイズ。
- 初期に「mega が p90−31%/p99−23%で速い」と速報したが、(a)汚染データ+(b)単一cycle由来で**撤回**。
- 物理と整合: 低負荷・単一ノードでは1ホップ削減(数十〜数百µs)が ms規模の処理+スケジューリング揺らぎに埋もれる([[coloc-resource-efficiency-study]] [[related-work-coloc]])。
- per-endpoint では `/cart/checkout`(深いツリー)の裾が最も動くが noisy。

**→ 主指標を 遅延 から CPU/req(資源効率)へ転換中。** 理由: 通信処理は消えず**CPUとして焼かれる**(NotNets: CPUの25-40%しか業務ロジック)。CPUは足し算なので latency が隠した差を拾える可能性。`compare.sh` に Prometheus 取得を**統合済み**(列 node_cores/app_cores/**node_mc_per_req**(ミリコア秒/req,主)/app_mc_per_req=対照)。**ただしスモーク中にユーザ指示で中止=未完走。** 懸念: 215rps(ノードCPU 3%)では CPU差も小さい→**①負荷を飽和近くへ上げる**②**Istio注入**(Envoy税11→1で増幅)が要る。

**実験資産 `km2/experiments/`:**
- `all.yaml` = 11コンテナ1 Pod(megapod)。ポート衝突回避で **email 8080→8081 / reco 8080→8082 / shipping 50051→50052**、全 `*_SERVICE_ADDR` を localhost 化。per-コンテナ requests は分離と同一(公平比較)。合計~6.3vCPU(単一ノード16vCPUに余裕で収まる)。
- `loadgen-csv.yaml` = locust headless+`--csv`、末尾でCSVを stdout に出し**keep-alive `sleep 600`**で生存。RUN_TIME は compare.sh が差し込む。
- `compare.sh` = normal(分離,Istio無し化パッチ)↔mega を warmup→measure で交互×CYCLES。env: `CYCLES/WARMUP/MEASURE`(例 `CYCLES=3 WARMUP=4m MEASURE=7m`)。結果 `results-compare.csv`。実験ns=**exp**。

**再現で踏んだ罠(重要・全て対処済み):**
- frontend は `SHOPPING_ASSISTANT_SERVICE_ADDR` 未設定で panic(機能無効でも値必須)。
- loadgen CSV回収: **終了直後の `kubectl logs` は空読みレース** → keep-alive で生かし**生存中ポーリング**で読む。
- `python3 - <<'PY'` は**ヒアドキュメントが stdin を占有**しpipeのログが届かない → ログは**ファイルargv渡し**。
- loadgen Pod 解決で**前段ウォームアップの残存Podを掴むと warmup値を誤記録** → 残存Pod消滅待ち+`--sort-by=creationTimestamp` の最新Pod採用。
- **port-forward はこの bash 環境で signal kill(exit 144)** → Prometheus は**在クラスタ curl Pod + `kubectl exec`**(`promq` Pod, svc `prometheus-grafana-kube-pr-prometheus.monitoring:9090`)。
- `pkill -f 'compare.sh'` は**自分のコマンド行も殺す** → ブラケットトリック `'compare[.]sh'`。

関連: [[bundling-merit-question]] [[coloc-resource-efficiency-study]] [[monitoring-stack]] [[exact-window-measurement]]
