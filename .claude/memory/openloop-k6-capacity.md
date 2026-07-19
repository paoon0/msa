---
name: openloop-k6-capacity
description: 【現行作業 2026-07-15】閉ループ負荷(constant_throughput)の双安定を外すため k6で開ループ(constant-arrival-rate)化し真の容量を測る。k6は動作、スイープ自動化の回収バグ修正中。
metadata: 
  node_type: memory
  type: project
  originSessionId: 20cea0c6-ac47-4825-8331-8727f5538d9f
---

**2026-07-15セッションの現行作業。[[hpa-scaling-angle]] の続き。resumeが重いのでメモから再開する用。**

## なぜ開ループか(重要な方法論修正)
これまでの負荷 locust `constant_throughput(1)` は **閉ループ**(各ユーザが応答を待って次を出す)。→ 天井付近で **双安定**(速い枝⇄遅い枝, 例 束ね u480=960↔630)になり、rpsがランダムにブレる。**真の容量を測れていない**(=システム+負荷ツールの均衡値)。★重要発見: この双安定は**HPA無しの固定台数でも出た**=HPA固有でなく**負荷モデル(閉ループ)由来**。対処=**開ループ**(応答を待たず一定到着レートで投げ続ける)。locustは本質クローズドなので **k6の constant-arrival-rate** を使う(ユーザ発案で「loadgeneratorで無理?」→over-provision近似も可だが k6採用)。

## k6 実装(資産 = `km2/experiments/k6/`)
- `checkout.js` — 開ループ本体。locustのcheckoutフロー移植(GET /product→POST /cart→POST /cart/checkout, 1周=1checkout, POST /cartは303→GET /cartをk6自動追従で実HTTP4req/周)。`constant-arrival-rate` rate=周/秒。**案C**=最初 WARMUP秒(VU立ち上げ過渡)を捨て MEASURE秒だけカスタム指標 m_* に記録(setup()でstart時刻→elapsed>WARMUPで記録)。handleSummary が `@@@K6_BEGIN@@@{json}@@@K6_END@@@` を stdout へ。
- `k6-job.yaml` — grafana/k6:latest, scriptをConfigMap(k6-script)でマウント, env RATE/WARMUP/MEASURE/PRE_VUS/MAX_VUS。command=`k6 run; echo @@@K6_DONE@@@; sleep 300`(Pod生存させ回収)。
- `run-k6-sweep.sh` — 掃引駆動。各アームを固定REPLICAS台(HPA無し, request150mでノードに載せる, 束ねは同梱HPA削除)デプロイ→レート掃引→各点で iter_rate(達成)/dropped/p50-99/failed/各サービスCPU(promq)/node を CSV(k6-sweep.csv)へ。

## ★実験設計(ユーザ確定)
- 固定台数(HPA無し)。**アーム=normal + bundle の2つ**(固定台数だとf3avg=f3percで同一になるため。ユーザ承諾済み)。
- REPLICAS=4, REQ_M=150m。RATES="100 200 300 400 500"周/秒。WARM=30 MEAS=180(案C, メイン実験と同じ本計測3分)。
- 容量の膝 = target に iter_rate が届かなくなる / dropped>0 / p99急上昇 する点。normal vs bundle を同じofferedレートで公平比較。

