---
name: demand-mismatch-experiment
description: 【2026-09-07完了60点】checkout/emailをfrontendに束ね需要のズレを最大化。★損の向きが閲覧比率で反転(frontemail 閲覧0で+1077m/閲覧300で+119m)。エッジなしfrontemailのsoftirq削減は+0.2%=ゼロ対照
metadata:
  type: project
---

**資産: `km2/experiments/summer2026/` の `results-mix2.csv` / `timeline-mix2.csv` / `mix2.log`、解析 `analysis-mix2.md`。新アーム4本は `manifests/{frontemail,frontcheckout,checkoutemail,catalogcheckout}.yaml`(`bundle-vs-loss2.sh` に `apply_normal_except` ヘルパーを追加して対応)。**

## なぜやったか(ユーザ発案)
9/2・9/4 では束ね相手が frontend の近傍(catalog/reco/cart)で、閲覧型に対する需要の伸びがどれも +88〜124% と揃っており、損が1台分しか出なかった。**checkout と email は閲覧型(`GET /product/x`)から呼ばれない**ので、閲覧を積むと最大のズレが作れる。

## 条件
normal + frontemail / frontcheckout / checkoutemail / catalogcheckout × 購入100周/s固定 + 閲覧0/100/200/300 × 3サイクル = 60点(欠測ゼロ)。開始1台・HPA 70%コンテナ別1-8台・warm180/meas240・枠は適正化**等倍**、対象は **frontend 1077 / catalog 662 / checkout 321 / email 119m の4つのみ**(reco・cart はマニフェスト値のまま)。

## 需要のズレ(normal 実測、需要=利用率×台数)
frontend 0.71→**1.77(+149%)** / catalog 0.67→1.49(+122%) / **checkout 0.70→0.90(+29%)** / **email 0.78→0.95(+22%)**。狙いどおり。

## ★★主結果: 損の向きが閲覧比率で反転する
- **閲覧0**(必要台数 fe1/cat1/chk1/**email2**): frontemail **+1077m(3/3)** = email が2台必要で **frontend が1→2台に引きずられた**(frontend コンテナは2台で36%と半分空き)。checkoutemail +321m(3/3)。**catalogcheckout 0m(3/3)**。
- **閲覧300**(必要台数 **fe3**/cat2/chk2/email2): frontcheckout **+321m(3/3)** = checkout が2→3台に。frontemail **+119m(3/3)** = email が2→3台に。**catalogcheckout 0m(3/3)**。
- ⇒ **同じ frontemail の損が 1077m と 119m で9倍違う**。引きずる側と引きずられる側が入れ替わったため。
  **損 =(引きずられた側の枠)×(余分な台数)** が両方向で成立(8/19 の式の双方向検証)。
  枠の大小は損の量を決め、どちらが引きずられるかは需要比率が決める。
- **catalogcheckout は全帯で損ゼロ**(必要台数が常に一致)=「必要台数が一致する相手と束ねよ」の最も直接的な確認。

## ★便益のゼロ対照が取れた
softirq/1万リク(閲覧0): normal 27.60 に対し **frontemail 27.67±0.13 = +0.2%(エッジなし)**、frontcheckout −1.1%、checkoutemail −1.2%、catalogcheckout −1.4%。
**frontend は email を呼ばない**(`src/frontend/main.go` の呼び出し先に無い。email を呼ぶのは checkout)ので削減ゼロ、という予測がばらつきの中で正確に当たった。
ただし削減は −1.1〜−1.4% で、frontcatalog の **−16〜19%**(実験9/4)より1桁小さい。これらのエッジは購入1周に1回しか呼ばれないため。⇒ **便益 = 取り込んだエッジの通信量**の裏付け。

## 使えなかった帯
- **閲覧100**: checkout の需要0.83が1台/2台の境界。normal だけ cyc2/3 で1台に落ち、4アーム全部が一律+321mに見える=**基準側のコイン投げ**。
- **閲覧200**: frontend 需要1.44が2/3台の境界 + 全アームで取りこぼしと遅延跳ね(p50最大999ms)。
- 閲覧300 も取りこぼしあり(normal cyc2 で477件・p50 1660ms)。**予約枠(台数)は3サイクル一致で堅いが、CPU時間の比較は閲覧0/100 に限ること。**

## 実CPU時間
閲覧0/100 では全アーム ±1.5% 以内でサイクル間ばらつきに埋もれる。細いエッジの束ねはCPU時間には出ない。

## 次
**閲覧比率を細かく刻む(0/25/50/75/100)**。frontemail の損が 1077m→119m と反転したので**間に損ゼロの点がある**はず=「この束ねが成立するワークロード比率の境界」。境界のコイン投げを消したいなら枠1/3(9/4の手法)を併用。

関連: [[mixed-workload-experiment]] [[scale-third-experiment]] [[coloc-bundling-decision-rule]] [[rightsizing-experiment]] [[coloc-gain-replica-saving]]
