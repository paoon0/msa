#!/usr/bin/env bash
# k6 開ループ レート掃引: 固定台数(REPLICAS台, HPA無し, request下げて載せる)で
#   到着レート(周/秒)を掃引し、達成iter_rate/dropped/遅延/各サービスCPU を記録。
#   容量の膝 = target に iter_rate が届かなくなる / dropped>0 / p99急上昇 する点。
#   アーム: normal(分離) と bundle(束ね=frontrecocatalogcart)。1周=1checkout。
# 出力: km2/experiments/k6/k6-sweep.csv
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
DIR=$REPO/km2/experiments/k6
ARMS=${ARMS:-"normal bundle"}
RATES=${RATES:-"100 200 300 400 500"}   # 周/秒(=checkouts/s)。offered http rps ≈ ×4
REPLICAS=${REPLICAS:-4}
REQ_M=${REQ_M:-150}
WARM=${WARM:-30}      # 捨てる秒(VU立ち上げ過渡)
MEAS=${MEAS:-180}     # 記録する秒
PRE_VUS=${PRE_VUS:-500}
MAX_VUS=${MAX_VUS:-4000}
CSV=${CSV:-$DIR/k6-sweep.csv}
LOG=${LOG:-$DIR/k6-sweep.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
BUNDLE_SCALE=(frontend checkoutservice cartservice currencyservice paymentservice shippingservice emailservice adservice)

exec > >(tee -a "$LOG") 2>&1
echo "================ K6-SWEEP START $(date -Is) arms=[$ARMS] rates=[$RATES] reps=$REPLICAS warm=${WARM}s meas=${MEAS}s ================"
echo "arm,target_rate,iter_rate,rps,dropped,failed_rate,p50,p90,p99,avg,node_cores,hot" > "$CSV"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 20 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }

deploy(){ local arm=$1
  echo "---- deploy $arm (固定${REPLICAS}台, req=${REQ_M}m, HPA無し) ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete deploy --all -n $NS >/dev/null 2>&1
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  if [ "$arm" = normal ];then
    for f in "${NORMAL[@]}";do kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null;done
    SCALE=("${NORMAL[@]}")
  else
    for y in $REPO/km2/frontrecocatalogcart/*.yaml;do case "$y" in *kustomization*|*loadgenerator*|*hpa-percontainer*)continue;;esac;kubectl apply -f "$y" -n $NS >/dev/null;done
    SCALE=("${BUNDLE_SCALE[@]}")
  fi
  kubectl delete hpa --all -n $NS >/dev/null 2>&1  # 束ね同梱HPAを消す
  for d in "${SCALE[@]}" redis-cart;do kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true;done
  for d in "${SCALE[@]}";do kubectl set resources deploy/$d -n $NS --requests=cpu=${REQ_M}m >/dev/null 2>&1||true;done
  for d in "${SCALE[@]}";do kubectl scale deploy/$d -n $NS --replicas=$REPLICAS >/dev/null 2>&1||true;done
  kubectl scale deploy/redis-cart -n $NS --replicas=1 >/dev/null 2>&1||true
  for d in "${SCALE[@]}" redis-cart;do kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||true;done
  echo "  $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"
}

run_rate(){ local arm=$1 rate=$2
  echo "==== [$arm] target=${rate}周/秒 $(date -Is) ===="
  kubectl create configmap k6-script -n $NS --from-file=checkout.js=$DIR/checkout.js --dry-run=client -o yaml | kubectl apply -f - >/dev/null 2>&1
  kubectl delete job k6load -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  sed -e "s/__RATE__/$rate/" -e "s/__WARM__/$WARM/" -e "s/__MEAS__/$MEAS/" -e "s/__PRE__/$PRE_VUS/" -e "s/__MAX__/$MAX_VUS/" "$DIR/k6-job.yaml" | kubectl apply -f - -n $NS >/dev/null
  local pod=""
  for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l app=k6load --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break; sleep 3;done
  local t_run=$(date +%s)   # pod Running 基準の絶対時刻
  # 計測窓の中盤でCPU採取: WARM + 計測の6割 経過まで待つ
  sleep $(( WARM + MEAS*6/10 ))
  HOT=$(promq "sort_desc( sum by(pod)(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"k6load.*|promq.*\"}[45s])) / on(pod) group_left sum by(pod)(kube_pod_container_resource_requests{namespace=\"$NS\",resource=\"cpu\"}) )" \
    | python3 -c "import sys,json,re;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(';'.join('%s=%.0f%%'%(re.sub(r'-[a-f0-9]{6,}.*\$','',x['metric'].get('pod','?')),float(x['value'][1])*100) for x in r[:5]))" 2>/dev/null)
  NODE=$(promq "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[45s]))" | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(round(float(r[0]['value'][1]),1) if r else 'NA')" 2>/dev/null)
  # k6は t_run+WARM+MEAS で計測完了。その時刻+20s まで確実に待ってから、ログを一度だけ読む(ポーリング競合を排除)。
  local done_at=$(( t_run + WARM + MEAS + 20 ))
  while [ "$(date +%s)" -lt "$done_at" ]; do sleep 5; done
  local logs; logs=$(kubectl logs "$pod" -n $NS 2>/dev/null)
  local summary; summary=$(printf '%s\n' "$logs" | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
  echo "$summary" | grep -q '{' || { echo "  !! summary回収失敗(pod=$pod)"; kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1; return; }
  echo "$summary" | python3 - "$arm" "$CSV" "$NODE" "$HOT" <<'PY'
import sys,json,csv
arm,out,node,hot=sys.argv[1:5]
d=json.load(sys.stdin)
row=[arm,d.get('target_rate'),round(d.get('iter_rate') or 0,1),round(d.get('rps') or 0,1),
     d.get('dropped'),round(d.get('failed_rate') or 0,4),
     round(d.get('p50') or 0,1),round(d.get('p90') or 0,1),round(d.get('p99') or 0,1),round(d.get('avg') or 0,1),node,hot]
with open(out,'a',newline='') as f: csv.writer(f).writerow(row)
print("  -> iter_rate=%s/%s dropped=%s p50=%.0f p99=%.0f failed=%.3f node=%s"%(round(d.get('iter_rate') or 0),d.get('target_rate'),d.get('dropped'),d.get('p50') or 0,d.get('p99') or 0,d.get('failed_rate') or 0,node))
print("     hot=[%s]"%hot)
PY
  kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
}

ensure_promq
for arm in $ARMS; do
  deploy "$arm"; sleep 10
  for r in $RATES; do run_rate "$arm" "$r"; done
done
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ K6-SWEEP DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null | cut -c1-140
