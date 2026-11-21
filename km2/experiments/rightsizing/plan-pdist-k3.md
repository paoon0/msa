# 計画: 枠を基準で 3 台にして、ρ の近さでペアを選ぶとどうなるか (pdist-k3)

作成 2026-10-15。**同居実験の結果を見る前にコミットする。** `plan-pdist2.md` (今の枠で 4 組を足す案) は実行せず、この計画で置き換える。

## 1. 問い

ユーザの問いは「ρ (= 閲覧 1 周が購入 1 周の何倍の CPU を使うか) の近さでペアを選ぶとどうなるか」。台数の予測が当たるかは問わない。

pdist (2026-10-14) では、ほとんどの回で台数が 1 台か 2 台にしかならず、引きずりは「あり / なし」の二択でしか見えなかった。そこで枠を縮めて台数の段階を増やし、ρ の差の大きさと、引きずられた台数 Δn の関係を見る。

## 2. 枠 (ユーザ確定 2026-10-15)

- **基準の配合 b50v150 で 3 台になる枠**にする。r = D1(b50v150) / 1.5 (= pdist の枠の 1/3)。D1 は `results-mix-cpu2.csv` の、基準の配合・1 台のときの平均。
  - 1 台なら利用率 150% になり、HPA の判定で 3 台に増え、3 台のときに約 50% になる。
  - **2026-11-06 のやり直し (pdistk3sep2 / pdistk3pair2) は D1 を `results-mix-cpu3.csv` から取った表 `rightsize-pdist-k3-mc3.csv` を使う** (式は同じ、`make_rightsize_k3.py` で生成。mix-cpu2 は Prometheus の元データが消えて検証できないため取り直した)。旧表 `rightsize-pdist-k3.csv` (mix-cpu2 由来) は 2026-10-16 の pdistk3sep / pdistk3pair が使ったもので、消さずに残す。差は各サービス ±6m 以内。
- **ad はペアに入れない。枠は大きめの 800m にする** (2026-10-15 ユーザ確定。当初案 600m は跳ね上がり約 580m で 96% になり 77% を超えるので変更)。基準の配合では利用率約 8%、起動直後の JIT の跳ね上がり (pdist で最大約 580m) でも約 72% で、77% を超えない。limits は 1000m に上書きするので requests ≤ limits。
- redis-cart は RS_SERVICES の対象外。normal のマニフェストの 300m のまま、HPA なしで常に 1 台 (表の値は実際と合わせて 300 と書く)。
- 表: `rightsize-pdist-k3.csv`。

| サービス | 枠 [m] | サービス | 枠 [m] |
|---|---|---|---|
| frontend | 477 | currency | 220 |
| reco | 314 | cart | 127 |
| catalog | 276 | checkout | 78 |
| shipping | 32 | email | 31 |
| payment | 24 | ad | 800 |

## 3. ペア (10 組)

pdist の 6 組 (front+ad を除く) と、通信量の太い線から選んだ 4 組。通信量は `edge-traffic/results-edge-pairs.csv` のヘッダ込みバイト量 (購入 100 のとき、サービス間エッジ合計に対する割合)。

| ペア | アーム | ρ の差 | 通信量 |
|---|---|---|---|
| checkout + shipping | pairsP1b | 0.00 | 3.7% |
| catalog + reco | pairsP1b | 0.02 | 18.4% |
| front + cart | pairsP2 | 0.17 | 4.1% |
| catalog + checkout | pairsP2 | 0.36 | 2.3% |
| front + catalog | pairsP3 | 0.01 | 38.8% |
| currency + checkout | pairsP3 | 0.28 | 2.6% |
| front + currency | pairsQ1 | 0.09 | 8.5% |
| checkout + cart | pairsQ1 | 0.20 | 2.7% |
| front + reco | pairsQ2 | 0.01 | 4.8% |
| checkout + front | pairsQ3 | 0.37 | 2.5% |

- `pairsP1b` は pairsP1 から front+ad のブロックを除いたもの。残りのブロックが同一であることを機械的に確認済み。

## 4. 実験

- アーム: `normal` / `pairsP1b` / `pairsP2` / `pairsP3` / `pairsQ1` / `pairsQ2` / `pairsQ3` の 7 アームを 1 回の本走で回す。normal を全組で共有する。
- 点: b100v0 / b50v150 / b50v300。
- **開始台数は 3 と 4** (pdist の「基準の台数と、その 1 つ上」に合わせる)。点ごとにリセットする。
- 3 サイクル。点と開始台数の順番はサイクルごとにシャッフルし (SHUFFLE_SEED=1)、アームの順番は回転させる。
- 7 アーム × 3 点 × 開始 2 通り × 3 サイクル = 126 回。pdist の 1 回あたり約 8.7 分から、**約 18〜19 時間**。
- WARM 180 s / MEAS 240 s。HPA は目標 70%、コンテナ別、SU 30 s / SD 60 s、**min 1 / max 12** (pdist の 8 から上げる)。
- limits の上書き: frontend 3000m、catalog 3000m、ad 1000m。GRPC_LB=1。
- 各点の前に、CPU 温度が 70℃ 以下になるまで冷却待ちを入れる。
- ノードの容量: 実験以外の Pod の requests は約 1.05 コア。開始 4 台のときの requests 合計は約 9 コア (全サービス 4 台、ad 600m × 4、redis 0.3 を含む)。16 コアに収まる見込み。

