# HPA比較実験 再現手順書（束ね vs 分離 / softirq/req と スループット）

2026-07-07 作成。**自分の手で再現するための詳細**。研究の問い・指標・トポロジ・手順・落とし穴を全部書く。

---

## 0. 一言でこの実験は何か

「直接通信するサービスを **1 Pod に束ねて localhost 通信**にすると、細分化（1 Pod 1 サービス）より
**通信に使うカーネル CPU（softirq）が減る**。HPA（オートスケーラ）を有効にした状態でも
その効果が残り、**ノードあたりのスループットが上がる**か」を実機で比較する。

比較する2アーム（同じ3サービス frontend/reco/catalog をスケール対象にする）:
- **front3（束ね）**: frontend+recommendation+productcatalog を **1 Pod に同居**し内部を localhost 化。HPAは束ねPodだけに付ける。
- **normal（分離）**: 上記3サービスを **別々の Pod**（従来構成）。HPAを3サービス個別に付ける。
- cart+redis と他サービス(checkout/currency/payment/shipping/email/ad)は **両アーム共通・固定1レプリカ**（スケールしない。特にredisはstatefulなので束ねると分裂する→束ねから外す）。

---

## 1. 環境の前提

- 単一ノード Kubernetes（MicroK8s）。ノード ~16 vCPU。
- namespace = `exp`。**Istio サイドカーは無し**（各Deploymentに `sidecar.istio.io/inject: "false"` を patch。exp名前空間はistio-injection未ラベルなので二重に無効）。
- 監視: kube-prometheus-stack（Prometheus + node-exporter + cadvisor）。Service名 `prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090`。
- HPA前提: metrics-server が稼働（`kubectl top node` が動くこと）。K8s 1.27+ なら ContainerResource も使える。
- 独自イメージ: checkoutservice = `mizuki0118/mygo:bunpupaymail`（計測入り）。他は upstream v0.10.3。
- **公平性**: 全サービスの resources.requests/limits を `km2/all/all.yaml` の値に統一（アーム間で同一）。

---

## 2. 指標: softirq/req（1リクエストあたりの通信カーネルCPU）

### なぜ softirq か
- パケット処理（IP/iptables/conntrack/bridge/veth 通過）のカーネル CPU は **softirq モード**に計上される（`/proc/stat`）。
- softirq は **どのコンテナの cgroup にも計上されない**（ksoftirqd/割り込み文脈）。だから
  背景ノイズ（VS Code等=userモード）と物理的に分離でき、かつ **HPAが読むcgroup CPUには映らない**。
- ClusterIP経路（veth+bridge+conntrack）→ localhost(loopback)経路 で softirq が減る。この差を測る。

### 定義（単位 = CPU-ミリ秒/リクエスト）
```
softirq/req = ( softirq_負荷時[cores] − softirq_アイドル基線[cores] ) / rps × 1000
```
- `softirq_cores` = `sum(rate(node_cpu_seconds_total{mode="softirq"}[窓]))` … 全CPU合計の softirq 使用率（cores=CPU秒/秒）。
- 基線を引く=負荷が生んだ分だけ取り出す（背景の常時softirqを除く）。softirq基線は ~0.005 cores で安定。
- rps で割る=秒を相殺し「1リクエストあたり」に正規化。`cores/(req/s)=CPU秒/req`, ×1000で CPU-ミリ秒/req。
- 対照指標: `app_cores`(=cgroup CPU合計, HPAが見る量), `node_cores`(=ノード非idle全体)。

### Prometheusクエリ（在クラスタ curl Pod 経由。port-forwardはこのbash環境でkillされるため）
```sh
# 読み取り専用ヘルパ Pod
kubectl run promq -n exp --image=curlimages/curl:latest --restart=Never --command -- sleep 86400
# クエリ（例: 負荷時 softirq を 3分窓で）
kubectl exec promq -n exp -- curl -s \
  "http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090/api/v1/query" \
  --data-urlencode 'query=sum(rate(node_cpu_seconds_total{mode="softirq"}[3m]))'
# app(cgroup)CPU:
#   sum(rate(container_cpu_usage_seconds_total{namespace="exp",container!="",container!="POD",pod!~"loadgenerator.*",pod!~"promq.*"}[3m]))
```
**注意**: `kubectl exec ... | python`(パイプ)は動くが `kubectl exec ... > file`(リダイレクト)はこの環境で空になる。パイプで受けること。高負荷時はexecがタイムアウトするのでリトライを入れる（取り逃したら `time=<unix>` で履歴クエリして後追い回収できる）。

