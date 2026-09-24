# k6 — 開ループ負荷生成(2026-07-15〜)

locust(閉ループ: 返事を待ってから次を送る)では、遅くなると送る量も減って「双安定」になり真の容量が測れない。
k6 の `constant-arrival-rate`(開ループ: 返事に関係なく一定レートで送る)に替えて、容量の崖を測る。
summer2026 以降の実験(`bundle-vs-loss2.sh`)も負荷生成はこの `checkout.js` + `k6-job.yaml` を使う。

| ファイル | 役割 |
|---|---|
| `checkout.js` | シナリオ定義。購入型 = `GET /product/{id}` → `POST /cart` → `POST /cart/checkout` で 1 周。閲覧型(browse)= `GET /product/{id}` のみ。`WARMUP`+`MEASURE` 秒走り、`dropped_iterations` は窓に切り直して集計 |
| `k6-job.yaml` | k6 を Job として namespace `exp` に流すマニフェスト(レート・VU 数は env で注入) |
| `run-k6-sweep.sh` | 固定台数(`REPLICAS`, HPA 無し, requests=`REQ_M`)で `RATES` を掃引し、達成レート/dropped/p50-p99/各サービス CPU を CSV に記録。アームは `normal` と `bundle`(=frontrecocatalogcart) |
| `k6-sweep.csv` / `k6-sweep.log` | 上の既定出力(最新の走行) |
| `k6-sweep-run1.csv` | 初回スイープ |
| `k6-sweep-3arm-3cyc.csv` / `.log` | 3アーム×3サイクルの本走 |
| `t3.*`, `t4.*` | 回収バグ修正時の検証走行(t4 が修正後) |

CSV 列: `arm,target_rate,iter_rate,rps,dropped,failed_rate,p50,p90,p99,avg,node_cores,hot`(`hot` = CPU 利用率上位のコンテナ)。
1 周 = 3 HTTP リクエストなので `rps ≈ target_rate × 3`。容量の膝 = `iter_rate` が `target_rate` に届かない / `dropped>0` / p99 急上昇。

結論は memory `openloop-k6-capacity`, `fixed-replica-k6` を参照。
