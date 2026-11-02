# Grafana ダッシュボード「設計の確認 (exp)」(2026-11-02)

全パネルがグラフ。① と requests / limits は区間の終わりの値を横棒で出す (折れ線の最後の点は区間の終わりと一致しないため)。

AI が書いた測定スクリプトとは別の経路 (Prometheus がスクリプトと無関係に記録しているもの) で、実験が設計どおりだったかを人が後から確かめるためのダッシュボード。

| ファイル | 中身 |
|---|---|
| `make_design_check.py` | ダッシュボードを組み立てるスクリプト。問い合わせ文はすべてここに書いてある |
| `design-check.json` | 上のスクリプトが書き出した定義 (Grafana に登録するもの) |

## 開き方

```sh
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
```

ブラウザで `http://localhost:3000/d/design-check` を開く。1 点の区間に合わせるときは、`-times.csv` の `prom_from` / `prom_to` (unix 秒) の後ろに `000` を付けて URL に入れる:
`http://localhost:3000/d/design-check?from=<prom_from>000&to=<prom_to>000`

## 中身

| 段 | 見るもの | スクリプトの CSV との対応 |
|---|---|---|
| ① 区間の平均 | サービスごとの CPU 使用量・Pod 数、絞り、ノード CPU・周波数・最高温度 | `usage_mc`, `pods`, `throttle_pct`, `node_cores`, `freq_ghz`, `temp_max_c` |
| ② 構成 | 台数 (設定値・実際に動いている数)、HPA の数、requests / limits | `req_mc`, `lim_mc` |
| ③ 負荷をかけた時間 | k6 の Pod が動いていたか (30 秒ごと)、k6 の CPU の立ち上がり・落ち込み | `-times.csv` の `k6_start` (正確な開始時刻は Explore で `kube_pod_container_state_started`) |
| ④ CPU の時系列 | 区間の中で CPU が安定していたか | (`-series.csv` に近い) |
| ⑤ 異常 | 再起動、Ready 落ち、絞り | — |

記録の細かさ: CPU (cAdvisor) は収集設定が 10 秒ごとだが、実際のサンプル間隔は約 11〜20 秒 (平均約 15 秒、2026-11-03 実測)。台数・設定値・Pod の状態 (kube-state-metrics) とノードは 30 秒ごと。

## 登録し直すとき

Grafana の保存先は emptyDir なので、Grafana の Pod が作り直されるとダッシュボードは消える。そのときは `python3 make_design_check.py` を実行し、Grafana の画面の「Dashboards → New → Import」で `design-check.json` を選んで登録し直す (2026-11-02 は Claude が Grafana の API で登録した)。

## 既知の制限

- ③ の k6 の Pod の状態は 30 秒ごとの記録なので、始まりと終わりは最大 30 秒ずれて見える。終わりの時刻は k6 の CPU (10 秒ごと) が落ちる時刻で見る。
- 負荷の量 (buy / view を何周/秒流したか) は、k6 (AI が書いた `../k6/checkout.js`) の記録しか無い。このダッシュボードでは確かめられない。
- 2026-11-02 時点で、Grafana の補助コンテナ 2 つ (ConfigMap からダッシュボードとデータソースを自動で読み込むもの) が、証明書エラーで再起動を繰り返している。Grafana 本体は動いていて、このダッシュボードの表示には影響しない。
