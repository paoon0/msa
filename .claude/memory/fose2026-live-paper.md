---
name: fose2026-live-paper
description: 【提出済 2026-09-14／カメラレディ作業中 9/25】FOSE2026ライブ論文。数値の出所は fose2026-data-provenance.md。カメラレディ チェックリストの確認結果とTeX環境の落とし穴(jssst.bstはurl無視/2段組にURLは\linebreak必須/popplerは和文CIDを列挙しない)を後半に記録
metadata: 
  node_type: memory
  type: project
  originSessionId: 2ed618a3-3070-43c7-841c-86ff649e1e9a
  modified: 2026-09-24T18:28:59.044Z
---

**2026-09-14 に EasyChair (conf=fose2026) へ提出済み。** 採否 9/18、カメラレディ 9/25 17:00。CFP: https://fose.jssst.or.jp/fose2026/cfp.html

## 提出版
- スナップショット `FOSE2026-TeX-UTF8/submitted-20260914/{tex,bib,pdf}` (MD5 は provenance §1)。以降の編集はカメラレディ向けで、差分はこれと比較する
- 2ページ、太字なし、題「Kubernetes HPA 環境下におけるコンテナ同居の効果と選択条件」/ "Effects and Selection Conditions of Container Colocation under Kubernetes HPA"、著者 田尾瑞紀 + 満田成紀 (和歌山大学戦略情報室 / IR Office)
- 構成: 抄録 → §1 はじめに → §2 同居とオートスケーラの干渉 (予約枠・必要台数・N=max を「定義」として置き、括弧で本稿のHPAはコンテナ別利用率なので実際にも一致と注記) → §3 実験環境 (localhost 実装、softirq を使う根拠 = 単一ノードでは affinity が +2–4% で変わらない) → §3.1 予備実験 (台数4固定) → §4 本実験 (HPA設定、適正化、表1) → §5 考察 (2段落、主張文で始める) → 今後の課題
- ビルド: `FOSE2026-TeX-UTF8/` で `platex; pbibtex; platex; platex; dvipdfmx` (latexmk 無し)

## 数値の出所 (すべて `FOSE2026-TeX-UTF8/fose2026-data-provenance.md` に記録)
- 再計算で**一致**: 表1 (`summer2026/table1_mismatch.py`)、§3.1 softirq −17〜23%/−43〜51%・buy(450) 359.6±22.9 vs 約440 (`fixed4_summary.py`)、§3 affinity +2.0/+4.2% (`icter_affinity_summary.py`)、§5 affinity 割合 38.8/4.8/4.1/2.5/1.7% (`edge_pair_shares.py`)
- §5「一定3組 5–9% / 反転3組 28–48%」: 元は 2026-09-13 20:27 の awk ワンライナー (セッション 8798bd8a の jsonl 行 3211 にのみ残存) → `summer2026/requests_shift_search.py` に移植し**一致** (9/8/5, 28/48/47%)。方法 = 需要(利用率×台数, 全区間平均) を両サービスの枠 kA,kB 倍 (0.20–4.00, 0.01刻み) で ceil(D/k/0.77) が全20点で一致する最小 max|k−1|。片側のみ・θ0.70 だと値が変わる (1–11% / 37–39%) ので開示時は条件を添える
- **★不整合 (9/18 判明)**: その awk は需要の平均に**ウォームアップ中 (0–180 s) も含めて**いた = 本文「180 秒のウォームアップ後 240 秒を計測」と食い違う。計測窓のみ (`--window`) だと **一定組 7–11% / 反転組 19–42%** (frontend+checkout 48%→19%)。結論は不変、数値は変わる。**カメラレディで差し替えるかは未決 (ユーザ判断待ち)**。原因 = 締切前日に使い捨て awk をゼロから書き既存の窓の慣例を流用せず、仮説どおりの結果だったので検算を省いた (指示側の問題ではない)
- ★教訓: 論文に書く数値の計算は必ずリポジトリ内のスクリプトとして保存し、需要などの共通計算は既存関数を再利用する (awk ワンライナーはセッション記録からしか復元できなかった)
- 複数サブエージェントによる第三者査読 (K8s技術/実験方法論/論理構成の3役割) は提案済み、9/18 時点で見送り (ユーザ判断)。必要時は現行 tex だけを渡して実行
- 前セッション (8798bd8a) 自身に未保存の計算・判断を書き出させた → `fose2026-draft.md`「前セッションの未保存の計算・判断」(A 本文に効く 8 件 / B 旧版 7 件 / C 判断)。検証して provenance に統合済 (fixed4 は warm90/meas120 で §4 の 180/240 とは別・本文未記載 / 飽和帯は cycle1-6 に統一 / 6組の選び方 = 7組から catalog+checkout を除外、除外組は 4/20 反転あり / 探索方法の変遷 = 片側→両側無制限→±20%撤回→最小ずらし)
- 表1の定義 = 分離配置 (normal) での HPA 到達台数の比較 (n(左)<n(右) が `n<`、同居アームの測定がある点だけ数える → frontcart は 19点)。`cyc5_summary.py` の帰属方式粒度損とは別物

## 査読対応の記録
- 執筆メモ `FOSE2026-TeX-UTF8/fose2026-draft.md` の「訂正確認場所」に指摘 120 件。対応済み 41 件はセクション末尾に列挙 (最優先 5 件すべて含む)、一部対応は 14 (requests↔n(s) の関係) と 84 (割合の定義文は行数都合で削除)
- 未対応の「高」: 総当たり探索の方法と解の定義 / 表1の 19/20 の理由 / 6組を選んだ理由

