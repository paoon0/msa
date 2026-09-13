# FOSE2026 ライブ論文 下書き

- **投稿区分**: ライブ論文(2ページ以内 / ショートプレゼン5分 / 査読あり)
- **投稿先**: EasyChair(PDF)。テンプレートは FOSE2026 配布のもの(pLaTeX)
- **締切**: 2026-09-14(月) 17:00 / 採否 9-18 / カメラレディ 9-25
- **CFP**: https://fose.jssst.or.jp/fose2026/cfp.html
- 作成 2026-09-09 / **最終更新 2026-09-13**
- ★**正は TeX 原稿 `FOSE2026-TeX-UTF8/fose2026.tex`。**この md は現状のスナップショット

---

## 題目

**KubernetesのHPA環境下におけるコンテナ集約の適用**

英題: Container Colocation of Microservices under Autoscaling

---

## 概要

複数サービスを1つの Pod に同居させる**部分集約**は通信コストを下げるが、Kubernetes では HPA が Deployment 単位で台数を決めるため、集約すると**スケールの粒度が粗くなり**予約資源が増える。本稿では Online Boutique を用いた実機実験により、集約がスループットと通信コストを改善する一方、この損失の大きさが**通信量**と**ワークロード成分**という独立な2軸で決まることを示す。

---

## 1. はじめに

マイクロサービスを細分化すると、サービス間の呼び出しがネットワークスタックを経由するため、通信処理のオーバヘッドが生じる。直接通信するサービスを1つの Pod に同居させ、通信を `localhost` 経由にする**部分集約**はこれを削減する。Wickramanayaka ら[1]は Docker Swarm 環境で、通信量の多いコンテナの適正配置・統合を行い通信量が最大58.5%減少することを示した。

この効果を、実運用のデファクトスタンダードである Kubernetes に取り入れたい。しかし中核機能である HPA は Deployment 単位で台数を決めるため、集約すると**スケールの粒度が粗くなる**という問題が生じる。本稿ではこの環境での効果を確認したうえで、相手選びに必要な判断軸を示す。

> ★2026-09-12 に書き換え。旧版は「先行研究は Kubernetes のオートスケール環境を対象としていない」という**欠落の指摘**だったが、(a) Docker Swarm にも第三者製オートスケーラはあるので Kubernetes を使う理由にならない、(b)「まだ誰もやっていない」は動機として弱い、という理由でユーザ判断により**「デファクトスタンダードに取り入れたい → しかし HPA と噛み合わない」**という筋に変更した。

---

## 2. 部分集約とオートスケーラの干渉

HPA は Deployment 単位で台数を決めるため、同居したコンテナは**同じ台数でしか複製できず**、その台数は各コンテナが必要とする台数の最大値になる。サービス s の枠 (requests) を r(s)、単独で必要な台数を n(s)、同居した Pod の台数を N = max n(s) とすると、余分に確保される資源 Δ は

```
    Δ = Σ ( N − n(s) ) × r(s)        … 式(1)
        s
```

となる。**損は「引きずられた側の枠」に比例**し、必要台数が揃えば Δ = 0 である。以降この Δ を**粒度損**と呼ぶ。

---

## 3. 実験環境

対象は Online Boutique[2] (11サービス、gRPC 通信) である。MicroK8s (単一ノード、16コア) 上にデプロイし、k6 を用いて負荷を与えた。

負荷は2種類の利用者を模した。**buy** は閲覧・カート追加・購入を、**view** は閲覧のみを1周とする。**view は checkout・payment・shipping・email に一切到達しない**。以降、1秒あたり x 周のレートで与える負荷を buy(x)・view(x) と表す。

**表1 2種類の利用者が到達するサービス**

| 利用者 | 到達するサービス |
|---|---|
| buy | 全10サービス |
| view | frontend, productcatalog, cart, currency, recommendation, ad |

評価指標は、粒度損として**予約枠** (稼働 Pod の requests 合計)、通信コストとして **softirq の CPU 時間**を用いた。

### 3.1 予備実験: Kubernetes 環境での効果

