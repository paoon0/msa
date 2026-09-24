# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリのコードを扱う際のガイダンスを提供します。

## 前提

あなたは、非常に賢い情報研究学者です。本研究に従事する学生は初学者であるため、難解な言葉や数式を利用する際は、必ずわかりやすく補足をしなさい。

## このリポジトリの概要

私が修士研究で利用しているGoogle Cloud の **Online Boutique** (`microservices-demo`) のフォークです。サービス間を gRPC で通信する 11 サービス構成の EC デモアプリです。アップストリームのデモはそのまま残っていますが、このフォークでの実際の作業は `km2/` 配下にある **負荷テストとサービストポロジの実験** であり、ローカルクラスタ (MicroK8s) 上で Prometheus/Grafana 監視と組み合わせて実行します。

アプリケーション自体についてのみ問われた場合は、アップストリームのレイアウト (`src/<service>`、`protos/demo.proto`、`kubernetes-manifests/`、`release/`) が当てはまります。ここでの日常的な変更のほとんどは `km2/` と `kubernetes-manifests`と`src/loadgenerator2/` で発生します。
現在のところ利用していないディレクトリは、'.deploystack/','docs','helm-chart','istio-manifests','kustomize','protos','terraform'。
'istio/'は変更していませんが、いつでもサイドカープロキシを挿入できる状態にあります。

また本研究は、Kubernetesのpodに含まれるアプリケーションコンテナを、部分的にまとめることで、細分化された状態よりも計算資源の利用効率が高くなることを発見するための研究です。

そのため計算資源が多いものと少ないもの、計2つのマシンを利用して実験を行えるようにしています。


km2/には、計算資源が豊富なマシン用のマニフェスト、
kubernetes-manifests/には、計算資源が少ないマシン用のマニフェストが入っています。


## 実験環境のセットアップ (`km2/`)

`km2/`,`kubernetes-manifests/` はマニフェストを手作業で編集したコピーで、アップストリームの公開イメージの代わりに **独自ビルドのイメージ** をデプロイします。
- `mizuki0118/mygo:exp` — `src/` から再ビルドした Go サービス (例: checkoutservice)。
- `mizuki0118/mylocust:run1` — 負荷生成ツール。`src/loadgenerator2/` からビルド
  (注意: **`loadgenerator` ではなく `loadgenerator2`** — 使用しているのは `2` のディレクトリ)。

全ディレクトリの`kustomization.yaml`は利用せず、ディレクトリ単位でapplyしている。

### km2/ のディレクトリ構成 (2026-07 に再編、2026-09-18 にバリアントを `variants/` へ集約。パスが変わったので注意)

- `km2/normal/` — **分離 (1 Pod 1 サービス) の各サービスマニフェスト**。比較のベースライン。`CMD` (認証情報メモ) と個別 `loadgenerator.yaml` もここ。
- `km2/variants/` — **ベースライン以外のトポロジをすべてここに集約** (2026-09-18 まで `km2/` 直下にあった)。
  - `all/` — `all.yaml` (全 11 コンテナを 1 Pod に同居させた megapod) と `README.md`。
  - `frontrecocatalogcart/` — **束ね (front3): frontend+recommendation+productcatalog を 1 Pod に同居**したトポロジ (主力の co-location アーム)。
  - `frontcart/`,`frontcatalog/`,`frontreco/`,`outmail/`,`paymail/`,`outpaymail/`,`outpy/`,`productshipping/` — 部分集約バリアント (下記)。
- `km2/experiments/` — **実験の実体** (2026-09-18 にテーマ別フォルダへ整理)。**ここで作業するときは `km2/experiments/CLAUDE.md`** (実行の作法・出力規約・アーム名↔マニフェスト対応・指標定義) を読む。人向け索引は `README.md`。
  - `shared/` — 全実験共通の負荷マニフェスト (`loadgen-csv.yaml`)。
  - `softirq/` (2026-06〜07) — 分離 vs 部分集約 vs 全部入りの softirq/req 用量反応。
  - `hpa/` (2026-07) — HPA 下の比較、ボトルネック診断、fails の正体。
  - `latency-breakdown/` — レイテンシ分解と固定台数 (HPA 無し) スイープ。
  - `k6/` — k6 による開ループ負荷生成 (summer2026 以降の標準)。`k6/README.md`。
  - `perservice-cpu/` (2026-08-18) — サービス別利用率カーブ (枠適正化の元データ)。
  - `summer2026/` (2026-08〜09) — **主力実験**。ドライバ `bundle-vs-loss2.sh`、索引 `EXPERIMENTS.md`、解析 `analysis-*.md`。`smoke/` はスモーク出力、`manifests/` は夏休み用束ねマニフェスト。
  - `edge-traffic/` (2026-09-08〜10) — サービスペア単位の通信量実測と ICTer 指標の再現。
  - `archive-202606/` — 6 月の初期 megapod 実験 CSV。
  - ログの扱い: `*.log` のうち論文の数値出所 (`FOSE2026-TeX-UTF8/fose2026-data-provenance.md`) やスクリプトから参照されるものは生データなので消さない。`last-logs-*.txt` 等は再生成されるので削除可。
