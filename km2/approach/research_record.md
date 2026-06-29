# 研究記録 (research_record)

> 実験の「生の記録」。手順・実際に打ったコマンド・つまずき・数値・解釈をそのまま残す。
> 計画の意図は `research_plan.md`、先行研究は `related_work.md` を参照。
> 新しい記録ほど上に追記する。

---

## 2026-06-30 ── softirq CPU/req：co-location で通信スタックCPUが約半減（−52%、3サイクル再現）

### 転機：主指標を「node全体CPU」→「softirq モードCPU」へ
前回 CPU/req に転換したが、**node 全体CPUは背景ノイズに支配されて使えない**ことが判明した。
- ノード `mizuki-nuc12wshi7` は単一ノードのワークステーション。無負荷の node非idle CPU を3回測ると
  **0.41 / 0.71 / 0.72 cores とドリフト**（range 0.3）。分解すると非idleの**約75%が非Kubernetes背景**
  （`kubelite`=MicroK8s制御系・**VS Code**・Claude/kubectl/python の計測ツール・dqlite/calico）。
- 鍵＝**CPU時間はモード別に別カウンタ**（`/proc/stat`）。背景ノイズは全部 **user** モード（計算）。
  **通信のkernel処理（NAT/conntrack/bridge）は softirq モード**で、しかも**どのコンテナcgroupにも
  計上されない**（送信スレッドは手を離し、ksoftirqd 等が非同期処理→ノード単位 softirq カウンタへ）。
- 実測（モード分解, 無負荷）：**softirq 0.0053⇄0.0056（不動）** に対し user 0.27⇄0.49（大揺れ）。
  負荷をかけると softirq 0.005→0.255（50倍）。→ **softirq を見れば user ノイズと物理的に隔離**できる。
  これは `mpstat -P ALL` の %soft 列を見るのと同じ標準手法（MeshInsight arXiv:2207.00592 はさらに
  perf/flamegraph で関数分解）。
- 補足：コンテナ別CPU(cgroup)は安定だが**通信コストが入っていない**（softirqはcgroup外）→
  app CPU は経路差を映さず「対照群（公平性チェック）」にしかならない。主指標にはできない。

### 方法
`km2/all/compare.sh` に softirq/system 取得を配線（CSV 22列）。各アームで
ウォームアップ→**温まったアイドル基線（softirq含む）**→本計測。
`softirq_mc_per_req =（負荷時 softirq − 無負荷 softirq）/ rps × 1000`。
`CYCLES=3 WARMUP=3m MEASURE=5m`、結果 `km2/all/results-cpu.csv`。

### 結果（3サイクル, ~208rps, exp ns, Istio無し）
| 指標 | normal（分離） | mega（同居） | 差 |
|---|---|---|---|
| **softirq/req【主】** | **1.181 ± 0.023** | **0.564 ± 0.017** | **−52.2%** |
| system/req | 3.197 ± 0.058 | 2.996 ± 0.165 | −6.3% |
| app/req【対照】 | 13.256 ± 0.268 | 12.465 ± 0.539 | −6.0% |
| node全体/req | 15.862 ± 0.365 | 14.385 ± 0.940 | −9.3% |

- **softirq の差 0.617 mc/req は、アーム内のサイクル間ばらつき(sd≈0.020)の 31 倍**＝圧倒的有意・3サイクル一貫。
- 指標が超安定（node全体 ±0.4〜0.9 と対照的）＝softirq が user ノイズから隔離されている証拠。
- **対照群 app/req は −6%** にとどまる（softirqの−52%と桁違いに小）＝差は通信由来、比較は公平。
- 絶対量：208rps で softirq は normal 0.246→mega 0.117 cores ＝ **約0.13コア節約（半減）**。

### 解釈と限界
- 結論：**Pod 同居で「リクエストあたり通信スタックCPU（softirq）が約半減」**。研究が目指した
  資源効率メリットを、初めてノイズに埋もれずクリーンに実証。エコー法の p99 −16%（別手法・独立）とも整合。
- 限界（論文に明記）：①単一ノード・Istio無し・低負荷ゆえ**絶対量は小**（0.13コア）。主張は「半減」で
  総CPU大幅減ではない。②softirq はノード単位ゆえ**アプリ分を直接は分離できない**→「経路だけ変えた
  A/B の差＋無負荷基線差引」で取り出す準実験。③app 対照が完全フラットでなく −6%（syscall/serialize の
  一部が同居で軽くなる、system −6% と整合）。

### 次の一手
1. **ヌル対照**（normal vs normal で softirq差≈0）でノイズ床を正式確認。
2. `/proc/softirqs` の NET_RX/NET_TX 件数で「ネットワーク種別の softirq」と裏取り。
3. **Istio 注入**で Envoy 税を増幅（差の上限）。
4. **同居数スイープ**（outmail→paymail→…→all）で横軸＝束数 vs softirq/req。

---

## 2026-06-29 ── 全部入りPod(megapod) vs 分離：1リクエスト遅延に正味差なし（低負荷）