---

## 3. トポロジ（マニフェスト）

- **normal（分離）**: `km2/frontend.yaml`, `km2/recommendationservice.yaml`, `km2/productcatalogservice.yaml`, `km2/cartservice.yaml`(cart+redis), `km2/checkoutservice.yaml` ほか各サービスを個別apply。
- **front3（束ね）**: `km2/frontrecocatalogcart/` ディレクトリ。
  - `frontrecocatalogcart.yaml` = frontend+recommendation+productcatalog を1 Podに同居（3コンテナ）。
    - frontend の env: `PRODUCT_CATALOG_SERVICE_ADDR=localhost:3550`, `RECOMMENDATION_SERVICE_ADDR=localhost:8090`。他はClusterIP。
    - reco は 8080→8090 に **remap**（frontendの8080と競合回避）。reco→catalogも `localhost:3550`（両方同居）。
    - `productcatalogservice` Service のセレクタを `app=frontend` に向ける（checkout等が ClusterIP で束ねPod内catalogに届くため）。reco の Service は不要（frontendしか呼ばない）。
    - **cart+redis は束ねに入れない**（`cartservice.yaml` を別ファイルで置き、cart→redis は `redis-cart:6379` の ClusterIP、redis は単一固定）。frontend→cart も `cartservice:7070`(ClusterIP)。
    - HPA同梱可（ただし比較スクリプトは削除して統一ポリシで付け直す）。
  - ポート競合注意: 同一Pod内で 8080/8090/3550 が重複しないこと（reco remap の理由）。

---

## 4. 1計測点あたりの流れ（測定プロトコル）

各 (サイクル, アーム, 負荷レベル) で以下を実施:
1. **デプロイ**: 既存全削除→対象トポロジをapply→全Deploymentに `inject:false` patch→rollout待ち。
   （毎回デプロイし直すことで **レプリカを1にリセット**。前サイクルのスケールアップ残りを持ち越さない）
2. **HPA作成**: スケール対象にだけ付ける。
   `kubectl autoscale deploy/<名> -n exp --cpu-percent=70 --min=1 --max=4`
   - front3: 対象= frontend（束ねPod）のみ。
   - normal: 対象= frontend, recommendationservice, productcatalogservice（同じ3サービス）。
3. **ウォームアップ**（捨てる, 3分）: loadgen Job を負荷レベルで起動→HPAがscale-upして落ち着くのを待つ。
4. **アイドル基線**（ドレイン30秒 + 窓2分）: 負荷を止め、温まったアイドルで softirq/app/node の基線を取得。
5. **本計測**（3分）: 再度負荷→3分窓で softirq/app/node の rate を取得。同時に **スケール対象の総レプリカ数**を記録。
6. **記録**: locust の Aggregated 行(rps,p50/90/99,fails) + CPU から softirq/req を計算し CSV へ1行追記。

負荷は locust（headless, `--csv`）: フロー index/product/cart/checkout。負荷つまみ=`USERS`,`RATE`(spawn),`RUN_TIME`。

---

## 5. HPA比較の具体パラメータ（本走の実値）

| 項目 | 値 |
|---|---|
| 負荷レベル SWEEP_USERS | `240 480`（効果が出る高負荷2点。80は両arm同等なので省略） |
| RATE（spawn） | 40（即ramp。HPAに持続負荷を見せる） |
| サイクル数 CYCLES | 3（平均±sdを出す） |
| ウォームアップ / 本計測 | 3分 / 3分 |
| 基線 | ドレイン30秒 + 窓2分 |
| HPA | CPU目標70% / min1 / max4 |
| スケール対象 | front3=frontend / normal=frontend,reco,catalog |
| namespace | exp、Istio無し |

RATE=40 で users を上げると、CPUが70%を超えたサービス（frontend等）がスケールする。

---

## 6. 実行コマンド（再現手順）

