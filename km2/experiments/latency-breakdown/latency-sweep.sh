#!/usr/bin/env bash
# ============================================================================
# normal(分離)の "300ms" はどこで消えるか = 通信(構造・負荷非依存) vs 待ち行列(負荷依存) を分離。
# 負荷を極低(1)→飽和(480)に振り、各点で:
#   (A) locust リクエスト種別ごと(/, /product, /cart, /cart/checkout)の p50/p99
#   (B) checkout の下流ホップ別レイテンシ(grpc_client_latency, destination別 p50/p99)
#   (C) 各サービスの CPU使用率(usage/request) = どこが飽和して待ち行列を作るか
# 判定: 1ユーザでも高い→構造/通信。低負荷では低く負荷で膨らむ→待ち行列。
# 出力: km2/experiments/latency-breakdown/latency-sweep.csv
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
ARMS=${ARMS:-"normal"}
LOADS=${LOADS:-"1 10 40 120 240 480"}
RATE=${RATE:-40}
WARM=${WARM:-30}          # ウォームアップ秒
MEAS=${MEAS:-90}          # 本計測秒
HPA_TARGET=70; HPA_MIN=1; HPA_MAX=4
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-latsweep.yaml
PC_HPA=$REPO/km2/frontrecocatalogcart/hpa-percontainer.yaml
CSV=${CSV:-$REPO/km2/experiments/latency-breakdown/latency-sweep.csv}
LOG=${LOG:-$REPO/km2/experiments/latency-breakdown/latency-sweep.log}
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
FRONT3=(frontend checkoutservice cartservice redis-cart currencyservice paymentservice emailservice shippingservice adservice)
COMMON=(checkoutservice cartservice currencyservice paymentservice shippingservice emailservice adservice)

exec > >(tee -a "$LOG") 2>&1
echo "================ LATENCY-SWEEP START $(date -Is) arms=[$ARMS] loads=[$LOADS] ================"
echo "arm,users,rps,fails,agg_p50,agg_p90,agg_p99,product_p50,cart_p50,checkout_p50,checkout_p99,hop_p50,hop_p99,hot_services" > "$CSV"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 20 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ] && { echo "$out"; return; }; sleep 4; done; echo ""; }