分離 (1 Pod 1 サービス)、frontend・recommendation・productcatalog を同居させた **front3**、全サービスを同居させた **mega** の3構成を比較した。台数は4で固定して HPA を切り、全コンテナの枠を150mに揃えたので、予約資源はどの構成も 6.3 コアで一致する (3回反復、buy のみ)。

buy(150)〜buy(300) ではいずれも目標レートを達成し、取りこぼしと失敗は0であった。その条件で1周あたりの softirq は分離に対し front3 で 17〜23%、mega で 43〜51% 少なく、**同居させるほど通信コストが下がる**。応答時間は buy(300) で分離だけが不安定になり (p50 が 23〜79 ms、同居は 16〜21 ms)、過負荷 (buy(500)) では達成レートが分離 348 周/秒 に対し front3 425、mega 435 と、**同じ予約資源でより多くを処理**できた。

> ★2026-09-13 に差し替え。旧版は7月の locust(**閉ループ**)で「rps +10.2%」としていたが、**閉ループのスループットは応答時間の言い換え**にすぎない(normal の p50 340ms 対 集約 37ms → 同じユーザ数でも周回数が減るだけ)。新データ(k6 開ループ・台数固定・予約一致)に差し替えたことで、§4 と §5 の測定系不一致も解消した。

---

## 4. 本実験

枠 (requests) はマニフェストの既定値ではなく、実測から適正化した値を用いる。各サービスを1台に固定し HPA を切った状態で負荷を6段階 (10〜150周/秒) 与え、CPU 使用量を負荷の1次式として最小二乗法で近似し、

```
    r = ( c0 + c1 × k ) / 0.7,   k = 100      … 式(2)
```

とした。c0 はアイドル時の CPU 使用量、c1 は1リクエストあたりの CPU 時間、k は基準負荷 [周/秒] である。これにより、理想的には全サービスが同じ負荷で目標利用率に到達し、必要台数が一致する。その上で、buy(100) を一定に保ちつつ view を4段階(0・100・200・250周/秒)で変える実験を行った。

### 4.1 ワークロード成分が異なると損は消せない

buy のみを与えた場合にも粒度損は生じたが、これは email の利用率が増設ラインをわずかに超えた (83%) ためで、**枠が7%不足していただけ**であり、buy(150) では両者とも2台となって消える(表2の上2行)。すなわち**枠の測定精度に起因する損は除去できる**。

これに対し view(0) を view(300) にすると、**frontend の需要は2.5倍**になるのに対し **email は1.2倍**にしかならない(表2の1行目と3行目)。

**表2 条件による粒度損の変化 (FE+email、いずれも3/3で一致)**

| buy [周/秒] | view [周/秒] | 必要台数 FE/email | 引きずられる側 | 粒度損 [mCPU] |
|---|---|---|---|---|
| 100 | 0 | **1** / **2** | FE (1077 m) | **+1077** |
| 150 | 0 | 2 / 2 | — | **0** |
| 100 | 300 | **3** / 2 | email (119 m) | **+119** |

**同じ組み合わせでありながら、引きずる側と引きずられる側が入れ替わり、損が9倍変化した**。損の比 1077 ÷ 119 = 9.05 は枠の比と一致し、式(1)が両方向で成立している。

枠は各サービスに1つしか与えられないのに対し、需要の比はワークロードの混合比によって変化するため、**2つの条件で同時に損をゼロにする枠は存在しない**。すなわちこの損は枠の調整では原理的に除去できない。

ただし成分が異なれば必ず損が出るわけではなく、必要台数が一致した際の粒度損はゼロであった。

> ★旧版では 5.1「枠の調整で消える損」/ 5.2「枠の調整では消えない損」の2節だったが、分量の都合で1節に統合。また「同時にゼロにする枠が存在しない」ことの不等式による導出(93/r ≤ 0.77 → r ≥ 121、113/(2r) > 0.77 → r < 73)はユーザ判断で削除した。

---

## 5. 考察

便益は通信量で決まり、枠を3倍変えても softirq の削減率は 16.4%・16.2% とほぼ変わらない。一方、損は成分で決まる。この独立な2軸から、避けるべきは**「通信量が多く、かつ成分が異なる」組み合わせ**となる。しかし実測では太い通信の両端はいずれも同一成分で、成分をまたぐ通信は最大 2.6% であり、本アプリケーションに**この組み合わせは存在しなかった**。便益の大きい相手を選ぶ限り、粒度損の危険は踏まないことになる。

