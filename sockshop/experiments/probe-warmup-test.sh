#!/usr/bin/env bash
# Sock Shop: readinessProbe 10 s の動作確認と Java の慣らし時間の測定 (2026-10-19)
#
# 1. 全 Deployment を立て直し、各 Pod の「コンテナ起動 → Ready」までの秒数を記録する。
# 2. 全部 Ready になったら負荷 (既定 b24v120 = ρ 測定で最も重い点) を LOAD 秒流し続ける (WARM 0 = 全体を記録)。
#    5 秒ごとに全 Pod の Ready と再起動回数を記録 (Ready 落ちがないか)。
# 3. 負荷の開始から SCALE_AT 秒後に、アプリ 8 つを 2 台にする (HPA が新しい Pod を足したときを模す)。
#    新しい Pod の起動 → Ready の秒数と、立ち上がり直後の CPU を見る。
# 4. 終わったら Prometheus から Pod ごとの CPU (rate 30s、10 秒刻み) を取り、プローブ失敗のイベントを保存する。
# HPA は使わない。終わった後は 2 台のまま残る (次の測定は立て直すので問題ない)。
set -u
NS=exp
DIR=/home/mizuki/ダウンロード/msa/sockshop
OUT=$DIR/experiments
TAG=${TAG:-probe10}
BUY=${BUY:-24}; VIEW=${VIEW:-120}
LOAD=${LOAD:-1200}
SCALE_AT=${SCALE_AT:-720}
APPS=(front-end catalogue carts orders payment shipping user queue-master)
PROM="http://prometheus-grafana-kube-pr-prometheus.monitoring.svc:9090"
LOG=$OUT/$TAG.log
exec > >(tee -a "$LOG") 2>&1
echo "==== START $(date -Is) tag=$TAG buy=$BUY view=$VIEW load=${LOAD}s scale_at=${SCALE_AT}s ===="