### 何をしたか
Online Boutique の全11コンテナを1 Pod に同居させた **megapod**（`km2/all/all.yaml`）と、通常の分離構成
（1 Pod 1 サービス、両アームとも **Istio 無し**に揃えた純パッキング比較）で、**1リクエストの
エンドツーエンド応答時間**を比較。計測は locust のクライアント側応答時間（`--csv` の Aggregated 行）。
自動化は `km2/all/compare.sh`（normal↔mega を ウォームアップ→本計測 で交互、env で `CYCLES/WARMUP/MEASURE`)。
- megapod のポート衝突回避: email 8080→8081 / reco 8080→8082 / shipping 50051→50052、全 `*_SERVICE_ADDR` を localhost 化。
- per-コンテナ requests は分離と同一（=詰め方だけ変えた公平比較）。実験 ns=`exp`、単一ノード。

### 結果（3サイクル × 各 4分ウォームアップ+7分本計測、~215rps）
| arm | p50 | p90 | p99 | avg | rps |
|---|---|---|---|---|---|
| normal | 51.0 | 150.0 | 666.7 | 80.7 | 215.9 |
| mega | 53.0 | 146.7 | 803.3 | 81.0 | 215.3 |

- **最安定指標 avg はほぼ同一（80.7 vs 81.0）**。p50 も誤差内。
- **p99 はラン間ノイズに埋没**：normal 単独で 420→780→800 と振れ、mega(730–860)と範囲が重なる。
  支配的ばらつきは arm 間でなく**サイクル間**＝本物の効果ではなくノイズの兆候。
- → 当初 cycle1 単独で見えた「mega 速い」は撤回。**低負荷・単一ノードでは µs〜数百µs の通信差が
  ms 規模の処理＋スケジューリング揺らぎに埋もれる**（`related_work.md` の物理と整合）。
- per-endpoint では深いツリーの `/cart/checkout` の裾が最も動くが noisy。

### つまずき（すべて対処済み・`compare.sh`/`loadgen-csv.yaml` に反映）
- frontend は `SHOPPING_ASSISTANT_SERVICE_ADDR` 未設定で panic（機能無効でも値が必須）。
- loadgen の CSV は **終了直後の `kubectl logs` が空読みになる** → keep-alive `sleep` で Pod を生かし、
  生存中にポーリングして読む。
- 前段ウォームアップの**残存 Pod を掴むと warmup 値を誤記録** → 残存 Pod 消滅待ち＋最新 Pod 採用で解決。
- `python3 - <<'PY'` はヒアドキュメントが stdin を占有 → ログは pipe でなくファイル渡し。

### 次の一手
低負荷では遅延に差が出ない → 主指標を **CPU/req（資源効率）** へ転換中（`compare.sh` に Prometheus 取得を統合、
在クラスタ curl Pod 経由＝port-forward はこの環境で落ちるため）。あわせて **①負荷を飽和近くまで上げる**、
**②Istio 注入で Envoy 税を増幅** が必要。CPU/req 本走は未実施（統合のスモーク中に中断）。

---

## 2026-06-24 〜 06-25 ── 通信時間の確認（エコー法）：差は実在した

### 目的
「2サービスを 1 Pod に同居（localhost 通信）させると、別々の Pod（ClusterIP 通信）より
通信の往復時間が短くなる」——この**最も基本的な差が、そもそも実機で測れるのか**を確認する。

### 設計の要点（なぜこの形か）
- **処理ゼロの相手で測る**: 以前 checkout→email で失敗したのは、測定時間に email の重い処理
  （Jinja2 レンダリング, ms 級）が混じり、見たい通信差（数十µs）が埋もれたため。
  → サーバ処理がほぼゼロの **gRPC ping** を相手にして「測定時間 ≒ 通信時間」にする。
- **経路だけを変える A/B**: サーバ・ノード・負荷・ペイロードを同一にし、**宛先アドレスだけ**を
  `localhost:8079`（集約）と `echo-server:8079`（分離=ClusterIP）で切り替える。

### 使ったツール（最終形）
- サーバ・ドライバとも **`fortio/fortio`**（Istio プロジェクトの負荷ツール）。
  - サーバ: `fortio server -grpc-port 8079`（gRPC PingServer。ping は最小ペイロードを返すだけ）。
  - ドライバ: `fortio load -grpc -ping -qps 200 -c 1 -n 30000 <addr>:8079`（分位点を直接出力）。

> **つまずき（記録）**: 当初 `moul/grpcbin`(サーバ) + `ghz`(ドライバ) を予定。grpcbin は問題なく pull
> できたが、**ghz は公式の配布イメージが無く**（README はソースビルドのみ）、`bojand/ghz:latest` は
> Docker Hub 上でマニフェストが壊れていて（`unexpected media type text/html ... not found`）pull 不可。
> ホストに docker も無くビルド不可。→ **サーバもドライバも単一の `fortio/fortio` に統一**して解決。