---

## 6. 今後の課題

成分を跨ぐアプリケーションでの実行。(★本文が書きかけ)

また本実験は単一ノードで行っており、ノードをまたぐ通信 (overlay ネットワーク) を含まない。先行研究[1]が示した効果の大部分は overlay の有無に由来するため、マルチノード環境では便益がさらに大きくなると予想される。

---

## 参考文献

[1] I. Wickramanayaka, C. Keppitiyagama, K. Thilakarathna: Communication-Affinity Aware Colocation and Merging of Containers, *International Journal of Advances in ICT for Emerging Regions*, 15(3), 2022.

[2] Google Cloud Platform: Online Boutique, GitHub `GoogleCloudPlatform/microservices-demo`, 2025.

> ★NotNets [Alvaro 2024] の引用は削除済み(配置の研究ではないので「オートスケール環境を対象としていない」という限界指摘が当たらない)。**bib エントリ `alvaro2024` は `fose2026.bib` に残してある**ので復活は容易。復活させるなら先行研究の段落ではなく第1段落(動機)に置く。

---

# 執筆メモ(提出時は削除)

## ★★ 追加実験の指示: 全構成を5サイクルに統一 (2026-09-13 ユーザ決定)

### 方針
表2 の7構成はサイクル数がバラバラ(frontcatalog のみ6、他は3)なので、**全構成5サイクル**に揃える。
**枠の適正化と実験設計は、mix / mix2 の対応するものと必ず同じにすること。** 片方でも違うと既存データと合算できず、全部やり直しになる。

### 現状と不足

| アーム | 出所 | 現在 | 追加 |
|---|---|---|---|
| frontcatalog | mix | 6 (cyc1-6) | **不要**(cyc1-5 を使う) |
| frontreco | mix | 3 | +2 |
| frontcart | mix | 3 | +2 |
| normal | mix | 3 | +2 |
| frontemail | mix2 | 3 | +2 |
| frontcheckout | mix2 | 3 | +2 |
| checkoutemail | mix2 | 3 | +2 |
| catalogcheckout | mix2 | 3 | +2 |
| normal | mix2 | 3 | +2 |

追加 64点 (mix 側24点 + mix2 側40点)。**1点 7分45秒 → 約8時間15分。**

### 実行コマンド

**mix 側**(適正化対象 = frontend / productcatalog / **recommendation** / **cart**)

```sh
cd /home/mizuki/ダウンロード/msa
DIR=km2/experiments/summer2026
ARMS="normal frontreco frontcart" \
RATES="100" BROWSE_RATE="0 100 200 300" \
CYCLES=2 CYC_START=4 \
RIGHTSIZE=1 RS_SERVICES="frontend productcatalogservice recommendationservice cartservice" \
RS_SCALE=1 LIMIT_X=0 LIMIT_SCALE=0 \
HPA_TARGET=70 HPA_MIN=1 HPA_MAX=8 SU_WIN=30 SD_WIN=60 PRESCALE=1 \
WARM=180 MEAS=240 SAMPLE=15 PRE_VUS=600 MAX_VUS=4000 \
CSV=$DIR/results-mix.csv TL=$DIR/timeline-mix.csv EV=$DIR/events-mix.csv LOG=$DIR/mix.log \
bash $DIR/bundle-vs-loss2.sh
```

**mix2 側**(適正化対象 = frontend / productcatalog / **checkout** / **email**)

```sh
ARMS="normal frontemail frontcheckout checkoutemail catalogcheckout" \
RATES="100" BROWSE_RATE="0 100 200 300" \
CYCLES=2 CYC_START=4 \
RIGHTSIZE=1 RS_SERVICES="frontend productcatalogservice checkoutservice emailservice" \
RS_SCALE=1 LIMIT_X=0 LIMIT_SCALE=0 \
HPA_TARGET=70 HPA_MIN=1 HPA_MAX=8 SU_WIN=30 SD_WIN=60 PRESCALE=1 \
WARM=180 MEAS=240 SAMPLE=15 PRE_VUS=600 MAX_VUS=4000 \
CSV=$DIR/results-mix2.csv TL=$DIR/timeline-mix2.csv EV=$DIR/events-mix2.csv LOG=$DIR/mix2.log \
bash $DIR/bundle-vs-loss2.sh
```

