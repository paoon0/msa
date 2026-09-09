#!/usr/bin/env bash
# ============================================================================
# normalの頭打ちが「HPAのCPU盲点による過少スケール」か「経路長(通信)の壁」かを判定。
# 全アプリサービスを固定4台(HPA無し, redisは1)にして u480 を計測。
#   HPA管理下(frontend3/catalog3/checkout1, rps~664)と比べ:
#     rps↑ latency↓  → HPAが過少スケールしていた(CPU盲点を実証)
#     rps~664のまま   → 台数では直らない経路長の壁
# 出力: km2/experiments/latency-breakdown/fixed-replicas.txt
# ============================================================================
set -u
NS=exp
REPO=/home/mizuki/ダウンロード/msa
REPLICAS=${REPLICAS:-4}
REQ_M=${REQ_M:-150}   # 4台がノードに載るようcpu requestを下げる(limitは据置=実処理不変, HPA不使用ゆえscaling基準にも無関係)
USERS=${USERS:-480}
RATE=${RATE:-40}
WARM=${WARM:-120}
MEAS=${MEAS:-150}
LOAD=$REPO/km2/experiments/loadgen-csv.yaml
LOADGEN=/tmp/loadgen-fixed.yaml
OUT=$REPO/km2/experiments/latency-breakdown/fixed-replicas.txt
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
ROLLOUT=300s
NORMAL=(frontend checkoutservice cartservice productcatalogservice currencyservice \
        paymentservice shippingservice emailservice recommendationservice adservice)
ARM=${ARM:-normal}   # normal(分離) or f3perc(束ね: frontend Podにfront+reco+catalog同居)
SWEEPCSV=${SWEEPCSV:-}   # 設定すると Aggregated行を1行追記(スイープ集計用)
# 束ねでスケールする Deployment 群(frontendが束ねPod, reco/catalogは中に居るので単独無し)
BUNDLE_SCALE=(frontend checkoutservice cartservice currencyservice paymentservice shippingservice emailservice adservice)
OUT=$REPO/km2/experiments/latency-breakdown/fixed-$ARM.txt

exec > >(tee -a "${OUT%.txt}.log") 2>&1
echo "================ FIXED-REPLICAS START $(date -Is) ARM=$ARM replicas=$REPLICAS users=$USERS ================"

ensure_promq(){ [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ] && return
  kubectl delete pod promq -n $NS --ignore-not-found >/dev/null 2>&1
  kubectl run promq -n $NS --image=curlimages/curl:latest --restart=Never --command -- sleep 86400 >/dev/null 2>&1
  for i in $(seq 1 30);do [ "$(kubectl get pod promq -n $NS -o jsonpath='{.status.phase}' 2>/dev/null)" = Running ]&&break;sleep 2;done; }
promq(){ local q="$1" i out; for i in 1 2 3 4 5;do ensure_promq
  out=$(kubectl exec promq -n $NS -- curl -s --max-time 20 "$PROM/api/v1/query" --data-urlencode "query=$q" 2>/dev/null)
  [ -n "$out" ]&&{ echo "$out"; return; }; sleep 4; done; echo ""; }

echo "---- deploy $ARM + 固定${REPLICAS}台(HPA無し) ----"
kubectl delete hpa --all -n $NS >/dev/null 2>&1
kubectl delete deploy --all -n $NS >/dev/null 2>&1
for i in $(seq 1 40);do [ -z "$(kubectl get deploy -n $NS -o name 2>/dev/null)" ]&&break;sleep 3;done
if [ "$ARM" = normal ];then
  for f in "${NORMAL[@]}";do kubectl apply -f $REPO/km2/normal/$f.yaml -n $NS >/dev/null;done
  SCALE=("${NORMAL[@]}")