## 5. 判定と集計

- **主判定 (同じ Pod の中で)**: 同居 Pod の各コンテナについて、サンプルごとの希望台数 = n (|u/70 − 1| ≤ 0.1) / ceil(n·u/70) を出し、窓内の最頻値が Pod の台数 n_st より小さければ「引きずられた」とする。Δn = n_st − 希望。
- **副判定 (分離との比較)**: 同じサイクル・点・開始台数の normal の台数 n_x と n_st を比べ、Δn' = n_st − n_x と損 [m] を出す。
- 両方を並べる。主判定には HPA の履歴効果 (台数が増えると、下がる側の判定が遅れる) による盲点がある (pdist で確認)。
- **主な報告**: 10 組を ρ の差の順に並べ、18 回中何回引きずられたか、Δn の平均、損の平均を出す。どの点で、どちらの側が引きずられたかも示す。通信量を添える。
- 予測の的中率は出さない。
- 印: 取りこぼし (窓) > 1%、Pending、Ready 落ち。印を付けて報告し、印付きの回を除いた集計も併記する。
- 解析の単位はペア。回を合算した検定はしない。

## 6. 限界

- 枠を 1/3 にすると台数が増える。2 台目以降の振り分けのコスト κ (mix-cpu2 で 2〜20%) のため、基準の配合でも 3 台から外れうる。基準の配合 (対照) で全組の台数がどうなったかを先に示す。
- payment / shipping / email の枠は 24〜32m と小さく、アイドル時の揺れが利用率に大きく出る。
- 7 アームを 1 回の本走で回すので約 19 時間かかる。日内の温度変化などの影響は、アームの順番の回転と冷却待ちで抑える。
- front が 4 アームに入る。同じアームの組は同じ実行を共有するので、10 組は独立ではない。

## 追記 (2026-10-15、実行前)

- **判定の主従を入れ替える** (ユーザ確認): 副判定 (分離との比較) を主な判定にする。pdist で、主判定 (同じ Pod 内) が HPA の履歴効果で front+ad の引きずりを見逃したため。同じ Pod 内の判定は補助として残す。
- **分離を先に 12 サイクル単独で測る** (ユーザ判断): `ARMS=normal`、3 点 × 開始 2 通り × 12 サイクル = 72 回 (約 10.5 時間)。目的は、分離の台数が回ごとにどれだけ揺れるかを知り、比べる相手を「同じ条件の分離の最頻値」にすること。分離が回ごとに割れた条件は「境目の条件」として印を付ける。同居のアームはこの後に回す (回し方は分離の結果を見てから決める)。
- 開始台数は 3 と 4 (同居と同じにする。HPA は始めた台数によって落ち着く台数が変わるので、分離も同じ開始台数で測る必要がある)。
- スモークで見つかった不具合: ad の枠 (600m) がマニフェストの limits (500m) を超えると、requests の置換が API に拒否された。`apply_rightsize.py` で requests と limits の上書きを同じコマンドで出すように修正した。

## 追記 2 (2026-10-15 14:40、実行前。開始台数の変更)

- 分離 12 サイクル (開始 3/4) を 14:07 に始めたが、アヌビスの点検を待つためユーザ指示で 14:30 ごろ止めた (途中の結果を見て止めたのではない)。測れた 2 点 (cyc1 の b50v150・b50v300、開始 3) は `results-pdistk3n.csv` に残すが、本集計には使わない。
- アヌビスの点検で次の 3 点が分かった。
  - 3 台以上を「1 台と 2 台の差で直線に延ばす」推定は実測の約 2 倍の台数を出していた (b50v300 で cart 推定 9 → 実測 5、currency 8 → 5、catalog 6 → 4)。開始台数の選定根拠には使えない。§6 の帯の計算も同様。
  - 開始 3 でも計測窓の中で台数が動いた (payment 3→5→4→3、最後の変化は 336 s)。
  - 開始 8 の予約合計は k6 の 800m を含めると約 15.6 / 16 コアで余裕がない。
- **ユーザ決定: 分離も同居も開始 1 台だけにする。** 開始台数を人が選ぶ要素をなくす。
- **ブレの扱い (ユーザ決定)**: 分離の台数が回ごとに揺れる条件は、同居でも同じように揺れると考える。揺れは捨てずに「ブレ」と印を付けて報告し、後から考察する。印は次の 2 種類で、どちらも集計から除かず併記する。
  - **回ごとのブレ**: 同じ配合で、分離 12 回の台数 (計測窓の最頻値) が 1 種類にそろわないサービス。12 回の分布をそのまま示す。
  - **窓内の変化**: 計測窓 (180〜420 s) の中で台数が変わった回 (`replicas_changed_in_window`)。どのサービスが、いつ、何台から何台に変わったかを示す。