### 環境
- 単一ノード `mizuki-nuc12wshi7`、MicroK8s、k8s **v1.32**（ネイティブサイドカー利用可）。
- namespace `exp`、**Istio 注入 OFF**（純粋な経路差を見るため）。
- 集約アームの Pod は、サーバを `initContainer + restartPolicy: Always`（ネイティブサイドカー）で先に起動し、
  `startupProbe(tcpSocket 8079)` で listen を待ってからドライバ本体を開始 → ドライバ終了で Pod は Completed。

### 実際に打ったコマンド（要点）
```sh
# サーバ（ClusterIP アーム用）を立てて Ready 待ち
microk8s kubectl apply -f km2/echo/echo-server.yaml
microk8s kubectl rollout status deploy/echo-server -n exp

# 分離アーム（ClusterIP 経由）
microk8s kubectl apply -f km2/echo/echo-clusterip.yaml
microk8s kubectl logs echo-clusterip -n exp -c fortio   # 末尾に分位点

# 集約アーム（localhost 経由）
microk8s kubectl apply -f km2/echo/echo-localhost.yaml
microk8s kubectl logs echo-localhost -n exp -c fortio

# 反復は pod を delete→apply→Succeeded 待ち→ログ抽出 を3回（results.csv に集約）
```
パラメータ: `-n 30000`（高精度な平均）、`-c 1`（キュー遅延排除）、`-qps 200`（低負荷固定）。

### 生結果（各3回。単位 ms）`km2/echo/results.csv`
| run | arm | avg | p50 | p90 | p99 |
|---|---|---|---|---|---|
| 1 | clusterip | 0.583 | 0.565 | 0.950 | 1.80 |
| 1 | localhost | 0.518 | 0.537 | 0.924 | 1.54 |
| 2 | clusterip | 0.586 | 0.565 | 0.951 | 1.81 |
| 2 | localhost | 0.608 | 0.544 | 0.928 | 1.62 |
| 3 | clusterip | 0.627 | 0.554 | 0.955 | 1.83 |
| 3 | localhost | 0.530 | 0.543 | 0.921 | 1.40 |

### 集計（3回平均）と頑健性
| 指標 | ClusterIP | localhost | 差 | 差% | localhost が低い回数 |
|---|---|---|---|---|---|
| avg | 0.599 | 0.552 | −0.047 | −7.8% | **2 / 3** |
| p50 | 0.561 | 0.541 | −0.020 | −3.6% | **3 / 3** |
| p90 | 0.952 | 0.924 | −0.028 | −2.9% | **3 / 3** |
| p99 | 1.812 | 1.521 | −0.291 | **−16.1%** | **3 / 3** |

### 解釈
- **H1 は支持された**: 処理ゼロのエコー往復で、localhost 経路は ClusterIP 経路より速い。
  特に **p50/p90/p99 は3回とも例外なく localhost が低い**。
- **裾（p99）が最も大きく約16%減**。これは物理と整合：loopback は veth+bridge+conntrack/iptables を
  通らず、1パケットあたりのカーネル処理（softirq・接続追跡）が軽い。混雑が出やすい裾ほど差が開く。
- **平均（avg）は信頼度が低い**: run2 で localhost の avg だけ逆転（0.608 > 0.586）。原因は
  p99.9 より外のまれな遅延スパイク（スケジューラ揺らぎ等）が平均を押し上げたため。
  → **見出し指標は平均ではなく中央値・分位点（特に p99）を使うべき**。
- 差の絶対値は小さい（数十〜数百µs）。これは低負荷・単一ノードでは当然で、先行研究でも
  bridge→loopback の差は overlay 有無の差より小さい（`related_work.md`）。**「差はあるが小さい」**が正確な結論。

### 既知の限界 / 注意
- 各 run 30000 サンプルで個々の平均は高精度だが、**run 間のばらつき**（背景負荷・スケジューリング）が
  平均を揺らす。分位点は頑健。
- 集約アームはサーバとドライバが同一 Pod で CPU を共有するが、qps200 の低負荷では競合は無視できる。
- Istio 未注入での値。Envoy を入れると ClusterIP 側は両側 Envoy を通るため差は桁で広がる見込み（別実験）。

### 次の一手（優先順）
1. **負荷スイープ**: qps を上げ飽和に近づけ、ClusterIP 側の softirq/conntrack CPU が効いて
   レイテンシ差が拡大するかを見る（サブ指標＝飽和スループット）。
2. **ペイロード増**: メッセージサイズを上げ、loopback と bridge のコピーコスト差を拡大。
3. **CPU/req（案②）への接続**: 経路差は CPU にも出る。「通信に費やす kernel CPU/req」を測る。
4. **Istio 注入版**の比較（差の上限を見る）。

### 後片付け
- `echo-server`(Deployment+Service)・`echo-clusterip`・`echo-localhost` は計測後に削除。
- マニフェストは `km2/echo/` に保存（再実行可能）。結果は `km2/echo/results.csv`。
