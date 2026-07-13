# 調査記録: 「なぜ normal(分離)は頭打ちするのか」と co-location の本当の価値

作成 2026-07-14。SCALE_ALL 実験 → ボトルネック診断 → レイテンシ分解 → 固定台数スイープ の一連の調査結果と考察。
関連CSV/ログは `km2/experiments/` と `km2/experiments/latency-breakdown/`。
**重要: この調査で当初の主張を複数訂正した。訂正内容は各節と §7 にまとめる。**

---

## 0. 共通の実験条件
- 環境: MicroK8s 単一ノード(~16 vCPU)、namespace=exp、Istio無し(inject:false)。監視=kube-prometheus-stack。
- 負荷: locust checkoutフロー。1周=3req(GET /product → POST /cart → POST /cart/checkout)。
  `wait_time=constant_throughput(1)`(=各ユーザ1周/秒を目標、**返事を待ってから次へ=閉ループ**)。spawn rate=40。
  → **rps上限 = users×3**(u240:720 / u480:1440)。
- アーム: `normal`(分離=1Pod1サービス) / `f3avg`(束ね+Pod平均HPA) / `f3perc`(束ね+コンテナ別HPA)。
  束ね=frontend Pod に frontend+recommendation+productcatalog を同居しlocalhost通信。cart+redisは分離固定(redis分裂回避)。
- 指標: rps, p50/p90/p99, fails, softirq/req(通信カーネルCPU), app/req(cgroupアプリCPU), node/req(ノード非idle全体), 各サービスのレプリカ数・CPU利用率。

---

## 1. SCALE_ALL 本実験(全サービスHPA, 3アーム×3cyc×u240/480)
CSV=`results-hpapercont-allscale.csv`。HPA=CPU70%/min1/max4。全アプリサービスに個別HPA(redisのみ固定)。

### 1-1. 集計結果(3サイクル平均, 1リクあたり CPU-ms)
| arm | users | rps | softirq/req | app/req | node/req | node_cores(of16) |
|---|---|---|---|---|---|---|
| 束Pod平均 | 240 | 703 | 0.622 | 9.26 | 10.36 | 8.0 |
| 束コンテナ別 | 240 | 705 | 0.632 | 9.32 | 10.55 | 8.2 |
| 分離normal | 240 | 639 | 0.932 | 10.23 | 11.42 | 8.0 |
| 束Pod平均 | 480 | 749 | 0.494 | 8.33 | 9.41 | 7.9 |
| 束コンテナ別 | 480 | 852 | 0.567 | 8.85 | 10.03 | 9.4 |
| 分離normal | 480 | 664 | 0.918 | 10.08 | 10.93 | 8.0 |

**読み:**
- **softirq/req は束ねが分離の約半分**(u240 0.62 vs 0.93 = −32%, u480 0.5-0.57 vs 0.92 = −38〜46%)。全条件で一貫=これが最も堅い差。
- **app/req(アプリ計算CPU)はほぼ同じ**(束ね8.3-9.3 vs 分離10.1-10.2)。やや低いのは通信付随処理(シリアライズ等)が localhost で軽い分。純粋計算は不変。
- **node/req(ノード全体)は束ねが約1割低い**(softirq削減が効いている)。
- **注: node_cores は ~8/16 コア=ノードは半分空いている**。どのアームもCPU飽和していない(後の§4で重要)。

### 1-2. 各サービスのレプリカ数(cyc1/cyc2/cyc3)
**users=240**
| サービス | 束Pod平均 | 束コンテナ別 | 分離normal |
|---|---|---|---|
| frontend | 2/2/3 | 3/3/3 | 3/3/3 |
| recommendation | ↑同居 | ↑同居 | 2/2/2 |
| productcatalog | ↑同居 | ↑同居 | 3/3/3 |
| checkout | 1/1/1 | 1/1/1 | 1/1/1 |
| cart | 2/2/2 | 2/2/2 | 2/2/2 |
| currency | 2/2/2 | 2/2/2 | 2/2/2 |
| payment | 1/1/1 | 2/2/2 | 1/2/1 |
| shipping | 1/1/1 | 1/1/1 | 1/1/1 |
| email | 2/2/2 | 2/2/2 | 2/2/2 |
| ad | 1/1/1 | 1/2/1 | 1/1/1 |
| **総Pod** | 12/12/13 | 14/15/14 | 18/19/18 |