## 2ページに収める作業の教訓
- あふれ量は `\typeout{\the\pagetotal}` を `\end{document}` 直前に置いた probe をビルドして測る (pdftotext の行数は日本語行を落とすので不可)
- **1ページ目で行を削っても効かない** (節見出し前後の伸縮余白が吸収)。2ページ目の本文 (表より後) を削るしか効かない
- 参考文献 [1] の GitHub パスは `\linebreak` 付きが最短。短くしても 3 行のまま

## 作業上の注意
- 指示された箇所以外を勝手に書き換えない。まず提案して判断を仰ぐ (ユーザ指示 2026-09-10、09-14 にも「変更を急に加えすぎないで」)
- このシェル (Bash ツール) は `\\` を `\` に潰す。TeX や正規表現のバックスラッシュを含む sed/perl/heredoc は壊れるので、Write ツールでスクリプトを書いてから実行する
- Python は `py -3`、日本語出力は `PYTHONIOENCODING=utf-8`

## カメラレディ チェックリスト対応 (2026-09-25)
- **済**: 和文あらまし (`\Jabstract` のみ = 和文論文では正) / 著者・所属 (`\shozoku` 3引数 = 英文氏名・和文所属・英文所属。`Graduate School of Systems Engineering` は複数形 Systems が正で大学ポートレート JPCUP と一致、`IR Office` は**満田先生に確認済み**) / 句読点 (．45 ，58、。、は0件、和文隣接の半角 . , も0件) / 図は**1枚も無い** (`\includegraphics` 0件・画像XObject 0 なので300dpi要件は該当なし。`image/sampleFig.png` は sample.tex 専用で未使用) / フォント埋め込み (17書体すべて FontFile あり) / BibTeX 使用 (upBibTeX + jssst.bst) / 文献の並び順 (yomi で自動ソート、google→wickramanayaka で著者アルファベット順)
- **変更した箇所**: ①`\ejtitle` の `\\` を削除 (左下英文タイトルが3行→2行) ②本文の半角括弧を**全角（）に統一** (24箇所。数式・`buy()`/`view()` の記法・`式(\ref{})`・コメントは半角のまま) ③文献[1]に**タグURL** `.../releases/tag/v0.10.3` を追加 (参照日は**書かない** = タグは不変なので意味が無い、というユーザ判断) ④`.bib` の引用キー `Wickramanayaka20223345` → `wickramanayaka2022` に戻した (本文4箇所の `\cite` と不一致で全部 `[?]` になる寸前だった) ⑤URLの `\texttt` を外し本文書体に
- **未了**: 37行目 `Docker環境で` / 40行目 `であるHPA` / 137行目 `affinityの順に` の和欧間スペース (他82箇所は空けているので不統一。中黒隣接の22箇所は約物なので正しい)
- zip 同梱リスト = `fose2026.tex` `fose2026.bib` `fose2026.bbl` `fose.cls` `fose.sty` `jssst.bst` + PDF (+任意で `.latexmkrc`)。`newsletr.sty` は `\def\ds@newsletr` 内なので**不要**。`sample.*` `compsoft-guide.pdf` `image/` は除外

## TeX 環境の落とし穴 (このリポジトリ固有・再利用可)
- **`jssst.bst` の ENTRY に `url` も `doi` も無い** → `.bib` に書いても**警告なしで捨てられる**。URL/DOI は `howpublished` か `note` に文字列で入れる (`@misc` の出力順 = 著者: タイトル, howpublished, 年. note.)
- **2段組(段幅7.5cm)に GitHub のURLは入らない**。`\url{}`・`\urlstyle{rm}`・`\UrlBreaks`拡張・`\sloppy`・`\allowbreak` は**全部 Overfull**(22–57pt)。唯一成立するのは `.bib` 内で手動 `\linebreak` を置く方法。書体は `\texttt` を外すと同じURLが約1.2cm短くなる。Underfull(行が緩む)は残るが Overfull(枠外)を避ける必然の代償で対処不要
- **`pdffonts`(poppler) は和文CIDフォントを列挙しない** (`Unknown character collection 'Adobe-Japan1'` で欧文15個しか出ない)。埋め込み検証は `dvipdfmx -v` の `[CIDFontType0]` 行か、PDFのストリームを zlib 展開して `/BaseFont` と `/FontFile*` を対応させる自作スクリプト。同じ理由で `pdftotext`/`pdftoppm` も和文を出せないので**日本語の見た目は目視できない** → 改行位置の変化はDVIのバイト比較で確認する
- `compsoft-guide.pdf` (学会の様式解説書) は**パスワード保護**で Read ツールから開けない。様式の一次情報が必要なときはユーザに開いてもらう
- Online Boutique のバージョン確認法 = `helm-chart/Chart.yaml` の `appVersion: "v0.10.3"` (最も確実) / `release/kubernetes-manifests.yaml` の image タグ / `km2/normal/*.yaml` の image タグ。`git tag` は空で remote は `paoon0/msa` (upstream を1コミットで取り込んだ形) なので**git からは辿れない**。★km2/normal は checkoutservice だけ `mizuki0118/mygo:bunpupaymail`、loadgenerator は `mylocust:run1` = 10サービス中2つは upstream でない → 本文§3「アプリケーションの変更はない」と整合するか**未確認** (`src/checkoutservice` に first commit 後3コミットあり)

関連: [[softirq-cpu-metric]] [[icter-affinity-replication]] [[edge-traffic-measurement]] [[mixed-workload-experiment]] [[demand-mismatch-experiment]] [[fixed-replica-k6]] [[verify-numbers-python]] [[readiness-probe-blind-spot]]