- 主判定: 同居 Pod の台数 n_st と、同じ配合の分離 12 回の台数の最頻値 n_x を比べる (n_st > n_x なら引きずられた、Δn = n_st − n_x)。回ごとの比較 (同じサイクルの分離) も併記する。同じ Pod の中での判定は補助。
- 回数:
  - 分離: 3 点 × 開始 1 × 12 サイクル = 36 回 (約 5.2 時間)。
  - 同居: 6 アーム × 3 点 × 3 サイクル = 54 回 (約 7.8 時間)。分離の後に回す。
- 予約合計 (開始 1 台、k6 を含む): 約 1.6 + 0.8 + 0.3 + 1.05 + 0.8 ≈ 4.6 コア。最大は分離の実測の到達台数で確認する。

## 追記 3 (2026-10-15、実行前。配合を 4 つに)

- **ユーザ決定: 配合に b100v200 を加え、b100v0 / b50v150 / b50v300 / b100v200 の 4 つにする。** b100v200 は閲覧 ÷ 購入 = 2 で基準 (3) に近いが、負荷の総量が最大 (300 周/s)。ライブ論文で front+catalog が引きずられた購入 100 + 閲覧 200〜300 に当たり、「負荷が高いと ρ が近くても引きずられるか」を見る点。mix-cpu2 では測っていない (測った最大は b100v150)。予測には使わないので判定には影響しない。
- 回数: 分離 4 点 × 12 サイクル = 48 回 (約 7 時間)、同居 6 アーム × 4 点 × 3 サイクル = 72 回 (約 10.4 時間)。
- 本走の前に、b100v200・開始 1 台・全 7 アーム (分離と同居 6 つ) で短いスモーク (WARM 60 / MEAS 60) をして、取りこぼし・Pending・予約合計と、新しい枠での同居マニフェストの動作を確かめる。

## 追記 4 (2026-10-16 00:10、同居の結果を見る前)

- 分離 12 サイクル (`results/timeline/events-pdistk3sep.csv`, `pdistk3sep.log`) は 2026-10-15 15:21〜22:17 に完了。48 回すべてで枠検査合格・取りこぼし 0・Pending 0。cyc12 b50v300 だけ k6 の集計回収に失敗した (results に行がない) が、時系列は窓の全体が揃っているので台数の比較には使う (取りこぼしは不明として印)。
- 同居 6 アーム × 4 配合 × 3 サイクル (`pdistk3pair`) を 2026-10-16 00:10 に開始 (ユーザ指示)。設定は分離と同じで、アームの順番はサイクルごとに回転 (ROTATE_ARMS=1)。
- 解析スクリプト `analyze_pdist_k3.py` を追記 2・3 の判定に合わせて書き直した (同居の結果を見る前に固定): 主判定 = 分離 12 回の最頻値との比較、回ごとの比較と Pod 内の補助判定を併記、ブレの印 (回ごと = 分離 12 回がそろわない側 / 窓内 = 同居 Pod の台数が窓内で変わった回)、配合 4 つ。

## 追記 5 (2026-10-16、アヌビス点検後。同居の結果は pairsP1b cyc1 の 2 観測だけ見た後)

アヌビスの点検で、マニフェストの配線・HPA・分離との条件差に明確なミスはなかった。解析スクリプトを次のように直した (**主判定の規則は変えていない**)。
- 「Ready落ち」の印は台数変更の途中を誤って拾っていた (ready は Deployment、current は HPA の status から取るため。分離の時系列で ready<current の 107 サンプル中 106 が current≠desired)。台数が動いていないサンプルに限定した。
- 計画 §5 の「印付きの回を除いた集計」が未実装だったので §4 に追加した。Pending は同居 Pod 以外の分も「Pending(他)」として印を付ける。
- 事後の参考として「分離 12 回の最大値を超えた回数」を併記する (分離が割れている条件、例えば checkout b100v200 の 5×7/6×5 で、1 台差を引きずりと言い切らないため)。
- 「回ごとの比較」は、点の順番が同じサイクル番号どうしの比較で、測定日時は 9 時間以上離れている。

限界に足すこと:
- 分離と同居を交互でなく別の時間帯 (分離 10/15 15:21〜22:17、同居 10/16 00:10〜) に測っている。
- cart・currency・reco は分離では terminationGracePeriodSeconds 5 s、同居 Pod に入ると既定の 30 s。HPA と Service は終了中の Pod を数えないので台数への影響はほぼないと見る。
- events-*.csv は見出しとデータ行の列数がずれ、件数も欠けている。台数変化の時刻は timeline から出し、events は根拠に使わない。

## 追記 6 (2026-11-19、周波数固定後のやり直しの設計。分離・同居とも未実行)