## ★サマリ回収バグ=解決(2026-07-16)
- **k6負荷自体は完全に動く**。手動単発でクリーンなサマリ取得済み: bundle rate200周/秒で **p99≈342/598/721ms**(MEAS20/40/60), rate50でp99=13ms → 200周/秒あたりで既にテール上昇。開ループ成立(iter_rate=target維持, dropped=0)。
- **★真の根本原因(当初診断は誤り)**: バグは「ログ回収失敗」ではなく `run-k6-sweep.sh` 行80の **`echo "$summary" | python3 - "$arm".. <<'PY'`** で、bashでは **heredoc `<<'PY'` が stdin を占有しパイプ `echo|` を無効化**。→ `python3 -` がheredoc本体をプログラムとして読み切り、続く `json.load(sys.stdin)` は空を読む→JSONDecodeError。summaryは実は正しく取れていた。
- **修正**: stdinを使わず **`SUMMARY="$summary" python3 - .. <<'PY'` + `json.loads(os.environ['SUMMARY'])`** に変更(コミット前)。過去の「絶対時刻待ち/stdout一本化」修正はそのまま有効。
- **ワンポイント検証OK**: t4.csv に1行=`bundle rate200 → iter_rate200/200 dropped0 rps600 p50 8.2 p99 702 node7.8cores, hot=currencyservice249%/checkout236%/cart182%/frontend180%`(手動p99721と整合)。**自動化パイプライン疎通完了**。
## ★本走完了(2026-07-16)= `k6-sweep.csv`
固定4台/HPA無し/req150m。過負荷域(normal400/500・bundle500)はk6自身がOOMでhandleSummary前に落ち回収失敗(=膝の先なので科学的要点に影響なし)。node_coresはpromqの内側rate[45s]が短くbundle全点NA→**Prometheus履歴からavg_over_time(rate[1m])[3m:15s]で補完**(内側は必ず[1m]以上=スクレイプ30s。normal補完値3.97/7.45/11.61がスクリプト記録4.0/7.3/11.8と一致=手法検証OK)。

| offered周/秒 | arm | iter/target | dropped | p50 | p99 | node cores |
|---|---|---|---|---|---|---|
|100|normal|100/100|0|6.3|**298**|3.97|
|100|bundle|100/100|0|6.0|**11**|3.88|
|200|normal|200/200|0|8.8|721|7.45|
|200|bundle|200/200|0|7.7|652|7.70|
|300|normal|299/300|**166**|120|2316|11.61|
|300|bundle|**300/300**|**45**|23|846|12.16|
|400|bundle|397/400|574|350|1938|14.46|

### ★結論(論文の核・開ループで双安定を外して真容量測定)
1. **容量↑**: normalは200→300で崩壊(dropped0→166,目標未達)。bundleは300を目標達成しつつ軽微dropped45、400で崩壊。→ **bundle容量≈300-350 vs normal≈250**。co-locが高容量=閉ループ双安定なしでcleanに実証。
2. **低負荷レイテンシ27倍差**: 100周/秒で p99 bundle11ms vs normal298ms。**node CPUは同一(~3.9cores,余裕大)** =CPU競合でなく純粋な通信経路差(localhost vs ClusterIP/Istio)。[[planA-echo-comm-time]]がアプリ層で顕在化。
3. **★node総CPUは同offeredでほぼ同等**(bundleが僅か高い時も=より多く捌くから)。→ **便益は「総CPU削減」でなく「レイテンシ/容量ヘッドルーム」として現れる**。[[megapod-latency-experiment]]の「低負荷で正味CPU差なし」と整合しつつ高負荷で容量差に転換。※[[softirq-cpu-metric]]のsoftirq削減は総CPUの小部分なので総node coresには埋もれる。
4. 副次: normalは400/500でk6 OOM回収失敗、bundleは400生存=応答速くVU滞留少。
- 次候補: 過負荷点欲しければk6 memory増(512→1024Mi req)で再取得 / node cores補完をrun-k6-sweep.shに恒久化([45s]→[1m]) / 図化。

## ★★run2完了(2026-07-17 00:09)= k6メモリ増量(req2048/lim4096Mi)で過負荷点も回収成功
run1=`k6-sweep-run1.csv`(1GB,過負荷OOM欠測), run2=`k6-sweep.csv`(4GB,全10点)。**OOM仮説を実証確定**: 別途bundle500を単発再現しPod`reason=OOMKilled`を直接観測(mem762Mi表示→上限突破)。run1の過負荷欠測は全てk6のOOMだった。

### run2 全10点(固定4台/HPA無/req150m/WARM30 MEAS180)
| off | arm | iter/tgt | dropped | p50 | p99 | node |
|---|---|---|---|---|---|---|
|100|normal|100/100|0|6.3|433|3.9|
|100|bundle|100/100|0|6.0|478|3.7|
|200|normal|200/200|0|9.1|918|7.7|
|200|bundle|200/200|0|7.7|681|7.9|
|300|normal|300/300|0|98.5|965|13.3|
|300|bundle|300/300|15|**21.5**|**563**|12.4|
|400|normal|**350**/400|**10086**|2970|8496|13.4|
|400|bundle|**397**/400|**707**|592|1299|14.7|
|500|normal|333/500|33042|3206|7520|12.4|
|500|bundle|**421**/500|15935|1951|7787|15.0|

