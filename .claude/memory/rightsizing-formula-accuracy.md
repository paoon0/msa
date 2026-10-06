---
name: rightsizing-formula-accuracy
description: 【2026-10-06 診断】FOSE式 枠=(c0+100c1)/0.7 の誤差の内訳。設計点で cart/email が+10〜15%ズレて77%線を越え毎回2台=表1のview0列の「<」の原因。view項が無いのが最大誤差(+80%)
metadata:
  node_type: memory
  type: project
  originSessionId: f19a71cf-0131-4423-8285-543cfa375857
  modified: 2026-10-05T16:08:23.766Z
---

ユーザ依頼「FOSEの枠適正化の式の精度を上げたい」で診断した結果 (2026-10-06)。検証データ = mix/mix2 の normal アーム (計測窓のみ、10サイクル) + loadsweep(150/200) + rightsized。スクリプトは scratchpad に置いただけでリポジトリには未保存。

- **購入負荷だけなら CPU 予測誤差は主要サービスで 3〜10%** (RMS)。小さく見えるが、HPA の増設線は 77% (70%×許容幅1.1) なので余裕は +10% しかない。
- **設計点 buy100/view0 での1台時利用率** (目標70%): frontend 68–75 / reco 64–70 / checkout 69–78 (線上でコイン投げ, 1/5で2台) / **cart 73–83, email 79–83 → 5/5で2台**。いったん2台になると D(2)=D(1)+c0/r>0.70 なので1台に戻らない (ヒステリシス)。
- ⇒ **表1 の view0 列 (frontend+cart 5<、frontend+email 5<、checkout+email 4<) は需要の伸び方ではなく枠の測定誤差が作った引きずり**。§4 の「一定組は7–11%ずらせば解」もほぼこの誤差の大きさ。
- 誤差の原因: 元データ (perservice-cpu) は1サイクル・6点だけで、カーブが低負荷で凹 (10→30周/sで急増) なので直線の切片 c0 が過大・傾き c1 が過小 (email: c0 16→再推定≈0, c1 0.67→0.95)。HPA 実験からは n と負荷が共線で c0 を分離できない (catalog が負になる)。fixed4 には利用率列が無い。
- **最大の誤差は view 項の欠落** (view300 で +60〜80%)。既存 mix データから推定した c1_view [m/周]: frontend 3.0, catalog 1.9, reco 1.5, currency 0.9, cart 0.6, ad 0.4, checkout 0.16, email 0.05, payment 0.03。

**How to apply:** 改良案は (1) 設計点で直接測る較正ループ r←r×u実測/0.70、(2) c0 は固定台数 n=1,2,4 で分離、(3) view 項を入れて単体測定だけから組の反転を予測し表1と答え合わせ。§4 の主張に響くので論文の数値と照合してから使う。関連 [[rightsizing-experiment]] [[fose2026-live-paper]] [[mixed-workload-experiment]]

**2026-10-06 ユーザ合意で第2版の手順を採用** (Online Boutique と Sock Shop で同じ手順にする): 手順書 `km2/approach/rightsizing-procedure.md`、スクリプト `km2/experiments/rightsizing/` (measure-class-cpu.sh / rightsize2.py / calibrate.py)。要点 = クラス別に1つずつ測る・設計点周辺に点を集め3サイクル・c0は台数差・**検証(1台時利用率66〜74%)と較正のステップを手順に入れる**。未測定。旧 perservice-cpu.sh は再編後のパス切れで動かない。

**★2026-10-06 レフェリー判定で訂正 (自分でも検算済み):**
- cart の「+10%・73–83%」は**誤り**。2台化直後の過渡が窓に混ざった値。mix2 (旧枠560m) で cart は終始1台・256–263m → 361m 換算で u1≈72%、予測誤差 +2.6%。設計点の誤差は frontend +2.1 / catalog −4.4 / reco −4.3 / checkout +0.8 / cart +2.6 / **email +11.6% (u1 78%) だけが大きい**。
- 実測 c0 はほぼゼロ (email ≈0.4m, cart ≈5m) → 「c0 のせいで戻らない」も誤り。戻らない理由は HPA の非対称 (77%超で増、減らすには合計需要 ≤70%)。u1<70 の catalog/reco は一時2台→戻った、u1>70 の cart/checkout は残った。2台化は全てウォームアップ中 (t=61–152s、1台時の瞬間最大 93–148%)。
- ⇒ 表1 view0 列の「<」は view の需要差では説明できない、までは言える。原因は email=枠の過小推定、cart/checkout=起動直後の跳ね上がり+HPA の非対称による履歴依存。
- **FOSE §3.2 の記述誤り**: bundle-vs-loss2.sh はアームごとに1回だけデプロイし view 0→100→200→300 を台数リセット無しで連続測定 (view100 の t=0 で cart/email は全サイクル2台)。「各点は1台から開始」は view0 のみ。修論で直す。
- provenance §3.3 の「cart 560m」は誤り (使用値は 361m)。
- view 項の欠落は「枠の誤差」ではなく、単体測定から台数を予測するのに要る項と位置づける。