ユーザ決定 (2026-11-19):
- **CPU 周波数は固定** (2026-11-17 16:56 から、ターボ無し P 2.1 / E 1.5 GHz、`km2/experiments/shared/cpufreq.sh`)。実験前に `cpufreq.sh status` で no_turbo=1 を確かめる。
- **ペアは今の 10 組のまま** (6 アームのマニフェストも同じ)。ρ を mix-cpu4 (周波数固定) で測り直しても近い 4 組 (差 ≤0.01) と遠い組の並びは変わらない。ただし front+currency の差は 0.10/0.08 → 0.05/0.07 (1 台/2 台) に縮んだ。front+currency を「遠い」のまま扱うか「中くらい」として別に報告するかは、2026-11-19 ユーザ決定で**分類しない** (「分類は別に必要ない。ρの差だけで十分」) → ρ の差の値で扱う。
- **枠の作り方は変えない**: r = D1(b50v150、1 台、6 サイクル平均) / 1.5、ad 800 / redis-cart 300 固定。D1 は `results-mix-cpu4.csv` から取る (`make_rightsize_k3.py`)。**2026-11-19 生成済み `rightsize-pdist-k3-mc4.csv`** (ユーザ了承「作っていいよ」、見込みと全サービス一致): frontend 906、reco 584、catalog 533、currency 369、cart 234、checkout 154、shipping 61、email 52、payment 36 [m] (mix-cpu3 由来の表の 1.5〜2.0 倍)。
- **配合は 5 つ: b100v0 / b50v150 / b50v300 / b75v200 / b0v300**。b100v200 は b75v200 に替える (予約の見込みが 16 コアを超えるため。b100v200 の見込み 15.0〜17.6 コア → b75v200 12.3〜14.3 コア、実験以外の約 2.95 コアを含む)。b0v300 (閲覧だけ) を足す (見込み 約 10.5 コア。checkout/payment/shipping/email は 1 台のまま、front/catalog/reco は 3 台の見込み)。b0v50 / b0v100 は全サービス 1 台の見込みで情報が無いので入れない。b50v300 の見込みは 13.8〜14.8 コアで余裕が小さい。
- **HPA の窓: 増設窓 (SU) 30 s・減少窓 (SD) 30 s・慣らし (WARM) 300 s・計測 (MEAS) 300 s** (smoke-k3win / smoke-k3su30 の結果から)。
- サイクル数は現行案 (分離 12・同居 3) のまま。追加測定のルール (損が分離のふれ幅に入った組を追加で測るか) は未決。
- 見込み時間: 5 配合 × (分離 12 + 同居 6 アーム × 3) = 150 回 × 約 12 分 = 約 30 時間。
- 本番の前に、予約が容量に収まるかを短いスモークで確かめる (未実施)。
- **2026-11-19 アヌビスの点検 (枠の表 `rightsize-pdist-k3-mc4.csv`)**: 表の値は生データから 1m 単位で再現、b50v150・1 台の 6 点は除外条件・飽和に当たらない、requests ≤ limits (ad は LIMIT_OVERRIDE 1000m が前提)、旧表 mc3 も再生成で一致。**訂正 1 — 容量の見込みが小さすぎた**: 上の見込み (b75v200 12.3〜14.3、b50v300 13.8〜14.8) は 2 台以降の CPU を据え置く下限寄りの推定だった。pdistk3sep2 の実測で ±0.15 コアで当たった外挿 (2 台から先は (D2−D1)/2 ずつ増える) では、b100v0 12.6 / b50v150 11.7 / b50v300 14.7 (幅 14.4〜16.5) / **b75v200 15.3 (幅 14.1〜16.2)** / b0v300 10.9 コア (実験以外 1.05 + k6 0.8 + redis 0.3 + ad 0.8 を含む)。立ち上がりの増やしすぎで +0.25〜0.85 コア → b75v200 は 16 コアに届きうる。**訂正 2**: 2 節の「3 台のときに約 50%」は、mix-cpu4 では 58〜66%。**スモークで見ること**: b75v200・b50v300 で Pending 0、b50v150 で checkout / shipping が 3 台に届くか (2 台で止まる余裕が 1% 以下)、周波数固定後の ad 起動時の CPU と台数。スクリプト (一時) は scratchpad の chk1〜5.py / chk4_H.py / chk4_mc3_H.py。
- **2026-11-19 ユーザ決定 (「aで」)**: limits は上げない (新しい枠でも全サービスで requests ≤ limits、mix-cpu4 と同じ limits)。email の limits 300m は据え置き (1 台 b100 系で絞り最大 9.2% が出るのは立ち上がりだけの見込み) → 容量スモークで計測窓内の email の絞りを確かめる。
- **2026-11-19 ユーザ決定 (「この三つを同居させるアームを一つ追加する」): frontend + catalog + reco を 1 Pod に同居させるアームを本番に足す**。
  - 使うアームは既存の `frontrecocatalog` (= FOSE 論文の front3、マニフェスト `km2/variants/frontrecocatalogcart/`。名前に cart が付くが中身は 3 コンテナ、cart+redis は別 Pod)。新しいマニフェストは作らない。Pod 内の通信は frontend→catalog・frontend→reco・reco→catalog の 3 本とも localhost (2026-09-08 の実測で全体の通信量の 34.4% + 28.1% + 4.4% ≈ 67%)。
  - ドライバの設定との組み合わせを確認 (2026-11-19、apply はしていない): マニフェストをクラスタに触れずに読み、`apply_rightsize.py` に通すと、3 コンテナとも新しい表の枠 (server 906m / recommendation 584m / productcatalog 533m、Pod 合計 2023m) と LIMIT_OVERRIDE (server・productcatalog 3000m) が当たる。PROBE_TIMEOUT の対象 `frontend:recommendation` もコンテナ名が一致。GRPC_LB=1 では fixed4-lb (2026-10-07) で動いた実績あり。同梱の HPA (上限 5) はドライバの make_hpa が apply の後に作り直す。
  - 容量の見込み (mix-cpu4 の 2 台の当てはめから、3 サービスの必要台数): 5 配合とも 3 サービスの連続値の必要台数が 0.2 以内に揃い (例 b75v200: 3.30 / 3.41 / 3.23)、束ねても予約は分離と同じ (b50v300・b75v200 で 8.09 コア、他は 6.07 コア)。ただし推定なので、新しい枠・PROBE_TIMEOUT=5 でこのアームを通したことはまだ無い → 本番前のスモークに入れる。
  - ρ の差 (mix-cpu4、1 台 / 2 台): 3 組の最大で 0.012 / 0.002 (front 0.328/0.322、catalog 0.316/0.324、reco 0.321/0.323)。解析 (`analyze_pdist_k3.py`) はペア前提なので、3 つ同居の扱い (ρ の差を最大値で代表させるか等) は解析時に決める (未決)。
  - 回数: 5 配合 × (分離 12 + 同居 7 アーム × 3) = 165 回 × 約 12 分 = **約 33 時間** (+3 時間)。