### ★結論の改訂(run1→run2で再現性を検証。重要)
- **【撤回】低負荷27倍差はフロック**: run1 bundle100 p99=11msは再現せず(run2=478ms≒normal433ms)。p99=11 msは不自然に良すぎた=単発異常値。→ **「低負荷でbundleが桁違いに速い」は主張しない**。低負荷は正味差なし([[megapod-latency-experiment]]と整合)。
- **【堅い・本命】過負荷域の容量差は再現**: 400offeredで normal崩壊(iter350,dropped**10086**,p50 2970ms)vs bundle持続(iter**397**,dropped**707**=14倍少,p50 592ms=5倍速)。run1のbundle400(iter397,dropped574,p50350)ともほぼ一致。**bundle飽和スループット≈420 vs normal≈340 checkouts/s=約20%高**。
- **【中負荷レイテンシ】300offeredで bundle p50=21 vs normal p50=98(約4.7倍速)**、p99も563 vs 965。これは実在の差。dropはブレ(run1 normal300=166 vs run2=0)。
- **node CPUは同offeredで同等**、過負荷でbundleが僅か高い(14.7-15.0)=より多く捌くから。→ 便益は「総CPU減」でなく「容量/レイテンシ・ヘッドルーム」。
- **★方法論の教訓**: 単発は膝付近で不安定(normal300 dropped 166↔0, bundle100 p99 11↔478)。**過負荷域(400/500)の差だけが2runで一貫**。要replication(HPA実験のように3cycle推奨)。次=各点3反復 or 図化。

## ★★★3アーム×3サイクル本走 完了(2026-07-17 ~05:00)= `k6-sweep-3arm-3cyc.csv`(45点,失敗0)
ユーザ指示でmega追加・3反復。スクリプトにmega分岐(km2/all/all.yaml, megapod単一Deploy全11container+redis同居,全SERVICE_ADDR=localhost, frontend Svc selector app=megapod)とCYCLES対応(cycle列,サイクル外側=時間ドリフト対策)を実装。k6 mem 4GB。統計は`verify-numbers-python`でPython再計算。

### 達成スループット iter_rate 平均±SD(周/秒)= 容量
| off | normal | bundle | mega |
|---|---|---|---|
|300|298.8±0.7(drop256)|300±0|300±0|
|400|343.5±**20.8**|392.2±9.9|395.0±**0.5**|
|500|**308.8**±27.1|426.8±16.6|419.6±2.1|

### 有意性(簡易Welch t)
- bundle−normal: 400 +48.7(t3.7) / 500 +118(t6.4)=**有意**
- mega−normal: 400 +51.5(t4.3) / 500 +111(t7.1)=**有意**
- **mega−bundle: 400 +2.7(t0.5) / 500 −7.2(t−0.7)=差なし(有意でない)**

### ★確定した3発見(論文主図級)
1. **部分集約(bundle)も全部入り(mega)も分離(normal)比 容量+約25〜38%**(t3.7〜7.1で明確有意)。
2. **★mega=bundle(t<1=差ゼロ)。部分集約で容量便益はほぼ飽和し、全ホップlocalhost化しても増えない**=[[bundling-merit-question]]の目標1「部分的にまとめるのが良い」を直接支持。**「全部まとめる必要はない」**。
3. **分離は脆い**: normal容量SD大(400 ±20.8 vs mega±0.5)、p50も300で327±**307ms**、500で**308へ低下=輻輳崩壊**(bundle/megaは500でも上昇し飽和=崩れない)。=「分離は容量が低いだけでなく飽和近傍で不安定」。
- node CPU: 各レートでほぼ同等(同仕事=同CPU)、過負荷でbundle/megaが高利用率到達(14-15 vs normal11.8=崩壊でCPU使い切れず)。
- 未処理: bundle500のSD±16.6はやや大(1サイクルで枝が振れた可能性)。図化まだ。mega/bundleは500でも未飽和気味=容量上限見るならrate>500も要検討。
- 次候補(戦略): これは目標1/2共通の「後悔しない一手」完了。次は(a)機構分解を各アームに展開(softirq/latencyの用量反応をrps天井に接続)or (b)目標2のスケール/HPA軸へ or (c)図化。ユーザ判断待ち。

