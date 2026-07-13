#!/usr/bin/env bash
# ============================================================================
# normal 構成(全サービス分離・Istio無し)で負荷をかけ、各サービス Pod の
#   ネットワーク パケット率(rx+tx pkts/s) と バイト率(rx+tx bytes/s) を実測する。
#   目的: 「バイト vs パケット」どちらが softirq を駆動するかの入力データ。
#         各サービスの平均パケットサイズ(bytes/pkt)も出す。
# 負荷は実験と同条件 USERS=80 RATE=1(rps≈208)。ウォームアップ後の窓[2m]で rate。
# 出力: km2/experiments/netmeasure.csv (pod, pkts_s, bytes_s, bytes_per_pkt)
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
LG_USERS=${LG_USERS:-80}
LG_RATE=${LG_RATE:-1}
WARMUP=${WARMUP:-150}          # 定常化待ち(秒)
WIN=${WIN:-2m}                 # rate 窓
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-net.yaml
CSV=$REPO/km2/experiments/netmeasure.csv
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT_TIMEOUT=300s
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)

setup_promq() {
  kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n "$NS" --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30); do [ "$(kubectl get pod promq -n "$NS" -o jsonpath='{.status.phase}' 2>/dev/null)" = "Running" ] && break; sleep 2; done
}
prom_vec() { # query -> "pod value" lines
  kubectl exec promq -n "$NS" -- curl -s "$PROM/api/v1/query" --data-urlencode "query=$1" 2>/dev/null
}

echo "================ NETMEASURE START $(date -Is) ================"
setup_promq

echo "---- 既存トポロジ全削除 → normal(分離) を張る ----"
kubectl delete -f "$REPO/km2/all/all.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1
for f in "${NORMAL[@]}"; do kubectl delete -f "$REPO/km2/$f.yaml" -n "$NS" --ignore-not-found >/dev/null 2>&1; done
for i in $(seq 1 40); do [ -z "$(kubectl get deploy -n "$NS" -o name 2>/dev/null)" ] && break; sleep 3; done
for f in "${NORMAL[@]}"; do kubectl apply -f "$REPO/km2/$f.yaml" -n "$NS" >/dev/null; done
for d in "${NORMAL[@]}" redis-cart; do
  kubectl patch deploy/"$d" -n "$NS" --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1 || true
done
for d in "${NORMAL[@]}" redis-cart; do kubectl rollout status deploy/"$d" -n "$NS" --timeout="$ROLLOUT_TIMEOUT" >/dev/null 2>&1 || true; done

echo "---- 負荷開始(USERS=$LG_USERS RATE=$LG_RATE) → 定常化 ${WARMUP}s 待ち ----"
sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"10m\"/; \
        s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_USERS\"/; \
        s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$LG_RATE\"/" "$LOAD" > "$LOADGEN"
kubectl delete job loadgenerator -n "$NS" --ignore-not-found --wait=true >/dev/null 2>&1
kubectl apply -f "$LOADGEN" -n "$NS" >/dev/null
sleep "$WARMUP"

echo "---- 計測(窓 $WIN) $(date -Is) ----"
PKT=$(prom_vec "sum by (pod)(rate(container_network_receive_packets_total{namespace=\"$NS\"}[$WIN]) + rate(container_network_transmit_packets_total{namespace=\"$NS\"}[$WIN]))")
BYT=$(prom_vec "sum by (pod)(rate(container_network_receive_bytes_total{namespace=\"$NS\"}[$WIN]) + rate(container_network_transmit_bytes_total{namespace=\"$NS\"}[$WIN]))")

python3 - "$CSV" "$PKT" "$BYT" <<'PY'
import sys,json,re
csvpath,pkt,byt=sys.argv[1],sys.argv[2],sys.argv[3]
def parse(j):
    d={}
    try: r=json.loads(j).get('data',{}).get('result',[])
    except: return d
    for x in r:
        pod=x['metric'].get('pod','?'); d[pod]=float(x['value'][1])
    return d
P=parse(pkt); B=parse(byt)
def svc(pod): return re.sub(r'-[0-9a-f]{6,10}-[0-9a-z]{5}$','',pod)
rows=[]
for pod in set(P)|set(B):
    if pod.startswith('loadgenerator') or pod.startswith('promq'): continue
    p=P.get(pod,0); b=B.get(pod,0)
    rows.append((svc(pod), p, b, b/p if p else 0))
rows.sort(key=lambda r:-r[1])
w=open(csvpath,'w'); w.write("service,pkts_per_s,bytes_per_s,bytes_per_pkt\n")
print("\n%-24s %10s %14s %12s"%("service","pkts/s","bytes/s","bytes/pkt"))
print("-"*64)
for s,p,b,bp in rows:
    print("%-24s %10.0f %14.0f %12.0f"%(s,p,b,bp))
    w.write("%s,%.0f,%.0f,%.0f\n"%(s,p,b,bp))
w.close()
tp=sum(r[1] for r in rows); tb=sum(r[2] for r in rows)
print("-"*64); print("%-24s %10.0f %14.0f"%("TOTAL",tp,tb))
PY

kubectl delete job loadgenerator -n "$NS" --ignore-not-found >/dev/null 2>&1
kubectl delete pod promq -n "$NS" --ignore-not-found >/dev/null 2>&1
echo "================ NETMEASURE DONE $(date -Is) -> $CSV ================"
