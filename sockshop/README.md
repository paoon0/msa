# Sock Shop (修士論文の 2 つ目のアプリ)

## 取得元 (2026-10-17)

- リポジトリ: https://github.com/microservices-demo/microservices-demo (Apache-2.0、`upstream/LICENSE`)
- コミット: `9dff06fae4981921caec6a62393a6ebfce4b3e3f` (2023-12-05 "Add deprecation notice")。リポジトリは **DEPRECATED** (Weaveworks の事業終了後、更新なし)。
- `upstream/` はその `deploy/kubernetes/` から無変更でコピーしたもの:
  - `manifests/` (28 ファイル、namespace `sock-shop`)、`complete-demo.yaml` (同じ内容を 1 ファイルに結合)
  - `manifests-loadtest/` (上流の locust 負荷。使わない予定、参考)、`autoscaling/` (heapster 時代の旧 HPA。使わない、参考)
  - `design.md` (上流の `internal-docs/design.md`、アプリの設計)
- 実験用に手を入れるマニフェストは `upstream/` を直接いじらず、別フォルダに作る。

## イメージ (Docker Hub で取得可能なことを 2026-10-17 に確認)

| サービス | イメージ | 言語 |
|---|---|---|
| front-end | weaveworksdemos/front-end:0.3.12 | Node.js |
| catalogue | weaveworksdemos/catalogue:0.3.5 | Go |
| catalogue-db | weaveworksdemos/catalogue-db:0.3.0 | MySQL |
| carts | weaveworksdemos/carts:0.4.8 | Java (Spring) |
| carts-db | mongo (**タグ無し = latest**) | MongoDB |
| orders | weaveworksdemos/orders:0.4.7 | Java (Spring) |
| orders-db | mongo (**タグ無し = latest**) | MongoDB |
| payment | weaveworksdemos/payment:0.4.3 | Go |
| queue-master | weaveworksdemos/queue-master:0.3.1 | Java (Spring) |
| rabbitmq | rabbitmq:3.6.8-management (+ kbudde/rabbitmq-exporter) | — |
| session-db | redis:alpine | Redis |
| shipping | weaveworksdemos/shipping:0.4.8 | Java (Spring) |
| user | weaveworksdemos/user:0.4.7 | Go |
| user-db | weaveworksdemos/user-db:0.3.0 | MongoDB |

## 気づいた点 (立てる前に直す候補)

- carts-db / orders-db の `mongo` がタグ無し。いまの latest (MongoDB 8 系) は 2017〜2018 年の Spring のドライバと合わない可能性が高い → 古い版に固定する。
- requests/limits はサービスによって limits しか無い、または無い。ContainerResource HPA には requests が要る → 全サービスに明示する。
- readinessProbe があるのは一部のサービスだけ。
- 注意事項 (状態を持つものは同居候補から外す、Java は慣らしを長く、注文は RabbitMQ 経由で非同期など) は `km2/approach/rightsizing-procedure.md` の「Sock Shop に移すときの注意」。