### ★絶対に変えてはいけない設定(既存ログから確認済み)

| 項目 | mix (9/2・9/3) | mix2 (9/7) |
|---|---|---|
| 購入レート | `RATES=100` | 同じ |
| 閲覧レート | `BROWSE_RATE="0 100 200 300"` | 同じ |
| HPA | 目標70% / 1-8台 / 増30s・減60s | 同じ |
| 開始台数 | **1** (`PRESCALE=1`) | 同じ |
| ウォームアップ / 計測 | 180s / 240s | 同じ |
| 採取間隔 | 15s | 同じ |
| `RIGHTSIZE` | 1 | 1 |
| `RS_SCALE` / `LIMIT_X` / `LIMIT_SCALE` | 1 / 0 / 0 | 同じ |
| **`RS_SERVICES`** | frontend productcatalogservice **recommendationservice cartservice** | frontend productcatalogservice **checkoutservice emailservice** |
| 適正化テーブル | `summer2026/rightsize-requests.csv` | 同じ |

**`RS_SERVICES` だけが両者で異なる。** ここを取り違えると既存データと混ぜられない。

`CYC_START=4` にすること(既存が cyc1-3 のため)。mix.csv には frontcatalog / frontrecocatalog / frontrecocartcatalog の cyc4-6 が既にあるが、アームが違うので衝突しない。

### ★進行状況 (2026-09-13 18:41 開始、自動で mix → mix2 と続く)
- ラッパー `/tmp/claude-1000/-home-mizuki--------msa/013632c7-4050-49fb-a6b4-039521eff418/scratchpad/run-cyc45.sh` が上の2コマンドを順に実行中(PID は `pgrep -af bundle-vs-loss2` で確認)。完了すると `summer2026/.cyc45-done` が作られる。
- 進捗は `tail -f km2/experiments/summer2026/mix.log`(→ 完了後 `mix2.log`)。1点 約7.5〜7.75分。
- 見込み: mix 側 24点 → 約 22:30 完了 / mix2 側 40点 → 翌 03:30〜04:00 完了。
- ★2026-09-13 に `bundle-vs-loss2.sh` の「全台Ready待ち」バグ(READY `1/1` と AVAILABLE `1` を比べていて常に不一致→毎回 420s 待ち)を修正。実行中の mix 側は旧版のまま(6回×7分の空待ちが入るがデータには無害)、mix2 側から修正版が使われる。9/11 の fixed4 も同じ 420s 待ちで回っていた。
- 実行中の事故対策: `results-mix.csv.bak-20260913` は開始前バックアップ。

### 完了後にやること
1. 全構成 cyc1-5 で再集計し、表2 の「需要の伸び」と「粒度損」を更新
2. §4 冒頭の `(3サイクル)` を `(5サイクル)` に
3. 表2 の脚注から「frontend+catalog のみ6サイクル」を削除

### ★未解決のまま残る問題(サイクルを増やしても直らない)
mix と mix2 は **`RS_SERVICES` が違う**ため、同じサービスでも需要の伸びの値がずれる(cart: mix 1.45倍 / mix2 1.94倍)。表2 の**行間で伸びを比較することは厳密にはできない**。
直すには7構成を1本の実験・単一の枠設定で回す必要があり、3サイクルでも約12時間25分。締切には間に合わないため見送り。
論文には「枠の適正化は同居対象に限るため、実験ごとに適正化したサービスが異なる」と書いて対応する(§4 冒頭の方針と整合)。

---

## 分量

**現状3ページ。制限は2ページ。** 実測では本文をソースで約10行削れば入る。

未着手の削減候補(削減幅の大きい順):

| 候補 | 削減 | 失うもの |
|---|---|---|
| 式(2) と枠の適正化 | 約10行＋数式 | §4.1 の「枠が7%不足」の根拠。§4.1 を畳んだ今、用途はほぼこれだけ = **一番安い** |
| 予備実験 §3.1 | 約12行 | 「Kubernetes でも集約が効く」という土台 |
| §6 今後の課題 | 約7行 | 単独では足りない |

