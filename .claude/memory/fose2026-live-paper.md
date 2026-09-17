---
name: fose2026-live-paper
description: 【提出済 2026-09-14】FOSE2026ライブ論文。スナップショット submitted-20260914/、数値の出所と再計算スクリプトは fose2026-data-provenance.md。全数値を再計算で一致確認済(§5の5–9%/28–48%は前セッションのawkをPython移植)。カメラレディ 9/25 17:00
metadata: 
  node_type: memory
  type: project
  originSessionId: 2ed618a3-3070-43c7-841c-86ff649e1e9a
  modified: 2026-09-17T16:05:26.562Z
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

関連: [[softirq-cpu-metric]] [[icter-affinity-replication]] [[edge-traffic-measurement]] [[mixed-workload-experiment]] [[demand-mismatch-experiment]] [[fixed-replica-k6]] [[verify-numbers-python]] [[readiness-probe-blind-spot]]