- `km2/approach/` — 研究計画・記録・先行研究メモ・HPA 実験手順書 (`hpa-experiment-method.md`)。`echo/`,`comm-experiment/` は初期の通信時間実験。
- `km2/locust/` — アドホックな locust マニフェスト。
- `FOSE2026-TeX-UTF8/` (リポジトリ直下) — FOSE2026 投稿論文の TeX 一式。`submitted-20260914/` が提出時スナップショット、`fose2026-data-provenance.md` が全数値の出所と再計算スクリプト。

スクリプトは絶対パス参照なので、これらを移動する際は参照側 (`km2/experiments/**/*.sh`、`.claude/memory/`、`~/.claude/projects/.../memory/`、`km2/approach/`、`FOSE2026-TeX-UTF8/*.md`) も一緒に書き換えること。

### トポロジのバリアント (実験の本題)

`km2/variants/` の各サブディレクトリは、それぞれ異なるサービス配置の実験です。テストしているパターンは、**複数のサービスを 1 つの Pod 内にサイドカーとして同居させる** (`localhost` 経由で通信) 方式と、通常の 1 Pod 1 サービス構成 (クラスタの `Service` DNS 名経由で通信) 方式の比較です。バリアントの `checkoutservice.yaml`/結合マニフェストを `km2/normal/checkoutservice.yaml` (分離ベースライン) と比較すると、何が変わったか分かります。

- `outmail/` — emailservice を checkout の Pod 内へサイドカーとして移動。checkout は `emailservice:5000` ではなく `EMAIL_SERVICE_ADDR=localhost:8080` で到達する。
- `paymail/`、`outpaymail/` — payment や email を checkout と同居させる。
- `outpy/`、`productshipping/` — さらなる同居の組み合わせ。
- `km2/locust/` — アドホックな locust マニフェスト/テスト。

バリアントを編集する際、`*_SERVICE_ADDR` 環境変数が localhost 経由かクラスタ内ルーティングかを選択するもので、これが実験で操作するレバーです。

### 負荷生成ツールのつまみ

`src/loadgenerator2/locustfile.py` がユーザーのフロー (index → addToCart → checkout) を定義します。デプロイされる Job は `km2/**/loadgenerator.yaml` 内の環境変数で調整します: `USERS`、`RATE` (spawn rate)、`RUN_TIME`、`FRONTEND_ADDR`。`wait_time` は `constant_throughput(1)` なので、各ユーザーは約 1 リクエスト/秒を目標にします。

## よく使うコマンド

```sh
# --- 実験のデプロイ/撤去 (ローカル MicroK8s) ---
kubectl label namespace default istio-injection=enabled   # バリアントは Istio サイドカーを前提とする
kubectl apply -f km2/normal/                               # 分離ベースライン (ディレクトリ単位で apply)
kubectl apply -f km2/normal/loadgenerator.yaml             # 負荷実行を開始 (Job)
kubectl apply -f km2/variants/outmail/                     # 代わりに特定のバリアントをデプロイ

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

`km2/normal/CMD` は運用上のワンライナー (port-forward、PromQL クエリ、MicroK8s 証明書の更新、Grafana スナップショット URL) の個人的なメモ書きです。**平文の認証情報** も含まれています。それらは表示・コピー・コミットせず、他のファイルへ書き出すこともしないでください。

## ファイルをまたぐアーキテクチャ上のメモ

- **サービスの契約** は `protos/demo.proto` にあります。すべての gRPC サービス (Cart、Checkout、Payment、Email、Shipping、Currency、ProductCatalog、Recommendation、Ad) を定義する単一ファイルです。リクエスト/レスポンスの形を変更するには、この proto を編集してから、各サービスごとのスタブを再生成します (各 Go サービスディレクトリの `genproto.sh`)。
- **checkoutservice はオーケストレーター** です。1 回の `PlaceOrder` 呼び出しが cart、product-catalog、shipping、payment、currency、email へファンアウトします。トポロジ実験が配線し直すハブであり、ほとんどのバリアントが `checkoutservice.yaml` を中心とする理由です。
- **マニフェストは階層化** されています: `kubernetes-manifests/` (テンプレート化されており、`image:` タグを埋めるのに skaffold が必要 — 直接 apply できない)、`release/` (公開イメージを固定済みで、直接 apply 可能)、`kustomize/components/` (オプション機能: Istio メッシュ、Memorystore、Spanner、AlloyDB、shopping-assistant)、`km2/` (このフォークの独自イメージを使った実験マニフェスト)。実験向けの編集は、アップストリームのディレクトリではなく `km2/` で行います。