- **2026-11-20 アヌビスの点検 (2 回目の変更が 3 回目 pdistk3sep3 / pdistk3pair3 に引き継がれているか、取る値に誤りが無いか)**。ドライバは 2 回目と同じコミット 68ef35c から未変更なので、2 回目の変更 (内側 280 s・予約枠の区間・-times/-raw・枠検査・リセット・シャッフル・GRPC_LB) は全部引き継がれている。**起動前に必須** (A・B はメインで再確認済み):
  - A. PROBE_TIMEOUT の当て先 (`bundle-vs-loss2.sh:440`) が 3 通りだけで、pairsP1b の reco (Deployment `productcatalogservice` のコンテナ `recommendation`) に当たらない。失敗は `>/dev/null 2>&1` で黙る (:443)。→ 近い組 catalog+reco だけ reco のヘルスチェックが 1 s のまま。
  - B. 閲覧の失敗数 `browse_failed` (k6/checkout.js:165) が結果 CSV に無い。failed_rate・p50/p99 は購入の要求からだけ出すので、b0v300 では常に 0。
  - C. `analyze_pdist_k3.py` が 2 回目用のまま (4 配合・mix-cpu2 の ρ・ペアだけで frontrecocatalog を黙って捨てる・start_ok/frames_ok を見ない) で未コミット。結果を見る前に直してコミットし、追加測定のルールと 3 つ同居の扱いを決めて書く。
  - D. 本番の起動コマンドを先に書く (ROTATE_ARMS=1、7 アーム、PROBE_TIMEOUT)。
  - 推奨: 各点で no_turbo を確かめる・START 行に PROBE_TIMEOUT/VU/コミット・アームごとに Deployment の yaml を保存・sample_hpa.py に spec.replicas・collect_events.py の列ずれ修正。任意: 同居のサイクルに normal を混ぜる。
  - 解析で対処: 窓内の台数変化は timeline から数え直す (replicas_changed_in_window は両方向に誤る、HPA の status は 1 サンプル遅れる)。得の CPU は -raw.csv でサービスに帰属。終了後すぐ Prometheus から熱による周波数低下・絞りを書き出す。
  - 本番の名前は pdistk3sep3 / pdistk3pair3 (提案、ユーザ未確定)。
