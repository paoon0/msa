---
name: pair-prediction-validation
description: 【2026-10-08 完了・合格】同居ペアの台数・損を分離測定から予測する判定式 (predict_pairs.py) の前向き検証 pairval。事前登録・採点規則・アーム構成
metadata:
  type: project
---

**判定式** `km2/experiments/rightsizing/predict_pairs.py`: results-mix-cpu.csv (分離1台/2台固定) から D_n=c+βb+νv (buy>0 の8点)、枠 r=D1(基準)/θ、HPA 規則 (ratio=u/0.7, 許容±10%, ceil, 同居は max) を開始1台/2台から固定点まで反復。不確かさ = 共通のずれ δ_common (5.9%/8.2%) × 固有 δ_indiv の27通り → 損なし/損あり/不明。

**設計 (ユーザ了承「枠は設定し直してよい」)**: 30案走査で θ=0.50・基準 b50v100 を選択 (FOSE の b100v0 θ0.70 は buy100 で全サービスがしきい値の真上=不明だらけ)。アヌビス判定: 骨組み妥当だが確定セルの6割は全員1台の自明セル、損ありは単純なクラス規則と同じ → 識別セル b100v150 を入れ、単純規則 R1/R2 と比較、主張は「余裕の大きい使い方での検証」に限定。

**本走** 2026-10-08 02:17 開始 (~14時終了)、results/timeline/events-pairval.csv, pairval.log (summer2026/)。normal + pairsX(catalog+reco, checkout+payment, shipping+email) / pairsY(catalog+payment, shipping+reco, front+checkout=新規に数えない) / pairsY2(catalog+email, payment+reco, front+shipping) × b100v0/v100/v150 × 開始1/2 × 3サイクル、点ごとリセット、limits 測定時と同じ。
**事前登録** `rightsizing/prereg-pairval.md` (コミット 7774197, 4b75d30, 51ef2f7)。採点 `score_pairval.py --strict-browse --ready-ignore adservice` (K1 主、K2 副)。合格 = 新規ペア・自明でない確定セルで区分一致 ≥90% かつ識別セルで過半数正解。

**結果 (2026-10-08 13:03 完了、72点、無効セル0で再実行なし)**: 合格。自明でない確定セルの区分一致 30/30 (Wilson 88.6–100%)、3つ組完全一致 31/31・サイクル89/89、識別セル 11/11。対照 R1 64.5%・R2 96.8%。K2 も全問正解。不安定0・得0。★損ありの確定セルは5個だけ (全て b100v0 開始1: catalog+email/payment +742m, front+shipping +1285m, payment/shipping+reco +832m)。★識別セル11のうち R2 と食い違うのは1個だけ=R2 に対する優位は弱い。★bistable 予測も的中: b100v100 で catalog 系ペアは開始1→損あり3/3、開始2→損なし3/3 (同じ負荷で履歴により損が変わる)。不明セルの中心値も概ね的中、外れは front 系 b100v100 開始1 の 1/3 サイクルずつ。途中 (44点時) にユーザ依頼で結果を覗いたことは prereg 追記で開示済み。出力 rightsizing/score-pairval-K{1,2}.txt。

**Why:** 修論の拡張「どのサービスなら配合が変わっても揃うか」の前向き検証。**How to apply:** 結果は採点スクリプトで出し、規則を変えたら変更前の結果も併記。外れの診断は prereg §5。関連 [[rightsizing-formula-accuracy]] [[bundling-three-terms]] [[demand-mismatch-experiment]]