```sh
cd ~/ダウンロード/msa            # リポジトリ直下
# 事前確認
kubectl top node                 # metrics-server が動くこと
kubectl get ns exp || kubectl create ns exp

# 本走（3サイクル、front3→normal を users240/480 で）
nohup bash km2/all/hpa-compare-softirq.sh >/dev/null 2>&1 &

# 進捗
tail -f km2/all/hpacompare.log            # 節目ログ
wc -l km2/all/results-hpacompare.csv      # 13行(header+12)で完了

# env で条件変更可（例: 1サイクルだけ、全3レベル）
CYCLES=1 SWEEP_USERS="80 240 480" bash km2/all/hpa-compare-softirq.sh
```
スクリプト本体 = `km2/all/hpa-compare-softirq.sh`。出力 = `km2/all/results-hpacompare.csv`。

---

## 7. データの読み方（集計）

CSV列: `cycle,arm,users,...,rps,softirq_mc_per_req,...,scale_replicas,scale_detail`。
3サイクル平均±sd を (arm,users) ごとに取り、束ね vs 分離 を比較:
```python
import csv,statistics as st
r=list(csv.DictReader(open('km2/all/results-hpacompare.csv')))
for u in ['240','480']:
  for arm in ['front3','normal']:
    g=[x for x in r if x['arm']==arm and x['users']==u]
    sq=[float(x['softirq_mc_per_req']) for x in g]; rp=[float(x['rps']) for x in g]
    print(arm,u,'softirq/req=%.3f±%.3f rps=%.0f±%.0f'%(st.mean(sq),st.pstdev(sq),st.mean(rp),st.pstdev(rp)))
```
判定: 差が sd の何倍か（4倍以上でほぼ有意）。今回の結果=softirq/req 束ね−36〜39%(堅い), スループット束ね平均+12〜29%(HPAスケール依存でばらつく)。

---

## 8. 落とし穴（重要・再現時に必ず踏む）

1. **frontend の env 必須値**: `SHOPPING_ASSISTANT_SERVICE_ADDR` 未設定だと frontend が panic（機能無効でも値が要る）。
2. **loadgen ログ回収レース**: Job終了直後の `kubectl logs` は空。CSVマーカー(`@@@CSV_BEGIN/END@@@`)を吐いて `sleep` で生かし、生存中にポーリングして読む。
3. **前段の残存loadgen Pod**を掴むと warmup 値を誤記録 → 残存Pod消滅待ち + `--sort-by=creationTimestamp` の最新Pod採用。
4. **port-forward はこの bash 環境で kill される** → Prometheus は在クラスタ curl Pod(`promq`)+`kubectl exec`。
5. **kubectl exec のリダイレクト(`>file`)は空**になる → パイプで受ける。高負荷でexecタイムアウト→リトライ、最悪 `time=` 履歴クエリで後追い。
6. **HPAのscale-down は5分停留**（scale-upは速い）→ サイクル間は低→高で回すか、毎回デプロイし直して1にリセット。
7. **redisを束ねるとスケール時に分裂**（cart状態が Pod 間で不整合）→ redis(と cart)は束ねから外す。
8. **束ねのHPA失速**: 既定HPA(`Resource cpu`)は Pod平均CPU=全コンテナ合計/requests合計。熱い frontend が冷たい reco/catalog に薄められ 70%に届かず**スケールしないことがある**（3サイクル中1回発生）。→ `ContainerResource` メトリックで frontend コンテナ単体を見れば改善する見込み（未検証）。
9. **pip/matplotlib 無し環境**: 図は手書きSVG生成 or `-o json`+python。

---

## 9. 関連ファイル
- 計測スクリプト: `km2/all/hpa-compare-softirq.sh`（softirqスイープ版=`hpa-sweep-softirq.sh`, 単発softirq=各 `km2/all/*-softirq.sh`）
- トポロジ: `km2/frontrecocatalogcart/`（束ね）, `km2/*.yaml`（分離）, `km2/all/all.yaml`（mega=全部入り, resources基準）
- 負荷: `km2/all/loadgen-csv.yaml`
- 結果: `km2/all/results-hpacompare.csv`, ログ `km2/all/hpacompare.log`
- 通信量実測: `km2/all/netmeasure.sh`（各サービスの packets/bytes）
- HPA盲点図: `km2/all/hpa-blindspot.svg`
