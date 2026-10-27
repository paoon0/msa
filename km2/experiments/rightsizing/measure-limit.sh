#!/usr/bin/env bash
# OB の限界 (購入だけ・閲覧だけ) を測る (2026-10-19)。配合を「限界に対する割合」で決めるための基準。
#
# 限界の定義 (2026-10-19 ユーザ決定): 取りこぼし (k6 が予定どおり始められなかった周、計測窓) が 目標×計測秒 の 1% 以下に
#   収まる、いちばん高い負荷。ρ の解析の除外ルール (取りこぼし 1% 超は除外) と同じ基準。
#   1 段ずつ上げ、1% を超えたらそのラダーを打ち切る (限界 = その 1 つ手前の段)。応答時間 (p99) は記録だけする。
#
# 設定は ρ の測定 (mix-cpu2) と同じ: 1 台固定・HPA 無し・limits 上書き (frontend/catalog 3000m, ad 1000m)・gRPC 振り分け・
#   冷却待ち 70℃ (最長 600 s)・各点の後 60 s 休み・慣らし b100 を 180 s。違いは計測が 120 s (mix-cpu2 は 180 s)。
# 1 サイクル = 購入ラダーと閲覧ラダー。ラダーごとに立て直す (前のラダーの過負荷を持ち越さない)。どちらを先にするかはサイクルで交互。
# k6 自身の CPU は CSV の k6load 行に残る (上限 2000m。張り付いていたらその段は k6 律速で無効)。
#
# 2 段階で使う:
#   粗 (既定): 1 サイクル、大きい刻みで限界のありかを探す
#     bash /home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/measure-limit.sh
#   細: 粗の結果の周りを細かい刻みで 3 サイクル (中央値を限界とする)
#     STAGE=fine CYCLES=3 BUY_STEPS="b150 b160 ..." VIEW_STEPS="v500 v525 ..." bash .../measure-limit.sh
# 解析: python3 analyze_limit.py results-limit-coarse.csv
set -u
DIR=/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing
STAGE=${STAGE:-coarse}
NC=${CYCLES:-1}                   # 外側のサイクル数 (内側の measure-mix-cpu.sh は 1 回 1 サイクル)
BUY_STEPS=${BUY_STEPS:-"b100 b125 b150 b175 b200 b250 b300"}
VIEW_STEPS=${VIEW_STEPS:-"v300 v400 v500 v600 v800 v1000"}
CSV=${CSV:-$DIR/results-limit-$STAGE.csv}
export REPLICAS=1 CYCLES=1 ORDER=asc STOP_DROP_PCT=${STOP_DROP_PCT:-1} WARM=${WARM:-60} MEAS=${MEAS:-120} \
       COOL_TEMP=${COOL_TEMP:-70} COOL_MAX_WAIT=${COOL_MAX_WAIT:-600} REST_POINT=${REST_POINT:-60} \
       PREWARM=${PREWARM:-180} PREWARM_POINT=${PREWARM_POINT:-b100} CSV
echo "==== MEASURE-LIMIT START $(date -Is) stage=$STAGE cycles=$NC buy=[$BUY_STEPS] view=[$VIEW_STEPS] stop>${STOP_DROP_PCT}% csv=$CSV ====" | tee -a "${CSV%.csv}.log"
for c in $(seq 1 $NC); do
  if [ $(( c % 2 )) = 1 ]; then ladders="buy view"; else ladders="view buy"; fi
  for l in $ladders; do
    if [ $l = buy ]; then pts=$BUY_STEPS; else pts=$VIEW_STEPS; fi
    echo "---- cycle $c ladder $l [$pts] $(date -Is)" | tee -a "${CSV%.csv}.log"
    CYCLE_START=$c POINTS="$pts" bash $DIR/measure-mix-cpu.sh
  done
done
echo "==== MEASURE-LIMIT DONE $(date -Is) ====" | tee -a "${CSV%.csv}.log"
