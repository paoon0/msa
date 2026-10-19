#!/usr/bin/env python3
# probe-warmup-test.sh の出力 (probe10-cpu.csv) から、立て直し直後の慣らし時間と、2 台目を足したときの CPU の立ち上がり・分担を出す。sockshop/experiments で実行。
import csv,collections,re
R=list(csv.DictReader(open('probe10-cpu.csv')))
dep=lambda p: re.sub(r'-[a-f0-9]{6,}-\w+$','',p)
S=collections.defaultdict(dict)
for r in R: S[r['pod']][int(r['t'])]=float(r['cpu_m'])
pods=collections.defaultdict(list)
for p in S:
    if len(S[p])>=20: pods[dep(p)].append(p)
A=lambda x:sum(x)/len(x) if x else float('nan')
a=lambda p,lo,hi:A([v for t,v in S[p].items() if lo<=t<=hi])
APPS=['front-end','catalogue','carts','orders','user','payment','shipping','queue-master']
print('1) 立て直し直後の Pod: 負荷開始 (t=0) からの 60 秒平均 [m]、定常 = t 400..700')
print('   %-13s %6s | %s'%('','定常',' '.join('%6s'%f'{a0}-' for a0 in range(-60,420,60))))
for d in APPS:
    p=min(pods[d],key=lambda p:min(S[p])); ss=a(p,400,700)
    print('   %-13s %6.0f | %s'%(d,ss,' '.join('%6.0f'%a(p,a0,a0+59) for a0 in range(-60,420,60))))
print('2) 12 分目に足した 2 台目 (t=724〜): 起動直後の CPU、10 秒刻みの最大、定常の分担')
for d in APPS:
    ps=sorted(pods[d],key=lambda p:min(S[p])); old,new=ps[0],ps[-1]
    t0=min(S[new]); mx=max(S[new].values())
    print('   %-13s 新Pod 最初60s %6.0f  次60s %6.0f  10秒最大 %6.0f | t900-1200 旧 %5.0f 新 %5.0f (新/旧 %.2f) 合計 %5.0f / 1台時 %5.0f'%(
        d,a(new,t0,t0+59),a(new,t0+60,t0+119),mx,a(old,900,1200),a(new,900,1200),a(new,900,1200)/max(a(old,900,1200),1e-9),a(old,900,1200)+a(new,900,1200),a(old,400,700)))