pods_json(){ kubectl get pods -n $NS -o json 2>/dev/null; }
# Pod ごとの 起動→Ready 秒数 (Ready になっていなければ空)
ready_times(){ pods_json | python3 -c '
import json,sys,datetime
p=lambda s: datetime.datetime.fromisoformat(s.replace("Z","+00:00")).timestamp()
for it in json.load(sys.stdin)["items"]:
    n=it["metadata"]["name"]
    if n.startswith(("promq","k6load")): continue
    cs=(it["status"].get("containerStatuses") or [{}])[0]
    st=cs.get("state",{}).get("running",{}).get("startedAt")
    rd=[c for c in it["status"].get("conditions",[]) if c["type"]=="Ready"]
    ok=rd and rd[0]["status"]=="True"
    print(n, st or "-", (round(p(rd[0]["lastTransitionTime"])-p(st)) if ok and st else "-"), cs.get("restartCount",0))
'; }

echo "---- 立て直し ----"
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
kubectl delete hpa --all -n $NS >/dev/null 2>&1
kubectl delete deploy --all -n $NS >/dev/null 2>&1
for i in $(seq 1 60);do [ -z "$(kubectl get pods -n $NS -o name 2>/dev/null | grep -v promq)" ]&&break;sleep 3;done
T_APPLY=$(date +%s)
kubectl apply -n $NS -f $DIR/normal/ >/dev/null
for d in $(kubectl get deploy -n $NS -o name); do kubectl rollout status $d -n $NS --timeout=400s >/dev/null 2>&1 || echo "  !! rollout 未完: $d"; done
echo "  全 Ready まで $(( $(date +%s) - T_APPLY )) s (apply から)"
echo "  Pod 起動時刻 起動→Ready[s] 再起動"; ready_times | sed 's/^/  /' | tee $OUT/$TAG-startup.txt
sleep 10

echo "---- 負荷 b${BUY}v${VIEW} を ${LOAD}s ----"
kubectl create configmap k6-script -n $NS --from-file=sockshop.js=$DIR/k6/sockshop.js --dry-run=client -o yaml | kubectl apply -n $NS -f - >/dev/null 2>&1
sed -e "s/__RATE__/$BUY/;s/__BROWSE__/$VIEW/;s/__WARM__/0/;s/__MEAS__/$LOAD/;s/__PRE__/50/;s/__MAX__/400/;s/__NUSERS__/200/" \
  $DIR/k6/k6-job.yaml | kubectl apply -n $NS -f - >/dev/null
until kubectl logs -n $NS job/k6load 2>/dev/null | grep -q K6_START; do sleep 2; done
T0=$(( $(kubectl logs -n $NS job/k6load | grep -oE '@@@K6_START@@@ [0-9]+' | awk '{print $2}') / 1000 ))
echo "  負荷開始 $(date -d @$T0 -Is)"
echo "t,pod,ready,restarts" > $OUT/$TAG-ready.csv
scaled=0
while :; do
  now=$(date +%s); t=$(( now - T0 ))
  pods_json | T=$t python3 -c '
import json,sys,os
for it in json.load(sys.stdin)["items"]:
    n=it["metadata"]["name"]
    if n.startswith(("promq","k6load")): continue
    rd=[c for c in it["status"].get("conditions",[]) if c["type"]=="Ready"]
    cs=(it["status"].get("containerStatuses") or [{}])
    print("%s,%s,%d,%d"%(os.environ["T"],n,1 if rd and rd[0]["status"]=="True" else 0,sum(c.get("restartCount",0) for c in cs)))
' >> $OUT/$TAG-ready.csv
  if [ $scaled = 0 ] && [ $t -ge $SCALE_AT ]; then
    echo "  t=${t}s アプリ 8 つを 2 台に"; for d in "${APPS[@]}"; do kubectl scale deploy/$d -n $NS --replicas=2 >/dev/null; done; scaled=1; T_SCALE=$now
  fi
  kubectl logs -n $NS job/k6load 2>/dev/null | grep -q K6_DONE && break
  sleep 5
done
T1=$(date +%s)
echo "---- 2 台目の 起動→Ready ----"; ready_times | sed 's/^/  /' | tee $OUT/$TAG-afterscale.txt
sum=$(kubectl logs -n $NS job/k6load | sed -n '/@@@K6_BEGIN@@@/,/@@@K6_END@@@/p' | grep '{')
echo "  k6: $sum"

echo "---- Prometheus: Pod ごとの CPU (rate 30s、10 秒刻み) ----"
kubectl exec promq -n $NS -- curl -s --max-time 60 "$PROM/api/v1/query_range" \
  --data-urlencode "query=sum by(pod,container)(rate(container_cpu_usage_seconds_total{namespace=\"$NS\",container!=\"\",container!=\"POD\",pod!~\"promq.*\"}[30s]))" \
  --data-urlencode "start=$(( T_APPLY ))" --data-urlencode "end=$T1" --data-urlencode "step=10" \
| T0=$T0 python3 -c '
import json,sys,os
t0=int(os.environ["T0"]); print("t,pod,container,cpu_m")
for r in json.load(sys.stdin)["data"]["result"]:
    for t,v in r["values"]: print("%d,%s,%s,%.1f"%(int(t)-t0,r["metric"]["pod"],r["metric"]["container"],float(v)*1000))
' > $OUT/$TAG-cpu.csv
echo "  行数 $(wc -l < $OUT/$TAG-cpu.csv)"
kubectl get events -n $NS --field-selector reason=Unhealthy -o custom-columns=TIME:.lastTimestamp,OBJ:.involvedObject.name,COUNT:.count,MSG:.message --no-headers > $OUT/$TAG-unhealthy.txt 2>/dev/null
echo "  プローブ失敗イベント: $(wc -l < $OUT/$TAG-unhealthy.txt) 件"; head -20 $OUT/$TAG-unhealthy.txt | sed 's/^/  /'
kubectl delete job k6load -n $NS --ignore-not-found >/dev/null 2>&1
echo "==== DONE $(date -Is) ===="