- **2026-11-20 ドライバ修正 (ユーザ了承「1」= アヌビスの A・B)**: `../summer2026/bundle-vs-loss2.sh` — (A) PROBE_TIMEOUT の当て先を、全 Deployment からイメージ名 (recommendationservice / LB_IMG_RECO) で探す方式にし、当てた後に readiness/liveness の timeoutSeconds を読み返して 1 つでも違えばアーム中止。(B) 結果 CSV の末尾 (n_samples の後) に `browse_failed`, `browse_failed_rate` (= 閲覧の失敗数 ÷ 計測窓で始めた閲覧の周) を追加。未コミット、実機では未確認 (修正確認のスモークは未実施)。
- **2026-11-20 smoke-k3f3 の結果で本番は保留**: k6 → frontend の負荷がほぼ 1 Pod に集中する (分離・同居とも、k6 の接続の使い回しと推定)。front3 b50v300 で p50 1.78 s。k6 の接続の扱いを決めるまで、修正確認のスモークと本番は起動しない (ユーザ条件「現在のスモークで問題がなく…」を満たさないため)。
- **2026-11-20 k6 の接続の張り直し (ユーザ決定「はりなおしでいい」、SN と同じ noConnectionReuse)**: `NO_REUSE=1` を k6/checkout.js・k6/k6-job.yaml・measure-mix-cpu.sh・bundle-vs-loss2.sh に追加 (既定 0 = 従来どおり。ドライバの START 行に no_reuse・probe_timeout・vus・コミットを出すようにした)。確認の測定 noreuse-chk (1 台固定 × 3 点 × 2 サイクル) で、frontend の D が基準の配合 b50v150 で +11.8%、粗い ρ 0.330 → 0.304。起動前に決めた目安 (3% 以内・ρ 差 0.02 以内) を満たさない → 今の ρ (mix-cpu4) と枠の表 mc4 は張り直しの条件に合わない。ρ・枠の測り直しかどうかをユーザに相談中。
- **2026-11-20 ③ ときどき張り直す (CLOSE_EVERY=20 = 要求 20 回に 1 回 Connection: close、ユーザ指示「3も試してみたい」)**: smoke-k3close20 で frontend の Pod 別 CPU が均等 (最大/最小 ≤ 1.08)、3 つ同居 b50v300 p50 12 ms。close20-chk で frontend の D が b50v150 +0.3%、粗い ρ 0.331→0.314 → 目安内 = 今の ρ (mix-cpu4) と枠 mc4 をそのまま使える見込み。**2026-11-20 ユーザ決定「とりあえずこの時々変更する方式で行こうと思う」= ③ CLOSE_EVERY=20 (回数で閉じる) を採用。** 時間で閉じる方式・k6 の版固定・ρ と枠の生カウンタでの作り直しは未決。別件: 周波数固定後、購入ありの点で p99 が 350〜840 ms (張り直しと無関係、mix-cpu4 でも同じ)。原因未調査。
- **2026-11-21 mix-cpu5 完了 (CLOSE_EVERY=20、6 サイクル)**: 生カウンタで ρ は mix-cpu4 とほぼ同じ (2 台 |Δρ| ≤ 0.001、1 台 front/catalog/reco −0.002〜−0.004、cart −0.009)、ペア差の符号は不変 (`analysis-rho5.txt`)。Pod 間の偏り無し (`analysis-podbalance-mc5.txt`)。**未決 (ユーザ判断)**: 本番の枠・ρ を mix-cpu4 のまま使うか、mix-cpu5 (張り直しあり・生カウンタ) で作り直すか。
- **2026-11-21 ユーザ指示「今回のρを元に改めて枠を決定して、次の実験準備をしてほしい」**:
  - **枠の表 `rightsize-pdist-k3-mc5.csv` を作成** (作り方は従来どおり r = D1(b50v150、1 台、6 サイクル平均) / 1.5、ad 800 / redis-cart 300 固定。D1 は mix-cpu5 を生カウンタで作り直した `analysis-rho5-work/mc5raw.csv` から、`make_rightsize_k3.py`)。mc4 との差: frontend 906→910、checkout 154→155、cart 234→230、catalog 533→539、currency 369→367、payment 36→38、shipping 61、email 52→53、reco 584→586 [m]。合計 4029→4039m (+10m) なので容量の見込み (b75v200 約 15.3 コア) は変わらない。
  - **解析 `analyze_pdist_k3.py` を 3 回目用に修正 (結果を見る前、アヌビス C)**: 配合 5 つ、ρ を mix-cpu5 (1 台 = 主、2 台 = 参考列 Δρ2)、frontrecocatalog を 3 メンバーの 1 観測 (Δρ = 3 組の差の最大 0.013、損 = n_st·Σr − Σn_x·r、引きずられた側 = n_x < n_st のメンバー全部、通信量は 3 本の和 62.0%)、start_ok / frames_ok = 0 に印 (開始不良・枠不一致)。主判定の規則は不変。確認: 2 回目 (pdistk3pair2/sep2) に通すと判定の回数は修正前と全組で一致 (ρ の列だけ変わる)。smoke-k3close20 で 3 メンバーの行が出ることを確認。ρ の差の並びは mix-cpu4 と同じく近い 5 組 (checkout+shipping 0.005、front+catalog 0.006、front+reco 0.007、3 つ同居 0.013、catalog+reco 0.013) と遠い組 (front+currency 0.050 〜 checkout+front 0.310)。
  - **未決 (起動前にユーザが決める)**: (1) 追加測定のルール (損が分離のふれ幅に入った組を追加で測るか)。(2) ~~k6 の版を固定するか~~ → **2026-11-21 ユーザ指示「固定しておいてくれない？」で固定済み**: `km2/experiments/k6/k6-job.yaml:25` を `grafana/k6@sha256:3d8e5c7f…` (mix-cpu5 と同じ v2.4.0) に変更 (クライアント側の dry-run で Job として通ることを確認、クラスタには何も適用していない)。(3) 本番前に新しい枠で容量スモークをするか (下の案)。(4) 本番の名前 pdistk3sep3 / pdistk3pair3。
  - **起動案 (未起動。引き金はユーザ)**。容量スモーク (分離・3 つ同居 × 予約が大きい b75v200・b50v300 × 1 サイクル、約 50 分。見るもの: 載らない Pod (FailedScheduling) 0 件、枠不一致 0、email の絞り、b75v200 の予約):
    ```
    S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; O=$S/smoke; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $O/cpufreq-smoke-k3mc5-20261121.txt; CLOSE_EVERY=20 RESET_EACH_POINT=1 POINTS="b75v200 b50v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc5.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 ARMS="normal frontrecocatalog" CYCLES=1 CSV=$O/smoke-k3mc5-20261121.csv TL=$O/timeline-smoke-k3mc5-20261121.csv EV=$O/events-smoke-k3mc5-20261121.csv LOG=$O/smoke-k3mc5-20261121.log bash $S/bundle-vs-loss2.sh > $O/stdout-smoke-k3mc5-20261121.txt 2>&1; echo "smoke exit=$?"
    ```
    本番 (分離 12 サイクル → 同居 7 アーム × 3 サイクル、5 配合、165 回、見込み約 33 時間):
    ```
    S=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026; R=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing; bash /home/mizuki/ダウンロード/msa/km2/experiments/shared/cpufreq.sh status > $S/cpufreq-pdistk3sep3-start.txt; CLOSE_EVERY=20 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b75v200 b0v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc5.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 ARMS="normal" CYCLES=12 CSV=$S/results-pdistk3sep3.csv TL=$S/timeline-pdistk3sep3.csv EV=$S/events-pdistk3sep3.csv LOG=$S/pdistk3sep3.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3sep3.txt 2>&1; echo "sep exit=$?"; CLOSE_EVERY=20 RESET_EACH_POINT=1 POINTS="b100v0 b50v150 b50v300 b75v200 b0v300" STARTS="1" SHUFFLE_POINTS=1 SHUFFLE_SEED=1 RIGHTSIZE=1 RSTABLE=$R/rightsize-pdist-k3-mc5.csv RS_STRICT=1 CHECK_FRAMES=1 RS_SERVICES="frontend checkoutservice cartservice productcatalogservice currencyservice paymentservice shippingservice emailservice recommendationservice adservice" LIMIT_OVERRIDE="frontend=3000m productcatalogservice=3000m adservice=1000m" PROBE_TIMEOUT=5 WARM=300 MEAS=300 HPA_MIN=1 HPA_MAX=12 HPA_TARGET=70 SU_WIN=30 SD_WIN=30 COOL_TEMP=70 ARMS="pairsP1b pairsP2 pairsP3 pairsQ1 pairsQ2 pairsQ3 frontrecocatalog" ROTATE_ARMS=1 CYCLES=3 CSV=$S/results-pdistk3pair3.csv TL=$S/timeline-pdistk3pair3.csv EV=$S/events-pdistk3pair3.csv LOG=$S/pdistk3pair3.log bash $S/bundle-vs-loss2.sh > $S/stdout-pdistk3pair3.txt 2>&1; echo "pair exit=$?"
    ```
  - **2026-11-21 ドライバに k6 イメージの記録を追加 (ユーザ指示「2はやっといて」)**: `../summer2026/bundle-vs-loss2.sh` — k6-job.yaml の digest を読み START 行に `k6=sha256:…` を出す、点ごとに k6 Pod の imageID をログに「k6 イメージ: pod=… imageID=…」で残し、指定と違えば「!!」で警告 (止めない)。`bash -n` と照合部分の単体確認のみ、実機未確認。measure-mix-cpu.sh には入れていない。
  - 起動前の確認 (2026-11-21 15:06、読み取りのみ): 周波数固定 (no_turbo=1、P 2100 / E 1500)、namespace に実験以外のもの無し (sn-test 無し)、他の実験プロセス無し、ディスク 7%、ノードに固定した k6 イメージあり。
  - **2026-11-21 アヌビスの実装点検 (読み取りのみ)**: 重大なし。中 3 つ (未対処、ユーザ判断待ち): (中1) Pending の数え方が「載らない (FailedScheduling)」と「コンテナ作成中」を区別しない (`../summer2026/sample_hpa.py:53` = phase だけ見る、自分でも確認) → 容量スモークの「Pending 0」は FailedScheduling のイベントで判定する必要がある。(中2) すべて未コミットで START 行の commit から中身を辿れない、枠の表 mc5 は git 外 → 起動前にコミットするか表の sha256 を START 行に出す。(中3) 周波数の確認が記録だけで止め役になっていない、同居側の直前の記録が無い → no_turbo=1 でなければ止める 1 行と、同居側の前の記録を足す。軽微: analyze_pdist_k3.py の引数の既定値・説明文が古い、点の欠けで観測が黙って消える、frontrecocatalog は残りのサービスを variants のコピーから apply (今は normal と同一)、ROTATE で frontrecocatalog の順番が 7・6・5 番目だけ。問題なし: 環境変数の読み込み、枠の当たり方 (全アーム)、HPA はコンテナ別、PROBE_TIMEOUT、imageID の追記、解析と出力の噛み合い、上書き事故なし、所要 約 33 時間。
  - **2026-11-21 中 1〜3 を修正 (ユーザ了承「いいよやっておいて」、未コミット・実機未確認)**: (1) `../summer2026/bundle-vs-loss2.sh` が点ごとに FailedScheduling のイベントを回収して events に残し、ログに「載らない Pod (FailedScheduling): N 件」を出す。`../summer2026/collect_events.py` は行に limit_x / browse_rate を入れてヘッダと列を揃えた (それ以前の events-*.csv は 2 列ずれ)、REASON があれば message の頭に付ける。`analyze_pdist_k3.py` は FailedScheduling を「載らない」の印にする。→ **容量スモークの判定は「Pending 0」ではなく「載らない Pod 0 件」**。(2) START 行に no_turbo と、ドライバ・checkout.js・k6-job.yaml・apply_rightsize.py・枠の表の sha256 (先頭 12 桁) を出す。(3) ドライバが起動時に no_turbo=1 でなければ止まる (REQUIRE_PINNED=0 で外せる)、起動時の cpufreq.sh status を `<ログ名>-cpufreq-start.txt` に残す (同居側の起動直前も残る)、点の終わりごとに no_turbo を確認して外れていれば「!!」。軽微: analyze_pdist_k3.py の引数の既定値を 3 回目 (pdistk3pair3 / pdistk3sep3 / mc5) に、説明文を更新、観測数を期待値と並べて表示。確認: `bash -n`、追加部分の単体実行、collect_events の出力、解析の 2 回目データでの回帰 (判定は不変)、偽の FailedScheduling で印が付くこと。
  - **2026-11-21 容量スモーク smoke-k3mc5 合格** (分離・3 つ同居 × b75v200 / b50v300、4/4 点): 載らない Pod 0 件、取りこぼし 0、枠検査 OK、k6 imageID 4/4 一致、計測区間の email の絞り 0%、予約の最大 約 15.4 / 16 コア (k6・実験以外を含む見込み)。ドライバの 11/21 修正は実機で動いた。残る懸案は p99 709〜809 ms (既知)。本番の起動はユーザ判断。
    2 回目のコマンドからの変更: CLOSE_EVERY=20 追加、POINTS (b100v200→b75v200、b0v300 追加)、RSTABLE mc3→mc5、PROBE_TIMEOUT=5 追加、WARM/MEAS 180/240→300/300、SD_WIN 60→30、frontrecocatalog 追加。
  - **2026-11-21 アヌビスの「計測時間のミス」点検 (読み取りのみ、未対処・ユーザ判断待ち)**: (重) MicroK8s の `--event-ttl=5m` のため、点の終わりに 1 回だけ回収するイベントからは t_rel≲326 s (ウォームアップ全体と窓の頭 約 26 s) が消える。smoke-k3mc5 の「載らない Pod 0 件」はイベントだけでは裏付けにならない。直し方 = 時系列の採取ループ内で重複を除きながら回収 (最低でも WARM 直後にも回収)、events に t_rel 列。(中) 窓の基準 t_run は k6 の開始より 4.2〜6.3 s 遅い。終わり側の余裕は 3.7〜5.8 s で、はみ出しても警告だけ → analyze_pdist_k3.py で margin_start_s/margin_end_s < 0 に印。(軽) analyze_pdist_k3.py の load() は同じ (cycle, arm, point) の重複測定を混ぜる → 最後だけ使うか assert。問題なし: ウォームアップ混入、s/ms、UTC/JST、予約の窓平均の再現 (4/4 一致)。
  - **2026-11-21 (軽) の重複測定を修正 (ユーザ指示「3はそうならないようにして」、未コミット)**: `analyze_pdist_k3.py` の load() が、同じ (cycle, arm, point) の測定が複数あれば最後の 1 回だけを使う (results は最後の行、timeline は t_rel が戻った所で区切って最後の区切り)。重複があれば「注意: … 最後の測定だけを使う」と表示。failed_sched() も times.csv の最後の t_run より 60 秒以上前のイベントを捨てる。確認: smoke-k3mc5 で修正前と出力が同じ、測り直しを模擬して 1 回目を改ざんした CSV でも結果は同じ (旧版は混ざって台数が変わる)。(中) の窓はみ出しの印はユーザ判断で入れない (「2は結構」)。(重) のイベント回収は未対処。修正前の控え: scratchpad analyze_pdist_k3.before-dup.py。
  - **2026-11-21 (重) のイベント回収を修正 (ユーザ指示「では直しておいて」、未コミット・実機未確認)**: 重さは話し合いで「中〜軽」に訂正 (計測窓の中は最初の約 26 秒を除き終わりの回収で残る。載らない状態が続けばイベントは更新され続けるので見える。消えるのはウォームアップ中に一瞬だけ載らなかったもの)。`../summer2026/bundle-vs-loss2.sh` が計測窓の始まり (sleep $WARM の直後) に SuccessfulRescale と FailedScheduling のイベントを裏で取っておき、点の終わりの回収と `../summer2026/collect_events.py` の新しい環境変数 EARLY で metadata.uid ごとに重ねる (同じイベントは後で取った方)。裏で取るので窓の時刻はずれない。確認: 作った JSON で重ね方・SINCE の絞り・EARLY 無し/ファイル無しで従来どおりになることを確かめた。bash -n 通過。実機ではまだ回していない。控え: scratchpad bvl2.before-ev.sh / collect_events.before-ev.py。
  - **2026-11-21 21:52 本番 pdistk3sep3 途中の所見**: cyc2 normal b75v200 (20:51 開始) で載らない Pod 1 件 (FailedScheduling、recommendationservice の 4 台目、Insufficient cpu)。時系列ではウォームアップ中の t_rel 140〜217 の約 90 秒だけ Pending (ns の予約 13.63 + Pending 0.59 コア、payment が 6 台に行き過ぎていた時期)、t_rel 233 で載り、計測窓 (300〜600) の中は Pending 0・reco 4 台で一定・取りこぼし (窓) 0。修正したイベント回収で初めて見えたもの。解析では点ごとのイベントで「載らない」の印が付くので、ウォームアップ中だけか窓に掛かるかを分けて判定する (未対応、解析時に要検討)。
