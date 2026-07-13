#!/usr/bin/env bash
# ============================================================================
# 束ねの fails の正体を捕まえる: f3perc+SCALE_ALL をレプリカ1から新規デプロイ→
#   u480 で連続負荷(スケールアップのPod入れ替えを故意に起こす)→
#   locust の _failures.csv(エラーメッセージ) と Pod入れ替えタイムラインを採取・相関。
# 出力: km2/experiments/fail-capture.txt
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
USERS=${USERS:-480}
RATE=${RATE:-40}
RUN=${RUN:-6m}
LOAD=$REPO/km2/experiments/loadgen-csv-fail.yaml
LOADGEN=/tmp/loadgen-failcap.yaml
PC_HPA=$REPO/km2/frontrecocatalogcart/hpa-percontainer.yaml
OUT=$REPO/km2/experiments/fail-capture.txt
ROLLOUT_TIMEOUT=300s
HPA_TARGET=70; HPA_MIN=1; HPA_MAX=4
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
FRONT3_DEPLOYS=(frontend checkoutservice cartservice redis-cart currencyservice paymentservice emailservice shippingservice adservice)
COMMON_SCALE=(checkoutservice cartservice currencyservice paymentservice shippingservice emailservice adservice)

exec > >(tee -a "${OUT%.txt}.log") 2>&1
echo "================ FAIL-CAPTURE START $(date -Is) users=$USERS run=$RUN ================"

# ---- deploy f3perc + SCALE_ALL (レプリカ1から) ----
echo "---- deploy f3perc+SCALE_ALL ----"
kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done
for y in "$REPO"/km2/frontrecocatalogcart/*.yaml; do
  case "$y" in *kustomization.yaml|*loadgenerator.yaml|*hpa-percontainer.yaml) continue;; esac
  kubectl apply -f "$y" -n "$NS" >/dev/null
done
for d in "${FRONT3_DEPLOYS[@]}"; do kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true; done
for d in "${FRONT3_DEPLOYS[@]}"; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done
kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
kubectl apply -f "$PC_HPA" -n "$NS" >/dev/null
for d in "${COMMON_SCALE[@]}"; do kubectl autoscale deploy/"$d" -n "$NS" --cpu-percent="$HPA_TARGET" --min="$HPA_MIN" --max="$HPA_MAX" >/dev/null 2>&1 || true; done
echo "  deploy完了。frontend=1レプリカから開始。"

# ---- 本走を忠実再現: ウォームアップ(スケールアップさせる)→ジョブ削除→アイドル→本計測(ここで失敗採取) ----
# ウォームアップ(3m, 捨て): 束ねをスケールアップさせる
sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"3m\"/; s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$USERS\"/; s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$RATE\"/" "$LOAD" > "$LOADGEN"
kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
kubectl apply -f "$LOADGEN" -n "$NS" >/dev/null
echo "  $(date -Is) ウォームアップ起動(3m, スケールアップ用)"
wpod=""
for i in $(seq 1 60); do
  wpod=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
  kubectl logs "$wpod" -n "$NS" -c main --tail=3 2>/dev/null | grep -q '@@@FAIL_END@@@' && break
  sleep 5
done
echo "  $(date -Is) ウォームアップ完了→ジョブ削除→アイドル30s(本走の基線相当)"
kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
sleep 30
# 本計測($RUN): この窓の失敗を採取(本走で fails が記録されたのはこのフェーズ)
sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$RUN\"/; s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$USERS\"/; s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$RATE\"/" "$LOAD" > "$LOADGEN"
kubectl apply -f "$LOADGEN" -n "$NS" >/dev/null
echo "  $(date -Is) 本計測起動(users=$USERS run=$RUN, この窓で失敗採取)"

# ---- Pod入れ替えタイムライン採取(負荷中, frontend束ねPodの集合変化を検出) ----
echo "==== POD-CHURN TIMELINE (frontend束ねPod) ===="
prev=""
runsec=$RUN; case "$runsec" in *m) runsec=$(( ${runsec%m}*60 ));; *s) runsec=${runsec%s};; esac
end=$(( $(date +%s) + runsec + 40 ))
while [ "$(date +%s)" -lt "$end" ]; do
  cur=$(kubectl get pods -n "$NS" -l app=frontend --no-headers 2>/dev/null | awk '{print $1"("$3")"}' | sort | tr '\n' ' ')
  reps=$(kubectl get deploy frontend -n "$NS" -o jsonpath='{.status.replicas}' 2>/dev/null)
  if [ "$cur" != "$prev" ] && [ -n "$cur" ]; then
    echo "$(date +%H:%M:%S) reps=$reps :: $cur"
    prev="$cur"
  fi
  # loadgen終了(マーカー)で抜ける
  lg=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
  kubectl logs "$lg" -n "$NS" -c main --tail=5 2>/dev/null | grep -q '@@@FAIL_END@@@' && { echo "  (負荷完了検出)"; break; }
  sleep 8
done

# ---- 失敗詳細を回収 ----
echo "==== 失敗/例外の詳細(locust _failures.csv / _exceptions.csv) ===="
lg=$(kubectl get pods -n "$NS" -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
logs=""
for i in $(seq 1 60); do
  logs=$(kubectl logs "$lg" -n "$NS" -c main --tail=-1 2>/dev/null)
  echo "$logs" | grep -q '@@@EXC_END@@@' && break
  sleep 5
done
echo "$logs" | sed -n '/@@@CSV_BEGIN@@@/,/@@@CSV_END@@@/p' | grep -E 'Aggregated|Type,Name' | head -3
echo "--- FAILURES ---"
echo "$logs" | sed -n '/@@@FAIL_BEGIN@@@/,/@@@FAIL_END@@@/p'
echo "--- EXCEPTIONS ---"
echo "$logs" | sed -n '/@@@EXC_BEGIN@@@/,/@@@EXC_END@@@/p'

# ---- 束ねPodの再起動/イベント ----
echo "==== frontend束ねPodのコンテナ再起動/最近のイベント ===="
kubectl get pods -n "$NS" -l app=frontend -o custom-columns=POD:.metadata.name,RESTARTS:.status.containerStatuses[*].restartCount,READY:.status.containerStatuses[*].ready 2>/dev/null
kubectl get events -n "$NS" --sort-by=.lastTimestamp 2>/dev/null | grep -iE 'frontend|Scaled|Killing|Unhealthy|BackOff' | tail -20

kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
kubectl delete hpa --all -n "$NS" >/dev/null 2>&1
echo "================ FAIL-CAPTURE DONE $(date -Is) ================"