**users=480**
| サービス | 束Pod平均 | 束コンテナ別 | 分離normal |
|---|---|---|---|
| frontend | 2/3/2 | **4/3/4** | 3/3/3 |
| recommendation | ↑同居 | ↑同居 | 2/2/2 |
| productcatalog | ↑同居 | ↑同居 | 3/3/3 |
| checkout | 1/2/1 | 2/1/2 | 1/1/1 |
| cart | 2/3/2 | 2/2/2 | 2/2/2 |
| currency | 1/2/2 | 2/1/2 | 2/2/2 |
| payment | 1/2/1 | 2/1/2 | 1/2/2 |
| shipping | 1/2/1 | 2/1/2 | 1/1/1 |
| email | 2/3/2 | 2/2/3 | 2/2/2 |
| ad | 1/1/1 | 1/1/1 | 1/1/1 |
| **総Pod** | 11/18/12 | 17/12/18 | 18/19/19 |

**読み:**
- **総Pod差の正体=reco+catalog**。分離は reco2+catalog3=5Podを単独で持つ。束ねはこれをfrontend Podに畳む→総Pod 12-18 vs 分離18-19。
- **他のサービス(checkout/cart/currency/payment/shipping/email/ad)は3アームほぼ同数**(共通の固定サービス)。
- **u480の双安定がサイクルで丸見え**: 束コンテナ別 frontend=4/3/4(cyc2だけ低い枝で3・総Pod12)、束Pod平均=2/3/2。**分離は3/3/3で常に安定(双安定しない)**。

### 1-3. u480双安定(バイモーダル)
束ね u480 は「高い枝 ~960rps(frontend4到達)」と「低い枝 ~630rps(frontend2-3停止)」を行き来。
- f3perc u480 = 964/636/956 rps
- f3avg u480 = 643/966/638 rps
- normal u480 = 630/708/653 rps(安定)

★当初「双安定=単一HPA判定の脆さ」と解釈したが、後の§5で**HPA無し固定台数でも双安定が出た**ため、**根本は負荷モデル(constant_throughput)の閉ループ**と判明(§6)。

---

## 2. ボトルネック診断: u480 rps崩落の正体=emailservice
スクリプト=`bottleneck-diag.sh`。SCALE_ALL前は u480 で束ねも rps が ~630 に崩落していた。
負荷中の per-container スロットリング率(CFS)を採取:
| container | 使用mc | 制限mc | %of制限 | throttle% |
|---|---|---|---|---|
| **email** | 270 | 300 | 90% | **96.7%** ←律速 |
| payment | 184 | 300 | 61% | 5.8% |
| checkout | 585 | 1200 | 49% | 0.0% |
| redis | 90 | 500 | 18% | 0.0% |

- **email(制限300m/1レプリカ)が96.7%スロットリング**。checkoutがPlaceOrder内でemailを同期gRPC呼び出しするため、emailが詰まると全checkoutが待たされ、constant_throughputで offered rpsごと崩落。
- **SCALE_ALL(emailにもHPA)で解決**: email等がスケール→rps 634→962(+52%)。
- **fails(HTTP500)の正体**(`fail-capture-multi.sh`, 多数回): 混雑ピークで下流(email等)の**Readiness/Livenessプローブが1s期限にtimeout→一瞬NotReady→frontendが500**。フラップは毎回だが500発生は間欠(2/5)。email CPUを800mに上げるとフラップ消失+rps 950→1150、但し犯人がpayment/adに移動(モグラ叩き)。→ **email は後で200m/300mに戻して他実験と条件統一**。

---

## 3. レイテンシ分解: 「300ms はどこで消えるか」(通信 vs 待ち行列)
スクリプト=`latency-breakdown/latency-sweep.sh`。負荷を1→480に振り、各点でリクエスト種別ごとレイテンシ・checkout下流ホップ・**各サービスCPU利用率(使用/request%)**を採取。SCALE_ALL(HPA)構成。

### 3-1. レイテンシ vs 負荷(p50 ms)
| users | normal rps | normal p50 | bundle rps | bundle p50 |
|---|---|---|---|---|
| 1 | 3 | **17** | 3 | **17** |
| 10 | 30 | 28 | 30 | 24 |
| 40 | 120 | 53 | 119 | 54 |
| 120 | 356 | 100 | 349 | 140 |
| 240 | 590 | 360 | 706 | 78 |
| 480 | 711 | 650 | 1172 | 310 |

- **1ユーザの床=両方17ms**(=通信/構造のコストは小さい)。
- normal は負荷で 17→650ms に膨張(約40倍)=**待ち行列(負荷依存)**。1ユーザで既に高いわけではない=**通信/経路長が主因ではない**(当初の私の説明を訂正)。

### 3-2. 各サービスCPU利用率の推移(使用/request %)★要望データ
**normal(分離)** — 負荷が上がると計算サービスが飽和していく:
| users | productcatalog | recommendation | frontend | cart | currency |
|---|---|---|---|---|---|
| 1 | 2% | 2% | 2% | 2% | 2% |
| 10 | 15% | ~9% | 17% | 9% | - |
| 40 | 45% | 23% | 45% | 31% | 22% |
| 120 | 105% | 67% | 107% | 59% | 58% |
| 240 | **159%** | 94% | 87% | 83% | 78% |
| 480 | **134%** | 106% | 67% | 94% | 103% |

