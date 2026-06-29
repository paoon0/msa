# km2/all — 全部入り Pod (megapod)

Online Boutique の全 11 コンテナを **1 Pod に同居**させた上端アーム。
束ねる数を最大化し、全サービス間 gRPC を localhost (ループバック) 化する。
「分離 (1 Pod 1 サービス) → 部分集約 (outmail/paymail/…) → 全部入り」スイープの最右点。

## 何を変えたか (`km2/checkoutservice.yaml` などの分離構成との差分)
- 11 コンテナ (frontend / checkout / cartservice / redis / productcatalogservice /
  currencyservice / paymentservice / shippingservice / emailservice /
  recommendationservice / adservice) を 1 つの Deployment `megapod` の Pod に同居。
- **ポート振り直し** (同一 Pod = 同一 localhost なので衝突回避):
  | サービス | 元 | 変更後 |
  |---|---|---|
  | emailservice | 8080 | **8081** |
  | recommendationservice | 8080 | **8082** |
  | shippingservice | 50051 | **50052** |

  (frontend=8080, paymentservice=50051 は据え置き)
- 全 `*_SERVICE_ADDR` と `REDIS_ADDR` を `localhost:<port>` に変更。
- per-コンテナの requests/limits は分離構成の原本どおり (詰め方だけ変えた公平比較)。

## 使い方
```sh
# 分離構成を撤去 (同名 Service がぶつかるため) してから:
kubectl apply -f km2/all/all.yaml
kubectl get pod -l app=megapod -w          # 11/11 Running になるまで待つ
kubectl apply -f km2/loadgenerator.yaml    # 負荷 (FRONTEND_ADDR=frontend:80 のまま届く)
kubectl port-forward deployment/megapod 8080:8080   # :8080 でストア確認
```

## Istio 条件で測るとき
Pod の annotation `sidecar.istio.io/inject` を `"false"` → `"true"` に変えて再 apply。
全部入りでは Envoy が **1 枚**で済み、localhost 通信は Envoy を素通りする
(分離だと 11 枚 + 各ホップで両側 Envoy を通過)。差が最も大きく出る条件。

## 計測
- 通信時間: checkout の `grpc_client_latency_seconds` (Service `checkoutservice` の metrics:9464 を
  既存 ServiceMonitor が拾う)。エンドツーエンドは locust 側の p50/p99。
- 資源: 総 CPU (予約 = Σrequests は分離と同じ。実使用 = `node_cpu_seconds_total` で比較)。
- 飽和スループット: 負荷を上げて頭打ちになる req/s。

## 既知の注意
- 1 Pod の合計 requests ≈ 6.3 vCPU。**1 ノードに収まる必要がある** (Pod はノードをまたげない)。
  計算資源が豊富なマシン (`km2/`) 前提。収まらなければ requests を一律で縮める。
- 1 コンテナの crash が Pod 全体を巻き込む (故障分離の喪失) = 全部入りの代償。スイープで議論する。
- 内部通信は localhost なので個別 Service は不要。外部接続用に `frontend` / `frontend-external`、
  metrics スクレイプ用に `checkoutservice` Service のみ残してある。
