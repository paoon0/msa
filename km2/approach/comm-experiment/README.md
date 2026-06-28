# outmail 通信時間 実験（echo を使わず本物の checkout→email/payment を計測）

最終更新: 2026-06-28 / 担当セッションからの引き継ぎメモ。詳細な背景は記憶 `planA-echo-comm-time.md` 参照。

## これは何か
`mizuki0118/mygo:bunpupaymail`（checkout を細バケット化＋payment計測追加したイメージ）で、
- 分離アーム … `km2/checkoutservice.yaml`（EMAIL=`emailservice:5000` = ClusterIP）
- 同居アーム … `km2/outmail/outmail.yaml`（EMAIL=`localhost:8080`）
を交互に走らせ、checkout→email / checkout→payment のレイテンシ分布を比較した。
payment は両アームとも ClusterIP のまま＝**ラン内対照群**（ラン間ノイズの推定に使う）。

## 計測コード（src/checkoutservice/main.go, コミット済み 233e9af）
- `grpc_client_latency_seconds` のバケットを `ExponentialBuckets(50e-6, 1.5, 30)`（50µs〜6.4s）に変更。
- `chargeCard` に payment 計測を追加（`destination="paymentservice"`, `method="Charge"`）。

## 結果（results-20260628.csv, 各6分80users, Istio未注入, cycle3は失敗で除外）
- 絶対値では email 同居 mean −16%/p99 −40% に見えるが、**対照の payment も mean −32%/p99 −69% "改善"** ＝ラン間ノイズ。
- DiD(mean)=+0.28ms、email/payment 比も向き不定 → **co-location の通信短縮効果は検出限界以下**。
- echo（処理ゼロ）では p99 −16% が見えたのと整合。実サービスでは処理(ms)+ノイズが µs 差を隠す。

## 次の一手（感度を上げる）
A. ペイロード掃引（locust の addToCart アイテム数↑） B. Istio注入で増幅 C. 案②＝予約CPU/req へ転換。

## 実行（automation）
- `loadgen-run.yaml` … RUN_TIME 可変の負荷 Job。
- `orchestrate.sh` … apply→rollout→loadgen→Prometheus分位点をCSV追記。
  ※スクリプト冒頭の `SP`/`CSV`/`REPO` パスは実行PCに合わせて要修正（元は scratchpad 直書き）。
  ※Prometheus は port-forward 9091、Grafana は CrashLoopBackOff のため直クエリで代替。