## ★機構分解と測定妥当性(2026-07-17セッション後半)
- **CPU/checkout(=node÷iter)**: 300で全アーム36〜41 mc秒でほぼ横並び(業務処理が大半で埋もれる)。→ **総CPUではco-loc効果は見えない**。
- **モード別CPU/checkout @300(3サイクル±SD)**: user 28.7/28.5/29.3(SD大0.17〜0.31=**ノイズ内、測れない**)、system 9.2/9.1/9.4(同)、**softirq 3.0/2.4/1.6 mc秒(SD極小0.01〜0.03)=◎信号≫ノイズ、normal→bundle→mega で −19%/−46% の明確な用量反応**。[[softirq-cpu-metric]]の加算性が1req単位でも再現。
- **★重要な訂正(ユーザ指摘で修正)**: 一度「総CPU/reqが平らだから容量向上はレイテンシ主因」と言ったが撤回。総/user/system CPUは背景+アプリ内在(GC/ランダム商品/cache)で**ブレて測定不能**(app-cgroupだけにしてもSD0.2残=内在ノイズ)。さらに**user/systemはco-locで本質的に変わらない**(業務ロジック・protobuf梱包は同じ仕事)=無い信号。→ **言えるのは「softirq削減(確定)」まで。容量+25%のCPU効率 vs レイテンシの要因分解は総CPU受動測定では不可能、介入実験(netem/CPU付与)が必須**([[verify-numbers-python]]の精度重視をまた実証)。
- **latencyは別軸の恩恵(確定)**: p99も用量反応(@100 normal375/bundle179/mega20ms, @300 p50 327/25/16ms)。低負荷でもテール差=CPU競合でなく純粋な経路短縮。softirq(効率)とlatency(応答性)は同一原因(NW経路除去)の別便益。
- **k6妥当性チェック済**: k6load Pod CPUは過負荷500でも0.5〜0.7コア(上限2.0に遠い)=飢えてない・アプリへの競合小。しかもnormal(0.45)<bundle/mega(0.60)=滞留VUはCPU無消費なので**in-cluster生成はnormalを不利にしていない**→容量比較の結論はより堅い。pinningは任意。
- **測定の注意/次への布石**: cadvisorの`container_cpu_user/system_seconds_total`内訳は**未スクレイプ**(合計のみ)。CPU隔離(kubelet reserved-cpus/static policy/isolcpus/cpuset, 2台目ノード)は可能だがsoftirqはNIC割込みで特別扱い&測定対象そのもの。負荷を2台目マシンに出す(外部NodePort or 2ノード目にk6固定+アプリ1ノード固定)が最も綺麗。
- **checkout.js改良案(未実施)**: 3種HTTP(GET product/POST cart/POST checkout)を今は合算計測→種類別(Trend3本 or tags)に分けると重いcheckout単体のco-loc効果が薄まらず見える。rps列=iter×3(1周3req計上, 実ワイヤは303追従で4req)。
- **未検証の核心(目標2)**: 全実験4台固定=co-locのHPA粒度損コストを測っていない=便益側だけ。台数スイープ(2/4/8)+不均一スケールで便益vs粒度損を対決させるのが次の決定打。単一ノードなのでnormalの通信は同一ホスト内(veth/kube-proxy)=マルチノードなら差はもっと出る(保守的)。
- 注意: **絶対パス /tmp はbash呼び出し間で非共有**(テスト出力はリポジトリ相対に出すこと)。CSV/LOGはenv override対応済(`${CSV:-...}`)。

## クラスタ状態
exp に bundle が4台固定・request150m・HPA無しで残存。スクリプトが冒頭で作り直すので放置可。停止時=全プロセス0/k6 pod 0。

関連: [[hpa-scaling-angle]] [[coloc-resource-efficiency-study]] [[verify-numbers-python]]
