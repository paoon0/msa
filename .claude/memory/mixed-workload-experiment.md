---
name: mixed-workload-experiment
description: 【混合ワークロード実験 2026-09-02完了・58/60点】購入型100固定+閲覧型0/100/200/300で需要のズレを作り、5構成×3サイクル。閲覧300でnormalだけSLO未達(0/3)。粒度損は22回中5回で直接観測(全てfrontcart)。但し予約枠は台数が揃うと完全同一=指標の分解能が粗い
metadata:
  type: project
---

**資産: `km2/experiments/summer2026/` の `results-mix.csv` / `timeline-mix.csv` / `events-mix.csv` / `mix.log`。索引は `EXPERIMENTS.md`。旧版(定義変更前の36点)は `archive-mix-old/`。**

## 条件
5構成(normal / frontcatalog / frontreco / frontcart / **frontrecocatalog**=frontend+reco+catalogの3つ束ね) × 購入型100周/s固定 × 閲覧型 0/100/200/300周/s × 3サイクル = 60点。取得58点(欠測2=ConfigMapマウント失敗、内容と無関係)。
開始1台・ウォームアップ180s・計測240s・枠は束ね候補4つのみ適正化・上限はマニフェストのまま。所要7時間37分。

## ★結果1: 閲覧型300で normal だけがSLOを満たせなかった(0/3)
束ねた4構成は満たした。p50: normal 9 / 238 / 627ms(3サイクルで単調悪化)、frontcatalog 10/10/10ms、frontrecocatalog 8/8/8ms。
**これは台数の刻みに依存しない明確な差**=容量の差。閲覧比率が上がるほど分離が先に崩れる。

## ★結果2: 粒度損を直接観測(束ねPod増加22回中5回で引きずられ)
判定法=台数がn→n+1になった瞬間の各コンテナ利用率。片方が70%未満なら引きずられ。
**引きずられた5回はすべて frontcart**:
| cyc | 閲覧 | 利用率 |
|---|---|---|
| 2 | 0 | cart 136% / **frontend 67%** |
| 1 | 200 | **cart 67%** / frontend 78% |
| 2 | 200 | **cart 67%** / frontend 85% |
| 1 | 300 | **cart 66%** / frontend 88% |
| 3 | 300 | **cart 61%** / frontend 81% |
★**閲覧0では cart が frontend を引き上げ、閲覧200/300では frontend が cart を引き上げる=損の向きが比率で逆転**(前回36点でも同じ現象を観測、再現した)。
**frontcatalog / frontreco / frontrecocatalog は 17回すべてで両コンテナとも70%超=損ゼロ。**(閲覧経路同士なので比率によらず同時に熱くなる)

## ★★結果3: 予約枠(損の指標)の限界が判明
**閲覧型100では15点すべてが 8.604コア(2065.0コア秒)で完全一致。** 理由=全構成が同じ台数(FE2/cat2/reco2/cart2/他1)に落ち着き、**束ねてもサービスごとの枠は変わらない**(同じ数字を足す順番が違うだけ)。
⇒ **予約枠に差が出るのは台数が食い違うときだけ。刻みは1台分(0.36-1.08コア)で中間値が存在しない。**
実際に差が出たのは: 閲覧0で frontcart のみ +17.6%(1728 vs 1470)、閲覧200/300で構成ごとにばらつく(2257-2889)。

## ★実験設定の不足(ユーザ指摘、データで裏付け)
1. **予約枠は整数の台数でしか動かない。** 台数が揃えば1ミリコアも変わらない。分解能が粗すぎる
2. **選んだ負荷点が平坦な場所に当たった。** 4点中1点(閲覧100)は情報量ゼロ。台数が切り替わる境目を狙って刻めていない
3. **CPU時間の差がサイクル間のばらつきと同程度。** 閲覧0のnormalは3サイクルで819/842/840秒(幅2.8%)、frontcatalogとの差は1.1%。n=3では有意差を主張できない
⇒ **細かい効率差の測定には不足。但し「捌けるか否か」(閲覧300でnormalのみ失敗)は取れている。**

## 計測基盤(この実験から有効)
`node_cpu_sec`(increase厳密) / `reserved_core_sec`(15秒ごとの予約枠を窓で時間積分) / `dropped_win`(窓のみ・購入と閲覧別) / `browse_*` / `replicas_changed_in_window` / timelineに`browse_rate`列。
**確保CPUの導出**: 15秒ごとにPod実体から予約枠を集計(k6load/promq/istio-proxy除外、Running/Pending分離)→計測窓の16サンプルの平均×240秒=面積。誤差は段差1台×15秒で全体の0.7%程度。使ったCPUはカウンタ差分なので厳密。

## 欠測の原因(未解決)
`FailedMount: object exp/k6-script not registered` → backoffLimit=3 でPodは作り直されるが、**再作成に約1分かかる間もスクリプト側の待ち時間が進むため、k6が35秒しか走れず結果を出せない**。根本対策=待ち時間の起点を「k6が実際に走り出してから」に変える(未実装)。発生率 58点中2点。

関連: [[coloc-gain-replica-saving]] [[coloc-bundling-decision-rule]] [[rightsizing-experiment]]
