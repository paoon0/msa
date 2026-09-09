#!/usr/bin/env bash
# 【夏休み実験B】崩壊の原因が「CPU上限(limits)による強制停止=スロットリング」かを因果で確定する。
#
# 背景(2026-08-20):
#   250-300周/s で崩壊が頻発するが、そのとき全コンテナの利用率は 55-70% で HPA は1台も増やさない。
#   犯人候補として email の 48% スロットリングを観測した。だが「相関」でしかない。
#
# この実験のやり方(対照実験):
#   同じアーム・同じ負荷で、CPU上限だけを2通りに変えて比べる。
#     lx=0  … マニフェストのまま(email 上限300m)= 前回崩壊した条件(対照)
#     lx=10 … 上限 = 枠(requests) × 10 (email 1190m) = 実質「絞りなし」
#   ★ 崩壊が lx=10 で消えれば「上限による強制停止が原因」と確定する。
#   ※ 「×3」では因果テストにならない: email は 300→357m(+19%)にしかならず、
#      逆に adservice は 300→207m と きつく なってしまう。だから大きい倍率を使う。
#
# 交互に回す理由: 崩壊は回ごとにばらつく(同じ構成が崩壊したりしなかったりする)ので、
#   条件をまとめて連続実行するとマシンの状態変化(ドリフト)と条件の効果が混ざる。
#   1サイクルごとに lx=0 と lx=10 を交互に実行して、時間の影響を両条件に等しく散らす。
set -u
DIR=/home/mizuki/ダウンロード/msa/km2/experiments/summer2026
ARM=${ARM:-frontcatalog}
RATES=${RATES:-"250 300"}
CYCLES=${CYCLES:-3}
LIMS=${LIMS:-"0 10"}
CSV=$DIR/results-expB-limits.csv
TL=$DIR/timeline-expB-limits.csv
EV=$DIR/events-expB-limits.csv
LOG=$DIR/expB-limits.log

for c in $(seq 1 $CYCLES); do
  for lx in $LIMS; do
    ARMS="$ARM" RATES="$RATES" CYCLES=1 CYC_START=$c RIGHTSIZE=1 LIMIT_X=$lx \
    CSV=$CSV TL=$TL EV=$EV LOG=$LOG \
    bash $DIR/bundle-vs-loss2.sh
  done
done
echo "================ 実験B 完了 $(date -Is) ================" | tee -a "$LOG"
