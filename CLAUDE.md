# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリのコードを扱う際のガイダンスを提供します。

## このリポジトリの概要

私が修士研究で利用しているGoogle Cloud の **Online Boutique** (`microservices-demo`) のフォークです。サービス間を gRPC で通信する 11 サービス構成の EC デモアプリです。アップストリームのデモはそのまま残っていますが、このフォークでの実際の作業は `km2/` 配下にある **負荷テストとサービストポロジの実験** であり、ローカルクラスタ (MicroK8s) 上で Prometheus/Grafana 監視と組み合わせて実行します。

アプリケーション自体についてのみ問われた場合は、アップストリームのレイアウト (`src/<service>`、`protos/demo.proto`、`kubernetes-manifests/`、`release/`) が当てはまります。ここでの日常的な変更のほとんどは `km2/` と `kubernetes-manifests`と`src/loadgenerator2/` で発生します。

研究では、計算資源が多いものと少ないもの、計2つのマシンを利用しています。

km2/には、計算資源が豊富なマシン用のマニフェスト、
kubernetes-manifests/には、計算資源が少ないマシン用のマニフェストが入っています。

## 実験環境のセットアップ (`km2/`)

`km2/` はマニフェストを手作業で編集したコピーで、アップストリームの公開イメージの代わりに **独自ビルドのイメージ** をデプロイします。
- `mizuki0118/mygo:exp` — `src/` から再ビルドした Go サービス (例: checkoutservice)。
- `mizuki0118/mylocust:run1` — 負荷生成ツール。`src/loadgenerator2/` からビルド
  (注意: **`loadgenerator` ではなく `loadgenerator2`** — 使用しているのは `2` のディレクトリ)。

`km2/kustomization.yaml` がコアサービスをデプロイします。`loadgenerator.yaml` は `batch/v1` の **Job** (Deployment ではない) で、固定の `RUN_TIME` だけ実行して終了します。kustomize 経由ではなく、個別に適用します。

### トポロジのバリアント (実験の本題)

`km2/` の各サブディレクトリは、それぞれ異なるサービス配置の実験です。テストしているパターンは、**複数のサービスを 1 つの Pod 内にサイドカーとして同居させる** (`localhost` 経由で通信) 方式と、通常の 1 Pod 1 サービス構成 (クラスタの `Service` DNS 名経由で通信) 方式の比較です。バリアントの `checkoutservice.yaml`/結合マニフェストを `km2/checkoutservice.yaml` と比較すると、何が変わったか分かります。

- `outmail/` — emailservice を checkout の Pod 内へサイドカーとして移動。checkout は `emailservice:5000` ではなく `EMAIL_SERVICE_ADDR=localhost:8080` で到達する。
- `paymail/`、`outpaymail/` — payment や email を checkout と同居させる。
- `outpy/`、`productshipping/` — さらなる同居の組み合わせ。
- `grafana/` — エクスポートしたダッシュボード JSON。`locust/` — アドホックな locust マニフェスト/テスト。

バリアントを編集する際、`*_SERVICE_ADDR` 環境変数が localhost 経由かクラスタ内ルーティングかを選択するもので、これが実験で操作するレバーです。

### 負荷生成ツールのつまみ

`src/loadgenerator2/locustfile.py` がユーザーのフロー (index → addToCart → checkout) を定義します。デプロイされる Job は `km2/**/loadgenerator.yaml` 内の環境変数で調整します: `USERS`、`RATE` (spawn rate)、`RUN_TIME`、`FRONTEND_ADDR`。`wait_time` は `constant_throughput(1)` なので、各ユーザーは約 1 リクエスト/秒を目標にします。

## よく使うコマンド

```sh
# --- 実験のデプロイ/撤去 (ローカル MicroK8s) ---
kubectl label namespace default istio-injection=enabled   # バリアントは Istio サイドカーを前提とする
kubectl apply -k km2/                                      # コアサービス (kustomize)
kubectl apply -f km2/loadgenerator.yaml                    # 負荷実行を開始 (Job)
kubectl apply -f km2/outmail/                              # 代わりに特定のバリアントをデプロイ

kubectl get pods
kubectl port-forward deployment/frontend 8080:8080        # :8080 でストアを閲覧
kubectl logs -f job/loadgenerator                         # 負荷実行を監視

# --- src/ を変更した後に独自イメージを再ビルド ---
docker build -t mizuki0118/mylocust:run1 src/loadgenerator2 && docker push mizuki0118/mylocust:run1
docker build -t mizuki0118/mygo:exp      src/checkoutservice && docker push mizuki0118/mygo:exp

# --- アップストリームのアプリ全体ワークフロー (全イメージをビルド) ---
skaffold run     # ./kubernetes-manifests 経由ですべてをビルド + デプロイ
skaffold dev     # 同上。ファイル変更時に自動再ビルド
skaffold delete  # 撤去

# --- サービスごとのテスト (サービスのディレクトリから実行) ---
# productcatalogservice / その他の Go サービス:
cd src/productcatalogservice && go test ./...
go test -run TestNameRegex ./...   # 単一のテスト
```

`km2/CMD` は運用上のワンライナー (port-forward、PromQL クエリ、MicroK8s 証明書の更新、Grafana スナップショット URL) の個人的なメモ書きです。**平文の認証情報** も含まれています。それらは表示・コピー・コミットせず、他のファイルへ書き出すこともしないでください。

## ファイルをまたぐアーキテクチャ上のメモ

- **サービスの契約** は `protos/demo.proto` にあります。すべての gRPC サービス (Cart、Checkout、Payment、Email、Shipping、Currency、ProductCatalog、Recommendation、Ad) を定義する単一ファイルです。リクエスト/レスポンスの形を変更するには、この proto を編集してから、各サービスごとのスタブを再生成します (各 Go サービスディレクトリの `genproto.sh`)。
- **checkoutservice はオーケストレーター** です。1 回の `PlaceOrder` 呼び出しが cart、product-catalog、shipping、payment、currency、email へファンアウトします。トポロジ実験が配線し直すハブであり、ほとんどのバリアントが `checkoutservice.yaml` を中心とする理由です。
- **マニフェストは階層化** されています: `kubernetes-manifests/` (テンプレート化されており、`image:` タグを埋めるのに skaffold が必要 — 直接 apply できない)、`release/` (公開イメージを固定済みで、直接 apply 可能)、`kustomize/components/` (オプション機能: Istio メッシュ、Memorystore、Spanner、AlloyDB、shopping-assistant)、`km2/` (このフォークの独自イメージを使った実験マニフェスト)。実験向けの編集は、アップストリームのディレクトリではなく `km2/` で行います。
