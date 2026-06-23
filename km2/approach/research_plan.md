# 研究計画 — Pod 集約による通信コスト削減の検証（案①：通信時間の確認フェーズ）

> 初学者向けに、専門用語にはそのつど補足を入れて書いています。
> 関連: `related_work.md`（先行研究）、`research_record.md`（実験の生記録）、`km2/echo/`（本実験のマニフェスト）。
>
> **方針の経緯**: 需要相関 ρ を軸にした「Pod 集約 vs 独立スケールのトレードオフ」（案B）は
> いったん **保留**し、内容は `research_plan_B_coloc_tradeoff.md` に保存してある。
> まず原点に戻り、**「2サービスを 1 Pod に同居させると通信が速くなる」という最も基本的な差が、
> そもそも実機で測れるのか** をきちんと確認するのが本計画（案①）。

---

## 0. ひとことで言うと

**同じノード上で、2つのコンテナを「別々の Pod（ClusterIP 経由で通信）」に置くか、
「1つの Pod（localhost 経由で通信）」に置くかで、通信の往復時間に差が出るかを実測する。**

---

## 1. 背景：なぜ「通信時間」で、なぜ以前は測れなかったのか

### 1.1 2つの通信経路

| 置き方 | 通信経路 | 通るもの |
|---|---|---|
| 分離（1 Pod 1 サービス） | ClusterIP（Service 名で通信） | アプリ → veth → ブリッジ → conntrack/iptables(kube-proxy) → veth → 相手 |
| 集約（2 サービスを 1 Pod） | localhost（ループバック） | アプリ → loopback(lo) → 相手 |

- **veth**: Pod ごとに作られる仮想 LAN ケーブルのようなもの。Pod の外と通信するたびに通る。
- **ブリッジ / conntrack / iptables**: ノード内で「どの Pod 宛か」を判定・追跡する仕組み。1パケットごとに少しずつ CPU を使う。
- **loopback**: 同じ Pod の中（＝同じネットワーク名前空間）だけで完結する通信。上記をすべて**通らない**ので、1パケットあたりの処理が軽い。

→ 理屈の上では **localhost の方が速い**はず。これを実機で確かめるのが目的。

### 1.2 以前なぜ失敗したか（重要な教訓）

最初は checkout → email の RPC 時間で測ろうとしたが、差が出なかった。原因は計測対象の選び方にあった：

```
測定時間 = 通信時間（見たいもの） + email の処理時間（Jinja2 レンダリング）
```

email の処理（CPU 200〜300m・GIL で直列）が**ミリ秒級**で支配的なのに対し、
見たい通信差は**数十マイクロ秒級**。大きくてブレる処理時間に、小さな通信差が埋もれて見えなかった。

> **教訓**: 通信差を見たいなら、**サーバ処理がほぼゼロの相手**で測り、
> 測定時間 ≒ 通信時間 にして通信差だけを切り出す必要がある。

---

## 2. 仮説

> **H1**: 処理ゼロのエコー往復において、localhost 経路は ClusterIP 経路より往復時間（特に平均と p99）が小さい。

---

## 3. 実験設計（エコー法）

### 3.1 部品（すべて既製イメージ、コード記述ゼロ）

- **エコーサーバ**: `fortio/fortio server`（Istio プロジェクトの負荷ツール）。
  gRPC の **PingServer** を 8079 で待ち受ける。ping は最小ペイロードを返すだけ＝**処理ほぼゼロ**。
- **計測ドライバ**: `fortio/fortio load -grpc -ping`。同じ ping を大量に投げ、
  往復時間の**分位点（p50/p90/p99）**を直接出力する。

> 当初 `moul/grpcbin` + `ghz` を予定したが、ghz は公式の配布イメージが無く（要ソースビルド）、
> `bojand/ghz:latest` も壊れていたため、**サーバもドライバも単一の `fortio/fortio`** に統一した。

### 3.2 2つのアーム（変えるのは「宛先アドレスだけ」）

公平に比べる肝は、**サーバ・ノード・負荷・ペイロードをすべて同一にし、経路だけを変える**こと。

