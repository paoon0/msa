---
name: grpc-pinning-imbalance
description: 【2026-10-06 実測で確認】分離構成で backend を複数台にしても gRPC 接続固定で負荷が偏る(4台中1台がほぼ0m、最大Podは平均の約2倍)。§3.1 のスループット比較と HPA 実験全般の交絡
metadata:
  node_type: memory
  type: project
  originSessionId: f19a71cf-0131-4423-8285-543cfa375857
  modified: 2026-10-06T04:20:17.277Z
---

**事実 (2026-10-06 実測, `km2/experiments/summer2026/smoke/lbcheck.log`, 集計 `km2/experiments/rightsizing/pod_balance.py`)**: §3.1 と同条件 (分離・4台固定・requests 150m 一律・limits 据置) で buy200/300 を各1点。Pod ごとの CPU の「最大 ÷ 平均」は frontend 1.10 (k6 が多数接続を張るので均等) に対し、backend は全部 1.8〜3.3。ほぼ全サービスで4台中1台が 0〜7m (仕事なし)。例: buy200 の reco 550/288/249/1m (= 呼び出し元 frontend 4本の接続が 2:1:1:0 に割れた形)。

**仕組み**: frontend/checkout (Go, `src/frontend/main.go:228`, `src/checkoutservice/main.go:234`) と reco (Python, `recommendation_server.py:132`) の gRPC クライアントは負荷分散の設定なし = pick_first、宛先は ClusterIP Service → 呼び出し元 Pod 1台につき接続1本、その呼び出しは全部1つの Pod へ。

**Why (影響)**:
- §3.1「同居 ≈440 vs 分離 359.6 周/s」に交絡。front3 は catalog/reco が frontend と同じ Pod なので構成上均等。分離の頭打ちは偏りでも説明できる可能性: email の最も忙しい Pod は 151m(200)→255m(300) で、上限 300m に約 340 周/s で達する計算 (仮説、未検証)。memory [[fixed-replica-k6]] の「CPU を余らせたまま詰まる」とも整合。
- HPA で backend を増やしても、既存の接続は古い Pod のまま → 新 Pod に仕事が来にくい。HPA の判断は Pod 平均 (= 合計 ÷ 台数) なので台数の決まり方 (粒度損の計算) は変わらないが、容量・遅延の効果は変わる。
- softirq/周 (合計で測る) は影響を受けない。

**How to apply:** 台数を増やした実験の容量・スループット・遅延の主張は、この偏りを前提に読み直す。対処の選択肢 (headless Service + round_robin / サーバ側 MaxConnectionAge / Istio / 限界として明記) はユーザ判断待ち。関連 [[fixed-replica-k6]] [[rightsizing-formula-accuracy]] [[fose2026-live-paper]]

**★2026-10-06 アヌビス(査読役)判定 (引用行は自分でも確認済み):**
- 偏りは「4本の接続を4台にランダムに配る」形で、1台が空く確率 90.6% = 毎回ほぼ必ず起きる。どの Pod が空くかはデプロイごとに変わる → サイクル間ばらつきの源 (§3.1 で分離だけ SD 大と符合、推測)。空き Pod は後発 Pod ではない (Ready 順と無関係)。
- **Istio を主構成にするのは不可**: (1) HPA 判断は ContainerResource で istio-proxy 除外済み (bundle-vs-loss2.sh:201-202) なので混入はしないが、予約枠集計 sample_hpa.py:57 も除外 → サイドカー requests 100m×Pod数が載らない。載せると分離40本4.0コア vs mega 0.4コアで同居の得に最大3.6コア上乗せ。(2) Pod 内 localhost は Envoy を素通り → 分離だけ Envoy 2回+mTLS で非対称拡大。(3) 既存結果と比較不能。ドライバ 225行で inject=false を強制上書きしている。ユーザ論拠「主指標は台数だから Istio で可」には「台数は合計 CPU で決まるので偏りにほぼ無関係。偏りが効くのは容量・遅延で、Istio はそこを最も交絡させる=直したい対象とずれる」。
- 表1 は無効にならない: 分離側の劣化点 8/40 (取りこぼし or p50>100ms) を除いても一定3組/反転3組の分類は不変 (件数は変わる)。provenance に感度分析を追記すべき。
- §3.1 容量 (+2割) は「既定 gRPC 設定 (クライアント LB なし) では」と条件付きでのみ。「分離は CPU を余らせ往復待ちで詰まる」因果主張は現状不可 (一部 Pod 飽和で説明可能)。
- 推奨: A (headless + round_robin、HPA 実験は MaxConnectionAge 併用)。条件: 全構成同一イメージ、softirq を基本帯で測り直し (DNAT 経由しなくなるので経路は厳密には不変でない)、4台固定で偏り ≤1.2 を採用条件に。Istio は「追加条件」として1帯だけなら可。