else  # f3perc(束ね)
  for y in $REPO/km2/frontrecocatalogcart/*.yaml;do case "$y" in *kustomization*|*loadgenerator*|*hpa-percontainer*)continue;;esac;kubectl apply -f "$y" -n $NS >/dev/null;done
  SCALE=("${BUNDLE_SCALE[@]}")
fi
kubectl delete hpa --all -n $NS >/dev/null 2>&1   # マニフェスト同梱HPA(束ねのfrontrecocatalogcart.yaml等)を消して真の固定台数にする
for d in "${SCALE[@]}" redis-cart;do kubectl patch deploy/$d -n $NS --type=merge -p '{"spec":{"template":{"metadata":{"annotations":{"sidecar.istio.io/inject":"false"}}}}}' >/dev/null 2>&1||true;done
# cpu requestを$REQ_Mに下げて4台がノードに載るように(limitは据置)。束ねPodは3コンテナ各150m。
for d in "${SCALE[@]}";do kubectl set resources deploy/$d -n $NS --requests=cpu=${REQ_M}m >/dev/null 2>&1||true;done
# 固定台数: スケール対象REPLICAS台, redisは1
for d in "${SCALE[@]}";do kubectl scale deploy/$d -n $NS --replicas=$REPLICAS >/dev/null 2>&1||true;done
kubectl scale deploy/redis-cart -n $NS --replicas=1 >/dev/null 2>&1||true
for d in "${SCALE[@]}" redis-cart;do kubectl rollout status deploy/$d -n $NS --timeout=$ROLLOUT >/dev/null 2>&1||true;done
echo "  デプロイ完了: $(kubectl get deploy -n $NS --no-headers 2>/dev/null | awk '{printf "%s=%s ",$1,$2}')"

ensure_promq
echo "---- $(date -Is) 負荷 users=$USERS (warmup ${WARM}s + measure ${MEAS}s) ----"
sed -E "s/(name: RUN_TIME, value: )\"[^\"]*\"/\1\"$((WARM+MEAS+30))s\"/; s/(name: USERS,[[:space:]]*value: )\"[^\"]*\"/\1\"$USERS\"/; s/(name: RATE,[[:space:]]*value: )\"[^\"]*\"/\1\"$RATE\"/" "$LOAD" > "$LOADGEN"
kubectl delete job loadgenerator -n $NS --ignore-not-found --wait=true >/dev/null 2>&1
kubectl apply -f "$LOADGEN" -n $NS >/dev/null
pod=""; for i in $(seq 1 40);do pod=$(kubectl get pods -n $NS -l job-name=loadgenerator --sort-by=.metadata.creationTimestamp -o jsonpath='{.items[-1].metadata.name}' 2>/dev/null)
  [ -n "$pod" ]&&[ -n "$(kubectl get pod $pod -n $NS -o jsonpath='{.status.containerStatuses[?(@.name=="main")].state.running.startedAt}' 2>/dev/null)" ]&&break;sleep 3;done
sleep $WARM
sleep $MEAS
wm="${MEAS}s"
echo "---- $(date -Is) 採取 ----"
# per-service CPU(絶対ミリコア) 全サービス。requestを下げたので%でなくmcで見る。limitも併記。
HOT=$(promq "sum by(pod)(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"loadgenerator.*|promq.*\"}[${wm}]))")
LIM=$(promq "sum by(pod)(kube_pod_container_resource_limits{namespace=\"$NS\",resource=\"cpu\"})")
echo "$HOT|@|$LIM" | python3 -c "
import sys,json,re,collections
raw=sys.stdin.read().split('|@|')
def parse(s):
    try: return json.loads(s).get('data',{}).get('result',[])
    except: return []
use,lim=parse(raw[0]),parse(raw[1])
def bysvc(r,scale):
    d=collections.defaultdict(list)
    for x in r:
        pod=x['metric'].get('pod','?'); svc=re.sub(r'-[a-f0-9]{6,}.*\$','',pod)
        try: d[svc].append(float(x['value'][1])*scale)
        except: pass
    return d
u=bysvc(use,1000); l=bysvc(lim,1000)
print('  per-service CPU(絶対mc: 合計使用 / 台数 / 1台使用 / 1台limit / limit比):')
for svc,v in sorted(u.items(),key=lambda kv:-sum(kv[1])):
    tot=sum(v); n=len(v); per=tot/n
    lper=(sum(l.get(svc,[0]))/len(l[svc])) if l.get(svc) else 0
    pct=('%.0f%%'%(per/lper*100)) if lper else '-'
    print('    %-24s 合計%5.0fm  x%d  1台%4.0fm  limit%4.0fm  (%s)'%(svc,tot,n,per,lper,pct))
" 2>/dev/null
# node/app/softirq
NODE=$(promq "sum(rate(node_cpu_seconds_total{mode!=\"idle\"}[${wm}]))" | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(r[0]['value'][1] if r else 'NA')" 2>/dev/null)
# checkout hop latency
HOP=$(promq "histogram_quantile(0.5, sum by(le,destination)(rate(grpc_client_latency_seconds_bucket{namespace=\"$NS\"}[${wm}])))" | python3 -c "import sys,json;r=json.load(sys.stdin).get('data',{}).get('result',[]);print(';'.join('%s=%.0f'%(x['metric'].get('destination','?'),float(x['value'][1])*1000) for x in r if x['value'][1] not in('NaN','')))" 2>/dev/null)
echo "  node_cores=${NODE} (of 16)"
echo "  checkout下流ホップ p50(ms): [$HOP]"
# locust 結果
logs=""; for i in $(seq 1 60);do logs=$(kubectl logs $pod -n $NS -c main --tail=-1 2>/dev/null); echo "$logs"|grep -q '@@@CSV_END@@@'&&break;sleep 4;done
export ARM REPLICAS USERS NODE SWEEPCSV
echo "$logs" | python3 -c "
import sys,csv,io,os
d=sys.stdin.read(); b,e='@@@CSV_BEGIN@@@','@@@CSV_END@@@'
if b in d and e in d:
    rows=list(csv.reader(io.StringIO(d.split(b,1)[1].split(e,1)[0].strip())));h=rows[0]
    def gi(n):return h.index(n) if n in h else None
    agg=None
    for row in rows[1:]:
        if len(row)>1 and (row[1] in ('Aggregated','/cart/checkout','/cart') or (row[1].startswith('/product') and 'PUK' in row[1])):
            def v(n):
                i=gi(n);return row[i] if i is not None and i<len(row) else '?'
            print('  %-16s rps=%-7s p50=%-6s p90=%-6s p99=%-6s fails=%s'%(row[1][:16],v('Requests/s'),v('50%'),v('90%'),v('99%'),v('Failure Count')))
            if row[1]=='Aggregated': agg=row
    sc=os.environ.get('SWEEPCSV','')
    if sc and agg:
        def v(n):
            i=gi(n);return agg[i] if i is not None and i<len(agg) else ''
        new=not os.path.exists(sc)
        with open(sc,'a',newline='') as f:
            w=csv.writer(f)
            if new: w.writerow(['arm','replicas','users','rps','p50','p90','p99','fails','node_cores'])
            w.writerow([os.environ.get('ARM'),os.environ.get('REPLICAS'),os.environ.get('USERS'),v('Requests/s'),v('50%'),v('90%'),v('99%'),v('Failure Count'),os.environ.get('NODE')])
" 2>/dev/null
kubectl delete job loadgenerator -n $NS --ignore-not-found >/dev/null 2>&1
echo "================ FIXED-REPLICAS DONE $(date -Is) ================"
