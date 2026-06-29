# km2/echo — 通信時間の確認実験（案①）

処理ゼロの gRPC ping を相手に、**localhost 経路（集約）vs ClusterIP 経路（分離）**の
往復時間を比較し、Pod 同居による通信差が実機で測れるかを確認する。
計画は `km2/approach/research_plan.md`、結果と解釈は `km2/approach/research_record.md`。

## ファイル
| ファイル | 役割 |
|---|---|
| `echo-server.yaml` | fortio エコーサーバ（Deployment + Service, :8079）。ClusterIP アーム用 |
| `echo-clusterip.yaml` | 分離アーム：別 Pod から `echo-server:8079`（ClusterIP）を叩く |
| `echo-localhost.yaml` | 集約アーム：同一 Pod 2コンテナで `localhost:8079` を叩く |
| `results.csv` | 反復計測の結果（run, arm, avg/p50/p90/p99 ms） |

## 実行
```sh
# 分離アーム
microk8s kubectl apply -f km2/echo/echo-server.yaml
microk8s kubectl rollout status deploy/echo-server -n exp
microk8s kubectl apply -f km2/echo/echo-clusterip.yaml
microk8s kubectl logs echo-clusterip -n exp -c fortio | tail -12   # 末尾に target 50%/99% 等

# 集約アーム
microk8s kubectl apply -f km2/echo/echo-localhost.yaml
microk8s kubectl logs echo-localhost -n exp -c fortio | tail -12

# 後片付け
microk8s kubectl delete pod echo-clusterip echo-localhost -n exp --ignore-not-found
microk8s kubectl delete -f km2/echo/echo-server.yaml --ignore-not-found
```

## 注意
- **Istio 注入は OFF** のまま（`exp` ns）。Envoy が入ると ClusterIP 側も Envoy 経由になり経路差が濁る。
- 比較は **avg ではなく分位点（p50/p90/p99）** を見る。avg はまれな遅延スパイクでブレる。
- つまみ: `-qps`（負荷）, `-n`（総数）, `-c`（並列度）, payload を変えると差の出方が変わる。
