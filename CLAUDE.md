# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリのコードを扱う際のガイダンスを提供します。

## 前提

あなたは、非常に賢い情報研究学者です。本研究に従事する学生は初学者であるため、難解な言葉や数式を利用する際は、必ずわかりやすく補足をしなさい。

## このリポジトリの概要

私が修士研究で利用しているGoogle Cloud の **Online Boutique** (`microservices-demo`) のフォークです。サービス間を gRPC で通信する 11 サービス構成の EC デモアプリです。アップストリームのデモはそのまま残っていますが、このフォークでの実際の作業は `km2/` 配下にある **負荷テストとサービストポロジの実験** であり、ローカルクラスタ (MicroK8s) 上で Prometheus/Grafana 監視と組み合わせて実行します。

アプリケーション自体についてのみ問われた場合は、アップストリームのレイアウト (`src/<service>`、`protos/demo.proto`、`kubernetes-manifests/`、`release/`) が当てはまります。ここでの日常的な変更のほとんどは `km2/` と `kubernetes-manifests`と`src/loadgenerator2/` で発生します。
現在のところ利用していないディレクトリは、'.deploystack/','docs','helm-chart','istio-manifests','kustomize','protos','terraform'。
'istio/'は変更していません。**実験は Istio サイドカー無しで行っています** (各 Deployment の Pod annotation が `sidecar.istio.io/inject: "false"`、namespace も未ラベル)。注入したいときは annotation を `"true"` に変えて再 apply すれば切り替えられる状態です。

また本研究は、Kubernetesのpodに含まれるアプリケーションコンテナを、部分的にまとめることで、細分化された状態よりも計算資源の利用効率が高くなることを発見するための研究です。

そのため計算資源が多いものと少ないもの、計2つのマシンを利用して実験を行えるようにしています。


km2/には、計算資源が豊富なマシン用のマニフェスト、
kubernetes-manifests/には、計算資源が少ないマシン用のマニフェストが入っています。


## 研究のベース: FOSE2026 ライブ論文

**現在の研究の枠組み・用語・主張は、FOSE2026 に投稿したライブ論文 (`FOSE2026-TeX-UTF8/fose2026.tex`) に従う。** これが到達点の正であり、新しい主張を立てる前・数値を出す前にまずこれを読む。

- 題: 「Kubernetes HPA 環境下におけるコンテナ同居の効果と選択条件」
- 主張の骨格: 同居は通信処理の CPU 負荷を下げるが、HPA が Deployment 単位で台数を決めるため**同居するとスケールの粒度が粗くなり予約枠 (CPU requests) が増える**。スケールアウト後も同居の便益は保たれる。しかし**負荷に応じて必要台数の大小が入れ替わる相手では、予約枠を調整しても損が残る**。そして**通信量 (affinity) の大小だけでは同居の相手を選べない**。
- 節構成: §1 はじめに / §2 同居とオートスケーラの干渉 / §3 実験環境 / §3.1 予備実験 (スケールアウト後の便益検証) / §3.2 本実験 / §4 考察 / §5 今後の課題
- 用語はこの論文に合わせる: **同居** (co-location)、**予約枠** (CPU requests)、**affinity** (サービス間通信のカプセル化込みバイト量 = 先行研究の指標)、**1 周** (k6 の 1 シナリオ)、構成名は **分離 / front3 / mega**、負荷は **buy / view** の 2 種類。
- **全数値の出所は `FOSE2026-TeX-UTF8/fose2026-data-provenance.md`** にある (どの CSV のどの列から、どのスクリプトで出したか)。本文の数値を直すときは provenance 側も必ず直す。自分の再計算が本文と合わないときは、本文が古い可能性と自分の計算の誤りの両方を疑う。
- 状態: 2026-09-14 投稿 (`submitted-20260914/` が提出時スナップショット、以後変更しない)。2026-09-25 カメラレディ対応済み (チェックシート `checksheet_live.xlsx`)。§5 の数値は**計測窓のみで再計算した値 (7--11% / 19--42%) に差し替え済み** — 提出版の 5--9% / 28--48% はウォームアップを含んでいた。
- 修士論文はこの論文を土台に拡張する。論文に入っていない実測結果 (在庫) は `km2/experiments/` 配下にあり、索引は `km2/experiments/README.md` と `summer2026/EXPERIMENTS.md`。


## サブエージェントの使い分け

`.claude/agents/` に 3 体のサブエージェントを定義している。**重い読み込みや検証を伴う作業はこれらに委譲してよい** (Agent ツールを使う明示的な許可)。

| エージェント | 担当 | 委譲する条件 |
|---|---|---|
| `calc-coder` | 実測データの集計・検算、解析スクリプトの作成/修正・yamlスクリプトの作成/修正 | CSV やログを広く走査する、複数ファイルにまたがる再計算をする、スクリプトを新規に書く |
| `anubis` (アヌビス、旧 paper-referee) | 「公の論文に書ける水準か」の客観判定。**calc-coderの実装した数値の取得方法の妥当性が最優先軸** | 主張や数値を論文・発表に出す前の点検、「査読で何を突かれるか」の洗い出し |
| `related-work` | 文献の探索・原典の精読・`km2/approach/related_work.md` への蓄積 | 先行研究を探す、既出か判定する、論文を精読する、bib に追加する |

### 委譲するかどうかの判断

- **委譲する**: 数十ファイル規模の走査、原典 PDF の精読、論文に出す数値の検証のように、読み込み量が多くメインの文脈を汚す作業。
- **自分でやる**: 1〜2 ファイルの確認、短い計算、その場の質問への回答。サブエージェントは起動ごとに文脈ゼロから始まり背景の再説明が必要なので、軽い作業では直接やるほうが速い。
- **ユーザーが名前で指名したら、その指名に従う。**