**2026-10-06 ユーザ「偏りは直しておきたい」→ 案A を実装 (未ビルド・未測定):** Go は src/frontend/grpclb.go・src/checkoutservice/grpclb.go (GRPC_LB_POLICY 未設定なら従来どおり、dnspoll リゾルバで GRPC_RESOLVE_EVERY 秒ごとに DNS 再解決=HPA 追加 Pod 対策、サーバ側改修は不要にした)、reco はチャネル定期作り直し。ドライバ bundle-vs-loss2.sh に GRPC_LB=1 (grpc_lb_patch.py が headless の双子 Service "<名>-hl" を作り *_SERVICE_ADDR を書き換え・イメージ差替え。email は Service 5000→コンテナ 8080 なので targetPort を使う)。この機械には docker も go も無い (go は scratchpad に一時導入してビルド確認のみ)。

**2026-10-07 案A 実測 (smoke/lbfix.log, lbcheck と同条件 GRPC_LB=1, 1回):** 偏りは全サービス 1.00〜1.11 に解消 (採用条件 ≤1.2 を満たす)、取りこぼし0・失敗0。**ただし全サービスの CPU 合計が +18% (buy200) / +9% (buy300) 増え、イメージを替えていない currency/payment/shipping/ad も +7〜30%**。p50 は 300 で 43→81ms に悪化、softirq/周 +14%/+3%。原因 (新イメージ差 / 接続数 4→16倍 / 負荷を散らすと1呼び出しあたり CPU が増える) は未分離 → 対照 GRPC_LB=2 (イメージだけ差替え、振り分けなし) を用意、未実行。reco-lb は setuptools 未固定で pkg_resources 欠落→起動失敗した (requirements.txt に setuptools<81)。
**2026-10-07 対照 (smoke/lbctl.log, GRPC_LB=2 = 新イメージ・振り分けなし, 1回):** CPU 合計は前比 +2.8% (200) / +1.9% (300) でほぼ前と同じ、偏りも残る (1.5〜2.9)。⇒ **CPU +9〜18% の原因はイメージではなく round_robin そのもの** (接続 4→16 本で HTTP/2 のまとめ書きが効かない / 散らすと低負荷側の効率が落ちる、のどちらかは未分離)。softirq/周 も振り分けありだけ +14% (200)。buy300 でノード CPU 約13.2/16 コア = ほぼ満杯で p50 81ms。含意: 偏った分離は CPU を少なめに見せていた。
**2026-10-07 ユーザ決定「振り分けはアリでいい」:** bundle-vs-loss2.sh の既定を GRPC_LB=1 に変更 (それ以前の実験の再現は GRPC_LB=0、EXPERIMENTS.md 冒頭と experiments/CLAUDE.md に明記)。呼び出し側イメージは同居コンテナ (front3 の reco、mega の frontend/checkout/reco) も含め全アームで -lb 版に揃える。未対応: rightsizing/measure-class-cpu.sh (独自デプロイ, c0 の2台点に振り分けが要る)、front3/mega での振り分け有無の比較 (未実行)。
**2026-10-07 front3/mega で振り分け有無 (smoke/lbarm0.log, lbarm1.log, 各1回):** ノードCPU/周の増加 = 分離 +15%/+10% (200/300)、**front3 も +17%/+15% (予想に反して分離並み)**、mega +4%/+0.4% (外向き gRPC がほぼ無いので当然)。front3 で増えたのは Pod 外から呼ばれる側 (currency/checkout/payment/shipping/cart/email +12〜28%) = 振り分けのコストは「受ける側が複数クライアントから受けるか」で決まり、front3 は内部化しない辺が多く残る。⇒ 分離比の同居の得: front3 node −7/−6% → **−5/−1%**、softirq −26/−23% → −24/−17% (**縮む**)、mega node −9/−2% → −18/−10%、softirq −49/−43% → −53/−45% (**広がる**)。1回ずつなので要反復。front3 の reco コンテナ (localhost 呼び出しのみ) も +11〜13% = イメージ差の可能性 (分離の対照では reco +6/−1%)。
