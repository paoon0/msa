#!/usr/bin/env bash
# fixed-replicas.sh を レプリカ数 4,3,2,1 × arm(normal,f3perc) で回し、u480の
# 「固定台数 → rps/latency」曲線を取る(HPA無し=閉ループ交絡なし)。request=150m固定で載せる。
# 出力: km2/experiments/latency-breakdown/replica-count-sweep.csv
set -u
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments/latency-breakdown
CSV=$DIR/replica-count-sweep.csv
ARMS=${ARMS:-"normal f3perc"}
REPS=${REPS:-"4 3 2 1"}
USERS=${USERS:-480}
REQ_M=${REQ_M:-150}
WARM=${WARM:-90}
MEAS=${MEAS:-120}
rm -f "$CSV"
echo "================ REPLICA-COUNT-SWEEP START $(date -Is) arms=[$ARMS] reps=[$REPS] u=$USERS ================" | tee "$DIR/replica-count-sweep-progress.log"
for arm in $ARMS; do
  for r in $REPS; do
    echo ">>>> $(date -Is) arm=$arm replicas=$r <<<<" | tee -a "$DIR/replica-count-sweep-progress.log"
    ARM=$arm REPLICAS=$r REQ_M=$REQ_M USERS=$USERS WARM=$WARM MEAS=$MEAS SWEEPCSV=$CSV \
      bash "$DIR/fixed-replicas.sh" >/dev/null 2>&1
    tail -1 "$CSV" 2>/dev/null | tee -a "$DIR/replica-count-sweep-progress.log"
  done
done
echo "================ DONE $(date -Is) ================" | tee -a "$DIR/replica-count-sweep-progress.log"
column -s, -t "$CSV" 2>/dev/null | tee -a "$DIR/replica-count-sweep-progress.log"
