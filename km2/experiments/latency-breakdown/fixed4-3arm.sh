#!/usr/bin/env bash
# ============================================================================
# 【2026-09-09】固定台数(HPA無し)3アーム比較: normal / f3perc(front3) / mega を各4台。
#   枠は 2026-07-14 の固定台数実験と同じ規則 = 全コンテナ requests=150m 一律・limits は据え置き。
#   → 予約はどのアームも 4台 × 10コンテナ × 150m = 6.0コア + redis 300m で完全に一致する
#     (normal=10Deployment / f3perc=8Deployment(frontendPodに3コンテナ) / mega=1Deployment(10コンテナ))。
#   HPA を使わないので「台数の増やし方」の交絡が無く、通信の得(softirq)とアプリCPUだけが残る。
# 出力: fixed4-3arm.csv(1点1行) / fixed-<arm>.log(詳細)
# 実行: bash km2/experiments/latency-breakdown/fixed4-3arm.sh
# ============================================================================
set -u
DIR=/home/mizuki/ダウンロード/msa/km2/experiments/latency-breakdown
CSV=${CSV:-$DIR/fixed4-3arm.csv}
ARMS=${ARMS:-"normal f3perc mega"}
REPLICAS=${REPLICAS:-4}
REQ_M=${REQ_M:-150}
USERS=${USERS:-480}
CYCLES=${CYCLES:-3}
WARM=${WARM:-90}
MEAS=${MEAS:-120}
BASE_W=${BASE_W:-30}
LOG=$DIR/fixed4-3arm-progress.log
echo "======== FIXED4-3ARM START $(date -Is) arms=[$ARMS] reps=$REPLICAS req=${REQ_M}m users=$USERS cycles=$CYCLES ========" | tee -a "$LOG"
for c in $(seq 1 $CYCLES); do
  for arm in $ARMS; do
    echo ">>>> $(date -Is) cyc$c arm=$arm <<<<" | tee -a "$LOG"
    CYC=$c ARM=$arm REPLICAS=$REPLICAS REQ_M=$REQ_M USERS=$USERS WARM=$WARM MEAS=$MEAS BASE_W=$BASE_W \
      SWEEPCSV=$CSV bash $DIR/fixed-replicas.sh 2>&1 | tail -30 | tee -a "$LOG"
  done
done
echo "======== FIXED4-3ARM DONE $(date -Is) ========" | tee -a "$LOG"