- **集約アーム（localhost）** `km2/echo/echo-localhost.yaml`
  fortio server とドライバを**同じ Pod の2コンテナ**にし、`localhost:8079` を叩く。
  サーバはネイティブサイドカー（`initContainer` + `restartPolicy: Always`, k8s 1.29+）で先に起動させ、
  `startupProbe` で 8079 が listen してからドライバを開始する。
- **分離アーム（ClusterIP）** `km2/echo/echo-server.yaml` + `km2/echo/echo-clusterip.yaml`
  fortio server を**別 Pod + Service**で立て、ドライバは別 Pod から `echo-server:8079` を叩く。

### 3.3 計測パラメータ

| 項目 | 値 | 理由 |
|---|---|---|
| 総リクエスト数 `-n` | 30000 | 平均を高精度に推定（標準誤差を十分小さく） |
| 並列度 `-c` | 1 | キュー遅延を排除し、純粋な往復時間を測る |
| 送信レート `-qps` | 200 | **低負荷に固定**。CPU 競合で経路差が濁るのを防ぐ |
| 反復 | 各アーム **3 回** | 1回ではノイズと区別できないため再現性を確認 |

### 3.4 環境統制

- **単一ノード**（mizuki-nuc12wshi7）。両 Pod は自動的に同一ノードに乗る。
- **Istio 注入 OFF**（`exp` namespace にラベル無し）。Envoy が入ると ClusterIP 側も Envoy 経由になり、
  「純粋な経路差」が濁るため、まずは入れない。
- namespace は `exp`。

---

## 4. 初期結果（2026-06-24、各1回め）

30000 calls / 200qps / 並列1。**全分位点で localhost が速く、向きは理論どおり**＝**差は実在した**。

| 指標 | ClusterIP（分離） | localhost（集約） | 差 |
|---|---|---|---|
| avg | 0.583 ms | **0.518 ms** | −0.065 ms（**−11%**） |
| p50 | 0.565 ms | 0.537 ms | −0.028 ms（−5%） |
| p90 | 0.950 ms | 0.924 ms | −0.026 ms（−3%） |
| p99 | 1.80 ms | **1.54 ms** | −0.26 ms（**−14%**） |

> 3回反復の集計値・生ログ・解釈は `research_record.md` と `km2/echo/results.csv` を参照。

**読み取り**: 差は平均で約65µs（約11%）、p99 で約260µs（約14%）。
loopback が veth+bridge+conntrack の1パケットあたりオーバーヘッドを省くという物理と整合。
小さいが、分布全体で一貫して同じ向き。

---

## 5. 限界と次の一手

- **差は小さい**（低負荷・単一ノードでは当然。先行研究でも bridge→loopback の差は小さい, `related_work.md`）。
- 次に効くレバー（差を拡大して有意性を高める）:
  1. **負荷スイープ**: qps を上げ飽和に近づけると、ClusterIP 側の余分な softirq/conntrack CPU が効き、
     レイテンシ差が拡大するはず（サブ指標＝飽和スループット）。
  2. **ペイロード増**: メッセージを大きくすると、loopback と bridge のコピーコスト差が広がる。
  3. **Envoy 注入時の比較**: istio 注入下なら ClusterIP は両側 Envoy を通り、localhost（同一 Pod）は
     Envoy をバイパスする。差が桁で広がる見込み（ただし新規性は弱い, `related_work.md`）。
- **資源効率（CPU/req）への接続**: 通信時間と並行して、経路差は CPU にも出る。
  「通信に費やす kernel CPU/req」を測る案②へ自然につながる。

---

## 6. ファイル一覧

| ファイル | 役割 |
|---|---|
| `km2/echo/echo-server.yaml` | fortio エコーサーバ（Deployment + Service, ClusterIP アーム用） |
| `km2/echo/echo-clusterip.yaml` | 分離アームのドライバ Pod（ClusterIP 経由） |
| `km2/echo/echo-localhost.yaml` | 集約アームの Pod（サーバ同居 + localhost 経由） |
| `km2/echo/results.csv` | 反復計測の結果表 |
| `research_record.md` | 実験の詳細な生記録（手順・数値・つまずき・解釈） |
| `research_plan_B_coloc_tradeoff.md` | 保留中の案B（相関トレードオフ）の計画書 |