**bundle(f3perc)** — catalog/recoはfrontend Podに同居(=frontend欄に合算)、飽和するのはcart/currency:
| users | frontend(束ね) | cart | currency | checkout | payment |
|---|---|---|---|---|---|
| 1 | 1% | 2% | 2% | - | 1% |
| 40 | 31% | 25% | 19% | - | 11% |
| 120 | 79% | 62% | 50% | 34% | 23% |
| 240 | 71% | 86% | 82% | - | 61% |
| 480 | 81% | **130%** | **125%** | 84% | 83% |

**読み:**
- **normal の頭打ち=productcatalog/recommendation 等の計算サービスがCPU飽和(100%超)して待ち行列を作る**。通信ではない。
- **束ねでは catalog/reco が飽和リストから消える**(frontend Podに畳まれ、localhostで軽い&frontendと連動スケール)。代わりに**同居していない cart/currency が次の詰まり所**に(=玉突き)。
- ※「%of request」は request比。request(catalog600m/limit1000m)なので134%=804m<limit=**スロットリングはしていない**(request超えはバースト、正常)。§4で「これは過渡」と判明。

---

## 4. 固定台数比較: 「頭打ちはHPA過少スケールか経路長の壁か」
スクリプト=`fixed-replicas.sh`。HPA切って全サービスを4台固定(request150mに下げてノードに載せる。limit据置=実処理不変)。u480。

### 4-1. normal 4台固定
| | rps | p50 | p90 | p99 | node |
|---|---|---|---|---|---|
| HPA均衡(参考) | 664 | 650 | 843 | 1233 | 8/16 |
| **4台固定** | **1022** | **280** | 740 | 1100 | 13.7/16 |

各サービス定常CPU(絶対mc / limit比): frontend 710m(44%), reco 608m(38%), currency 403m(25%), **catalog 363m(36%)**, checkout 223m(19%), cart 215m(22%), email 108m(36%)…**全サービス limit の44%以下=誰も飽和していない**。

**★決定的**: 台数を増やすだけで rps +54%(664→1022), p50 半減(650→280)。
- **normal の頭打ちは「経路長(通信)の壁」ではなく「HPA過少スケール」**。1ユーザ床17msで通信は微小。HPAは各サービスをCPU70%目標で満足させて止まるが、その均衡は多ホップ遅延が高い動作点。**HPAは遅延を見られない(CPU盲点)ので追加レプリカを足さない**。
- **§3の catalog 134%飽和は過渡だった**: 定常(6分計測)では catalog は 363m(36%)で余裕。HPA本実験でも catalog は常に3台(max=8でも増えない)=恒常飽和なら6台に増えるはず→増えない=**134%は立ち上がり中のピーク**。

### 4-2. bundle 4台固定(クリーン)
※初回は束ねマニフェスト同梱HPA(max5)が固定台数を上書き(frontend=5, email hop 1522ms等の過渡)→ apply後にHPA削除して再測。
| | rps | p50 | p90 | p99 | 総Pod |
|---|---|---|---|---|---|
| normal 4台 | 1022 | 280 | 740 | 1100 | 41 |
| **bundle 4台** | **1098** | 280 | **520** | 1100 | 33 |

- checkout下流ホップ email=6ms(正常)。全サービス低CPU。node 14.1/16。
- **4台なら両アームとも ~1000-1100rps・p50 280ms(ほぼ同じ)**。天井は同程度。
- 総Pod 33 vs 41 の差は reco/catalog を畳んだ分だが、**コンテナ数・CPU予約は同じ**(§7訂正参照)。

---

## 5. 固定台数スイープ(レプリカ 4,3,2,1 × u480)
スクリプト=`replica-count-sweep.sh`(warmup3分/計測3分=メイン実験と統一)。CSV=`replica-count-sweep.csv`。
| 台数 | normal rps | normal p50 | bundle rps | bundle p50 |
|---|---|---|---|---|
| 4 | 1015 | 350 | 1101 | 320 |
| 3 | **688** | 690 | 1112 | 350 |
| 2 | 930 | 210 | 935 | 220 |
| 1 | 681 | 690 | 640 | 700 |

