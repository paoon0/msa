# namespace exp の削除記録 (2026-10-17)

Sock Shop に移るため、ユーザの許可を得て `kubectl delete namespace exp` を実行した (2026-10-17 08:28 ごろ)。
削除の直前に、中身をこのフォルダへ YAML で保存した (認証情報は含まれない。Secret と PVC は exp に無かった)。

## 消えたもの (削除直前の状態、pdist-k3 同居本走の終了後)

| 種類 | 数 | 中身 | 戻し方 |
|---|---|---|---|
| Deployment | 9 | adservice, currencyservice, emailservice, frontend, paymentservice, productcatalogservice, recommendationservice, redis-cart, shippingservice (最後のアーム pairsQ3 の状態。cart/checkout は同居側に入っていたので単独の Deployment が無い) | `kubectl apply -n exp -f km2/normal/` (ドライバは毎回アームごとに apply し直すので、元の状態に戻す必要はない) |
| Service | 21 | 11 サービス + gRPC 負荷分散用の `-hl` (headless) 10 本 + frontend-external | normal の apply と `grpc_lb_patch.py` (ドライバが毎回作る) |
| HPA | 8 | ContainerResource 70% (ドライバが毎回作り直す) | ドライバ |
| ReplicaSet / Pod | 24 / 10 | 上の Deployment の世代と Pod | — |
| ConfigMap | 3 | `k6-script` (k6 のシナリオ。ドライバが毎回作る)、`istio-ca-root-cert`, `kube-root-ca.crt` (自動生成) | ドライバ / 自動 |
| ServiceAccount | 12 | 各サービス + loadgenerator + default | normal の apply |
| Pod `promq` | 1 | curlimages/curl。ドライバが Prometheus に問い合わせるための Pod (2026-10-16 00:10 作成) | ドライバ |
| PodMonitor | 3 | istio-envoy (payment), istio-envoy2 (checkout), istio-envoy3 (email)。Istio 時代の監視設定で、現在は使っていない | `podmonitors.yaml` から apply |
| ServiceMonitor | 1 | checkoutservice-monitor (app=checkoutservice) | `servicemonitors.yaml` から apply |

消えていないもの: namespace `monitoring` (Prometheus / Grafana、6 Pod)、`istio-system` (2 Pod、注入はしていない)、`kube-system`。

## ファイル

- `deployments.yaml`, `services.yaml`, `horizontalpodautoscalers.yaml`, `configmaps.yaml`, `serviceaccounts.yaml`, `podmonitors.yaml`, `servicemonitors.yaml`, `pod-promq.yaml` — `kubectl get <種類> -n exp -o yaml`
- `state.txt` — `kubectl get pods,deploy,hpa -n exp -o wide`

Online Boutique の実験を再開するときは、`km2/normal/` と `bundle-vs-loss2.sh` で立て直せる。PodMonitor / ServiceMonitor だけはリポジトリに同じ定義が無い可能性があるので、必要ならここの YAML を使う。
