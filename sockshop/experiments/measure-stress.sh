#!/usr/bin/env bash
# Sock Shop: どれくらいの負荷に耐えるかを、前回の ρ 測定の最大 (b24v120) より強い負荷で素朴に確かめる (2026-10-20 ユーザ決定)。
#   「限界に対する割合で配合を決める」話はなかったことにした (km2/approach/related_work.md §9.8)。ここでの結果は、ρ の格子の最大を決める材料。
#
# 3 本のラダー (下の段から 1 段ずつ上げる): 購入だけ / 閲覧だけ / 混合 (前回の最大 b24v120 と同じ 閲覧÷購入 = 5 の向きに強める)。
#   取りこぼし (計測窓) が 目標×計測秒 の 1% を超えたら、そのラダーを打ち切る。p99・各サービスの CPU・絞り・k6 の CPU も記録。
# 設定は ρ の測り直しと同じ: 1 台固定・HPA 無し・上限 2000m・接続の張り直し (B′)・冷却待ち 70℃ (最長 600 s)・各点の後 60 s 休み・
#   慣らし b20v100 を 300 s (利用者の登録もここで 1 回)。1 点 = ウォームアップ 60 s + 計測 120 s。ラダーごとに立て直す。
# 段の目安: front-end (Node、1 コアで頭打ち) は前回の当てはめから b60 ≈ 0.86 コア、v300 ≈ 1.05 コア、b30v150 ≈ 0.95 コア (B′ の +9% 込み)。
#
#   bash /home/mizuki/ダウンロード/msa/sockshop/experiments/measure-stress.sh                     # 1 サイクル
#   CYCLES=2 CYCLE_FROM=2 bash .../measure-stress.sh                                               # 続きの 2〜3 サイクル (同じ CSV に追記)
# 解析: python3 /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/analyze_limit.py results-stress.csv 120   (購入だけ・閲覧だけの表)
#       混合ラダーは CSV の point 列 (b26v130 …) で見る
set -u
DIR=/home/mizuki/ダウンロード/msa/sockshop/experiments
NC=${CYCLES:-1}                   # 外側のサイクル数 (内側の measure-mix-cpu.sh は 1 回 1 サイクル)
CYCLE_FROM=${CYCLE_FROM:-1}       # サイクル番号の始まり (続きを足すとき。2026-10-20 に 1 → 2〜3 を追加)
BUY_STEPS=${BUY_STEPS:-"b40 b50 b60 b70 b80 b90 b100"}
VIEW_STEPS=${VIEW_STEPS:-"v150 v200 v250 v300 v350 v400"}
MIX_STEPS=${MIX_STEPS:-"b26v130 b28v140 b30v150 b32v160 b36v180 b40v200"}
CSV=${CSV:-$DIR/results-stress.csv}
export REPLICAS=1 CYCLES=1 ORDER=asc STOP_DROP_PCT=${STOP_DROP_PCT:-1} WARM=${WARM:-60} MEAS=${MEAS:-120} \
       COOL_TEMP=${COOL_TEMP:-70} COOL_MAX_WAIT=${COOL_MAX_WAIT:-600} REST_POINT=${REST_POINT:-60} \
       PREWARM=${PREWARM:-300} PREWARM_POINT=${PREWARM_POINT:-b20v100} CSV
echo "==== SS-STRESS START $(date -Is) cycles=$NC from=$CYCLE_FROM buy=[$BUY_STEPS] view=[$VIEW_STEPS] mix=[$MIX_STEPS] stop>${STOP_DROP_PCT}% csv=$CSV ====" | tee -a "${CSV%.csv}.log"
for c in $(seq $CYCLE_FROM $(( CYCLE_FROM + NC - 1 ))); do
  if [ $(( c % 2 )) = 1 ]; then ladders="buy view mix"; else ladders="mix view buy"; fi
  for l in $ladders; do
    case $l in buy) pts=$BUY_STEPS;; view) pts=$VIEW_STEPS;; mix) pts=$MIX_STEPS;; esac
    echo "---- cycle $c ladder $l [$pts] $(date -Is)" | tee -a "${CSV%.csv}.log"
    CYCLE_START=$c POINTS="$pts" bash $DIR/measure-mix-cpu.sh
  done
done
echo "==== SS-STRESS DONE $(date -Is) ====" | tee -a "${CSV%.csv}.log"