**★重大な観察: 非単調・ノイジー(双安定)。**
- normal が「3台<2台」と物理的におかしい。1点1計測なので双安定でランダムに枝を引いている(normal-3=688は遅い枝, normal-2=930は速い枝)。
- **HPA無し固定台数でも双安定が出た** → §1-3で見た双安定は**HPAのせいではなく、`constant_throughput`(閉ループ)由来**と確定。
- robust に言えるのは端点のみ: 4台=両方~1000-1100, 1台=両方~640-680。中間は要反復。
- bundle は比較的クリーン(3台で早くも~1100飽和)、normal は erratic。

---

## 6. 負荷モデル(閉ループ)の問題 ★方法論上の重要点
`constant_throughput(1)`=各ユーザが応答を待って次を出す→**offered load がシステムの速さに依存**(閉ループ/フィードバック)。
- **双安定**: 天井付近で「速い状態(低遅延→追いつく→高rps)」と「遅い状態(高遅延→遅れる→低rps)」の2つが安定。どちらに落ちるかはウォームアップの偶然→**1点1計測はランダム**。
- **真の容量を測れていない**: 得られるrpsは「システム+閉ループ負荷ツール」の均衡であって、システム単体の最大処理量ではない。
- **比較が濁る**: co-loc vs normal で負荷自体が別の値に落ち着く。
- **含意**: 我々の"スループット/双安定"系の結果はこの影響下。双安定はHPA固有でない。
- **対処=開ループ負荷**(応答を待たず一定レートで投げ続ける/段階的レート掃引)→双安定が消え、真の容量とレイテンシ曲線がきれいに出る。**未実施・次の課題**。

---

## 7. 結論と訂正(正直な整理)

### 確定した事実
1. **softirq(通信カーネルCPU)は束ねが分離の約半分**(−32〜−46%)。全条件で堅い。localhost化の効果でPod数と無関係。
2. **normal のHPA頭打ち(664)はHPA過少スケール**: 4台固定で1022(+54%)。HPAはCPUしか見ず、多ホップ遅延(=真のボトルネック)が見えないため追加スケールしない=**HPA盲点の実例**。ノードは半分空き(CPU飽和ではない)。
3. **十分な台数を与えると normal も bundle も ~1000-1100rps・p50 280ms(同等)**。スループット/レイテンシの天井は同程度。

### 訂正した当初主張(この調査で自分で反証)
- ❌「co-locでレイテンシが下がる」→ **同台数ならnormalと同じ**(1ユーザ床も17msで同じ)。localネットワーク1ホップは元々サブミリ秒。**localhostが節約するのはCPU(softirq)であって時間ではない**。
- ❌「Pod数削減=資源メリット」→ **コンテナも予約も同じ**(3コンテナ別Pod=3×request、同居Pod=同じ3×request)。Pod数減はpause/kubeletの微差のみ。むしろ束ねは「3コンテナを同ノードに載せる」制約でスケジューリング不利。
- ❌「束ねはノードに載りやすい」→ **予約合計は同じ24コア**(束ねPodは3コンテナ分)。載りやすさは変わらない。
- ❌「双安定=単一HPA判定の脆さ」→ **固定台数でも双安定=負荷モデル(閉ループ)由来**。
- ❌「catalog 134%が恒常飽和」→ **立ち上がり過渡**。定常は36%、HPAは3台で満足。

### co-location の"確かな価値"(縮小後)
**唯一堅く残るのは softirq(通信CPU)の約半減。** ただし絶対量は ~0.5コア/1000rps ≈ 16コアノードの数%と控えめ。性能(rps/latency)は同台数なら差なし。→ **単一ノードでの"資源効率"物語は弱い**。

### 論文化への含意
- 単一ノードの効率主張は薄く、マルチノードの通信削減は自明。**非自明な核**が要る候補:
  (a) co-location × オートスケールの動的相互作用(ただし双安定は負荷モデル由来と判明し弱含み)、
  (b) 「HPAはCPU盲点で通信/遅延律速を過少スケールする」+それを解く手法(通信を見たスケール信号)。
- **次の必須修正=開ループ負荷**で真の容量・遅延曲線を取り直す(§6)。これ無しの throughput 比較は閉ループ均衡の値。

---

## 関連ファイル
- SCALE_ALL: `results-hpapercont-allscale.csv`, `hpa-percontainer-softirq.sh`(SCALE_ALL=1)
- max=8比較: `results-hpapercont-allscale-max8.csv`(normalは4→8で不変=上限律速でない)
- ボトルネック/fails: `bottleneck-diag.sh`, `fail-capture-multi.sh`, `loadgen-csv-fail.yaml`
- レイテンシ分解: `latency-breakdown/latency-sweep.sh` / `.csv`
- 固定台数: `latency-breakdown/fixed-replicas.sh`, `fixed-normal.log`, `fixed-f3perc.log`
- 固定台数スイープ: `latency-breakdown/replica-count-sweep.sh` / `.csv`