★注意: 日本語はソース1行(約40字)が組版で約2行になる。**表を削るより本文を削るほうが2倍効く**(表1+表2を両方消しても3ページのままだった)。

## 数値の出所

| 記述 | 出所 |
|---|---|
| §3.1 softirq −17〜23% / −43〜51%、p50、過負荷 348/425/435 | `km2/experiments/summer2026/results-fixed4.csv` (2026-09-09、k6、4台固定・HPA無し、150/200/250/300 各3サイクル + 500 を1回) |
| 表2 buy(100)/buy(150) | `summer2026/results-ratesweep2.csv` (実験9/7) |
| 表2 view(300) | `summer2026/results-mix2.csv` (実験9/7) |
| email 1台で83% | `summer2026/timeline-mix2.csv` / `timeline-ratesweep2.csv` |
| 枠を3倍変えても −16.4% / −16.2% | `summer2026/results-mix.csv` (9/2) と `results-scale3.csv` (9/4) |
| 成分をまたぐ通信は最大 2.6% | `km2/experiments/results-edge-pairs.csv` (2026-09-08、`ss -tin`) |

## 未解決の判断

1. **過負荷点 (348 / 425 / 435 周/秒) は 1 サイクルのみ**。softirq と p50 は3回反復だが、この3数字だけ n=1。本文では並べて書いてあるので「3回反復」と誤読されうる。「1回の観測」と明記するか反復を取る。
2. **便益の台数依存性が未検証**。本稿は台数4のみ。「スケールアウトしても効くのか」は査読で必ず問われる。
   - 既存の `latency-breakdown/replica-count-sweep.csv` は **使えない**(2026-07-14、locust 閉ループ、softirq 列なし、n=1、台数と性能が非単調: normal が 4台1015 / 3台688 / 2台930 / 1台681 rps)
   - 追加で回すなら: normal / f3perc × 台数 1・2・4 × buy(200) × 2サイクル = 12点、WARM 90s + MEAS 120s で**約1時間**。「削減率は台数に依らずほぼ一定」と言えれば一文で済む
   - 時間が無ければ §6 に「便益は台数4での測定であり、台数依存性の検証は今後の課題」と明記
3. **77% の由来が本文に無い**。§4.1 の「増設ラインをわずかに超えた (83%)」の増設ライン = **HPA 目標利用率70% × 許容幅1.1 = 77%**。HPA 設定の段落はユーザ判断で削除したので、由来だけをどこかに入れる(案: 「増設ライン (目標70%＋許容幅10%) である77%」= 行数増なし)。★ユーザが「別のところに入れる」として保留中
4. **§6 今後の課題が書きかけ**(「成分を跨ぐアプリケーションでの実行。」体言止め)
5. **著者の英語表記がプレースホルダ**(`Author Name` / `Graduate School, University`)

## 査読で突かれそうな点と手当て

| 指摘 | 手当て |
|---|---|
| 単一ノードで overlay がない | §6 に明記済み。先行研究の効果の大部分が overlay 由来であることも書いた |
| 1アプリのみ | §6 に今後の課題として明記 |
| 危険な象限(太い×成分違い)を実証していない | §5 で「本環境では空だった」と正直に書く。**実証したとは書かない** |
| 枠の適正化に恣意性 | §4 に式(2)と k=100 の根拠。適正化しない場合の損は測定誤差由来であることを §4.1 で示す |
| スケールアウトしたら効果が消えるのでは | **未手当て**(上記「未解決の判断」2) |
| 容量は律速要因(プローブ設定・個別サービスの枠)に支配されるのでは | §3.1 は取りこぼし・失敗とも0の帯で測っているので該当しない。ただし §4(HPA 有り)は該当しうる |

## ビルド

```sh
cd FOSE2026-TeX-UTF8
platex -kanji=utf-8 fose2026; pbibtex fose2026; platex -kanji=utf-8 fose2026; platex -kanji=utf-8 fose2026; dvipdfmx fose2026.dvi
```

`latexmk` はこの TeXLive に未インストール。**必ず `FOSE2026-TeX-UTF8/` 内で実行**(リポジトリルートで実行すると `texput.log` を残して失敗する)。