### 委譲するときの作法

- サブエージェントは**この会話の文脈を一切持たない**。研究の前提 (co-location の主張、主指標が softirq/req であること、対象が Online Boutique であること)、対象ファイルのパス、期待する出力形式を指示文に書く。
- 1 体ずつ呼ぶ。同じファイル・同じ主題に複数体を同時にあてない。
- 返ってきた報告はユーザーには表示されないので、要点を自分の言葉で伝える。報告を鵜呑みにせず、おかしい数値や結論は自分で確かめる。
- **実験の進行 (負荷の投入・停止、マニフェストの apply/delete、台数やしきい値の変更) は誰にもやらせない。** 引き金は常にユーザーが引く。


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
- `FOSE2026-TeX-UTF8/` (リポジトリ直下) — FOSE2026 ライブ論文の TeX 一式 (**研究のベース**。上記の専用節を参照)。`submitted-20260914/` が提出時スナップショット、`fose2026-data-provenance.md` が全数値の出所と再計算スクリプト、`checksheet_live.xlsx` がカメラレディのチェックシート。

スクリプトは絶対パス参照なので、これらを移動する際は参照側 (`km2/experiments/**/*.sh`、`.claude/memory/`、`~/.claude/projects/.../memory/`、`km2/approach/`、`FOSE2026-TeX-UTF8/*.md`) も一緒に書き換えること。

### トポロジのバリアント (実験の本題)

`km2/variants/` の各サブディレクトリは、それぞれ異なるサービス配置の実験です。テストしているパターンは、**複数のサービスを 1 つの Pod 内にサイドカーとして同居させる** (`localhost` 経由で通信) 方式と、通常の 1 Pod 1 サービス構成 (クラスタの `Service` DNS 名経由で通信) 方式の比較です。バリアントの `checkoutservice.yaml`/結合マニフェストを `km2/normal/checkoutservice.yaml` (分離ベースライン) と比較すると、何が変わったか分かります。

- `outmail/` — emailservice を checkout の Pod 内へサイドカーとして移動。checkout は `emailservice:5000` ではなく `EMAIL_SERVICE_ADDR=localhost:8080` で到達する。
- `paymail/`、`outpaymail/` — payment や email を checkout と同居させる。
- `outpy/`、`productshipping/` — さらなる同居の組み合わせ。
- `km2/locust/` — アドホックな locust マニフェスト/テスト。

バリアントを編集する際、`*_SERVICE_ADDR` 環境変数が localhost 経由かクラスタ内ルーティングかを選択するもので、これが実験で操作するレバーです。

### 負荷生成ツールのつまみ

**現役の標準は k6 (開ループ)** です。locust (閉ループ) は結果が双安定になるため、2026 夏以降は k6 に移行しました。両方残っていますが、新しい実験は k6 を使います。

- **k6**: `km2/experiments/k6/checkout.js` がシナリオ、`k6-job.yaml` が Job。つまみは `RATE` (周/s の目標)、`BROWSE_RATE` (閲覧型の負荷。混合ワークロード用)、`WARMUP`/`MEASURE` (ウォームアップと計測窓の秒数)、`PRE_VUS`/`MAX_VUS`。**開ループなので、目標レートを出せなければ取りこぼし (dropped) として現れます** — ここが容量の崖を測れる理由。
- **locust (旧)**: `src/loadgenerator2/locustfile.py` がフロー (index → addToCart → checkout) を定義。Job は `km2/**/loadgenerator.yaml` の環境変数 `USERS`、`RATE` (spawn rate)、`RUN_TIME`、`FRONTEND_ADDR` で調整。`wait_time` は `constant_throughput(1)` なので各ユーザーが約 1 リクエスト/秒を目標にする閉ループです。
- **1 周** = k6 の checkout シナリオ 1 回 (locust では 3 HTTP リクエスト)。負荷は「周/s」で表します。

### 枠 (requests/limits) を触るときの注意

マニフェストの `requests` は 2026-08 に**実測ベースで適正化済み** ( 枠 = (アイドル + 1 周あたり CPU × 100) / 0.7 ) です。HPA の判定も台数もこの値を基準に動くため、安易に変えると過去の結果と比較できなくなります。変えるなら両方のマニフェスト (`km2/`、`kubernetes-manifests/`) を揃え、何を変えたか記録すること。**`limits` を `requests` と一緒に縮めるとスロットリングでレイテンシが桁で悪化します** (実測済み) — 台数の実験で縮めるのは `requests` だけ。

## よく使うコマンド

```sh
# --- 実験の実行 (ローカル MicroK8s、namespace は exp) ---
# 主力実験はドライバ経由。アーム切替・負荷・計測・CSV 書き出しまで全部やる (km2/experiments/summer2026/ で実行)
ARMS="normal frontcatalog frontreco frontcart" RATES="150 200 250" CYCLES=3 \
  bash bundle-vs-loss2.sh

# --- 手で立てる場合 (Istio は入れない。namespace は default ではなく exp) ---
kubectl apply -n exp -f km2/normal/                        # 分離ベースライン (ディレクトリ単位で apply)
kubectl apply -n exp -f km2/variants/outmail/              # 代わりに特定のバリアントをデプロイ

kubectl get pods -n exp
kubectl port-forward -n exp deployment/frontend 8080:8080  # :8080 でストアを閲覧
kubectl logs -n exp --tail=50 job/k6load                   # 負荷実行を確認

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