deploy(){ local arm=$1
  echo "---- deploy $arm ----"
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  kubectl delete -f $REPO/km2/all/all.yaml -n $NS --ignore-not-found >/dev/null 2>&1
  for f in "${NORMAL[@]}";do kubectl delete -f $REPO/km2/normal/$f.yaml -n $NS --ignore-not-found >/dev/null 2>&1;done
  for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
  if [ "$arm" = normal ];then
    for f in "${NORMAL[@]}";do kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null;done
    local ds=("${NORMAL[@]}" redis-cart); local scale=("${NORMAL[@]}")
  else
    for y in $REPO/km2/frontrecocatalogcart/*.yaml;do case "$y" in *kustomization*|*loadgenerator*|*hpa-percontainer*)continue;;esac;kubectl apply -f "$y" -n $NS >/dev/null;done
    local ds=("${FRONT3[@]}"); local scale=(frontend "${COMMON[@]}")
  fi
  for d in "${ds[@]}";do kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true;done
  for d in "${ds[@]}";do kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||true;done
  kubectl delete hpa --all -n $NS >/dev/null 2>&1
  if [ "$arm" = f3perc ];then kubectl apply -f $PC_HPA -n $NS >/dev/null; for d in "${COMMON[@]}";do kubectl autoscale deploy/$d -n $NS --cpu-percent=$HPA_TARGET --min=$HPA_MIN --max=$HPA_MAX >/dev/null 2>&1||true;done
  else for d in "${scale[@]}";do kubectl autoscale deploy/$d -n $NS --cpu-percent=$HPA_TARGET --min=$HPA_MIN --max=$HPA_MAX >/dev/null 2>&1||true;done; fi
}

run_point(){ local arm=$1 u=$2
  echo "======== [$arm] users=$u $(date -Is) ========"
  sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$((WARM+MEAS+30))s\"/; s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$u\"/; s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$RATE\"/" "$LOAD" > "$LOADGEN"
  kubectl delete job loadgenerator -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
  for i in $(seq 1 20);do [ -z "$(kubectl get pods -n $NS -l job-name=loadgenerator -o name 2>/dev/null)" ]&&break;sleep 2;done
  kubectl apply -f "$LOADGEN" -n $NS >/dev/null
  local pod=""; for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
    [ -n "$pod" ]&&[ -n "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.containerStatuses[?(@.name=="main")].state.running.startedAt}' 2>/dev/null)" ]&&break; sleep 3;done
  sleep $WARM   # ウォームアップ捨て
  local t0=$(date +%s)
  sleep $MEAS   # 本計測窓
  local wm="${MEAS}s"
  # (B) checkout ホップ別 p50/p99
  local hop50=$(promq "histogram_quantile(0.5, sum by(le,destination)(rate(grpc_client_latency_seconds_bucket{namespace=\"$NS\"}[${wm}])))" \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(';'.join('%s=%.0f'%(x['metric'].get('destination','?'),float(x['value'][1])*1000) for x in r if x['value'][1] not in('NaN','')))" 2>/dev/null)
  local hop99=$(promq "histogram_quantile(0.99, sum by(le,destination)(rate(grpc_client_latency_seconds_bucket{namespace=\"$NS\"}[${wm}])))" \
    | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(';'.join('%s=%.0f'%(x['metric'].get('destination','?'),float(x['value'][1])*1000) for x in r if x['value'][1] not in('NaN','')))" 2>/dev/null)
  # (C) サービス別CPU使用率(usage/request %)。top3を出す
  local hot=$(promq "sort_desc( sum by(pod)(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*|promq.*\"}[${wm}])) / on(pod) group_left sum by(pod)(kube_pod_container_resource_requests{namespace=\"$NS\",resource=\"cpu\"}) )" \
    | python3 -c "
import sys,json,re
r=json.load(sys.stdin).get('data',{}).get('result',[])
out=[]
for x in r[:6]:
    pod=x['metric'].get('pod','?'); svc=re.sub(r'-[a-f0-9]{6,}.*$','',pod)
    try: out.append('%s=%.0f%%'%(svc,float(x['value'][1])*100))
    except: pass
print(';'.join(out))" 2>/dev/null)
  # loadgen 終了待ち→種別別 p50 採取
  local logs=""; for i in $(seq 1 60);do logs=$(kubectl logs $pod -n $NS -c main --tail=-1 2>/dev/null); echo "$logs"|grep -q '@@@CSV_END@@@'&&break; sleep 4;done
  printf '%s\n' "$logs" > /tmp/lat-logs.txt
  python3 - "$arm" "$u" "$CSV" "$hop50" "$hop99" "$hot" /tmp/lat-logs.txt <<'PY'
import sys,csv,io
arm,u,out,hop50,hop99,hot,lf=sys.argv[1:8]
d=open(lf,encoding='utf-8',errors='replace').read()
b,e="@@@CSV_BEGIN@@@","@@@CSV_END@@@"
rps=fails=ap50=ap90=ap99=p_prod=p_cart=p_chk=p_chk99="NA"
if b in d and e in d:
    rows=list(csv.reader(io.StringIO(d.split(b,1)[1].split(e,1)[0].strip())));hdr=rows[0]
    def gi(n): return hdr.index(n) if n in hdr else None
    def val(row,n,d="NA"):
        i=gi(n); return row[i] if i is not None and i<len(row) else d
    prod=[]
    for row in rows[1:]:
        if len(row)<2:continue
        nm=row[1]
        if nm=="Aggregated": rps=val(row,"Requests/s");fails=val(row,"Failure Count");ap50=val(row,"50%");ap90=val(row,"90%");ap99=val(row,"99%")
        elif nm.startswith("/product"):
            try:prod.append(float(val(row,"50%")))
            except:pass
        elif nm=="/cart": p_cart=val(row,"50%")
        elif nm=="/cart/checkout": p_chk=val(row,"50%");p_chk99=val(row,"99%")
    if prod: p_prod="%.0f"%(sum(prod)/len(prod))
def q(s): return '"'+s+'"' if s and (';' in s or ',' in s) else s
with open(out,"a",newline="") as f:
    csv.writer(f).writerow([arm,u,rps,fails,ap50,ap90,ap99,p_prod,p_cart,p_chk,p_chk99,hop50,hop99,hot])
print(f"  -> [{arm} u{u}] rps={rps} agg_p50={ap50} product={p_prod} cart={p_cart} checkout={p_chk}(p99 {p_chk99})")
print(f"     hop_p50=[{hop50}]")
print(f"     hot=[{hot}]")
PY
  kubectl delete job loadgenerator -n $NS --ignore-not-found >/dev/null 2>&1
}

ensure_promq
for ARM in $ARMS; do
  deploy "$ARM"; sleep 10
  for U in $LOADS; do run_point "$ARM" "$U"; done
done
kubectl delete job loadgenerator -n $NS --ignore-not-found >/dev/null 2>&1
kubectl delete hpa --all -n $NS >/dev/null 2>&1
echo "================ LATENCY-SWEEP DONE $(date -Is) ================"
column -s, -t "$CSV" 2>/dev/null | cut -c1-160 || cat "$CSV"
