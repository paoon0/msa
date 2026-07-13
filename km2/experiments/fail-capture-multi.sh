#!/usr/bin/env bash
# fail-capture.sh を N回繰り返し、各回の fails数/エラー種別/下流プローブtimeout件数/rps(枝) を集約。
# 原因(下流プローブtimeout→frontend500)が毎回再現するかを統計的に確認する。
# 出力: km2/experiments/fail-capture-multi.txt (各回サマリ)
set -u
REPO=/home/mizuki/ダウンロード/msa
N=${N:-4}
RUN=${RUN:-3m}
USERS=${USERS:-480}
SUM=$REPO/km2/experiments/fail-capture-multi.txt
LOG=$REPO/km2/experiments/fail-capture.log

echo "================ FAIL-CAPTURE-MULTI START $(date -Is) N=$N users=$USERS ================" | tee "$SUM"
for it in $(seq 1 "$N"); do
  echo "" | tee -a "$SUM"
  echo "########## ITER $it/$N $(date -Is) ##########" | tee -a "$SUM"
  rm -f "$LOG"
  RUN="$RUN" USERS="$USERS" bash "$REPO/km2/experiments/fail-capture.sh" >/dev/null 2>&1

  # 集計抽出
  agg=$(grep -E ',Aggregated,' "$LOG" | head -1)
  fails=$(echo "$agg" | awk -F, '{print $3}')
  rps=$(echo "$agg" | awk -F, '{printf "%.0f",$11}')
  # frontend最大レプリカ(枝の判定)
  frmax=$(grep -oE 'reps=[0-9]+' "$LOG" | grep -oE '[0-9]+' | sort -n | tail -1)
  echo "  fails=${fails:-NA}  rps=${rps:-NA}  frontend最大reps=${frmax:-NA}" | tee -a "$SUM"
  echo "  --- 失敗エラー種別(_failures.csv) ---" | tee -a "$SUM"
  sed -n '/@@@FAIL_BEGIN@@@/,/@@@FAIL_END@@@/p' "$LOG" | grep -vE '@@@|Method,Name' | sed 's/^/    /' | tee -a "$SUM"
  # 下流プローブtimeout件数(サービス別)
  echo "  --- 下流プローブ失敗イベント(件数) ---" | tee -a "$SUM"
  grep -E 'probe failed' "$LOG" | grep -oE '(payment|email|currency|checkout|shipping|ad|cart|recommendation|productcatalog|redis)[a-z-]*' \
    | sort | uniq -c | sed 's/^/    /' | tee -a "$SUM"
  probe_total=$(grep -cE 'probe failed' "$LOG")
  echo "    (プローブ失敗イベント合計=$probe_total)" | tee -a "$SUM"
  # ログ退避(後で個別確認できるよう)
  cp "$LOG" "$REPO/km2/experiments/fail-capture-iter$it.log" 2>/dev/null
done
echo "" | tee -a "$SUM"
echo "================ FAIL-CAPTURE-MULTI DONE $(date -Is) ================" | tee -a "$SUM"
echo "" | tee -a "$SUM"
echo "==== 横断サマリ ====" | tee -a "$SUM"
grep -E 'ITER|fails=' "$SUM" | grep -E 'fails=' | tee -a "$SUM"
