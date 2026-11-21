# mix-cpu4 と mix-cpu5 の CPU を生カウンタ (-raw.csv の窓内の最初と最後の差) で作り直した CSV を書く (2026-11-21)。除外は analyze_rho2 と同じ。
# 使い方 (rightsizing/ で): python3 rho_raw_mc4mc5.py <出力フォルダ> 1,2,3,4,5,6   → mc4raw.csv / mc5raw.csv / mc4raw-same.csv
import csv, collections, sys, io, contextlib
ARGS=list(sys.argv)
src=open('analyze_rho2.py').read().split('SEED = 20261010')[0]
sys.argv=['x','results-mix-cpu4.csv','results-mix-cpu4.csv']
with contextlib.redirect_stdout(io.StringIO()): exec(src)
def rawD(base):
    g=collections.defaultdict(list)
    for y in csv.DictReader(open(base+'-raw.csv')):
        g[(y['cycle'],y['point'],y['replicas'],y['deploy'],y['container'],y['pod'])].append((float(y['t_unix']),float(y['cpu_seconds_total'])))
    D=collections.defaultdict(float)
    for k,v in g.items():
        if len(v)<2: continue
        v.sort(); D[k[:5]]+=1000*(v[-1][1]-v[0][1])/(v[-1][0]-v[0][0])
    return D
def write(base, cycles, out):
    D=rawD(base); rows=list(csv.DictReader(open(base+'.csv')))
    full={(r['cycle'],r['replicas']) for r in rows}
    with open(out,'w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader()
        for r in rows:
            if int(r['cycle']) not in cycles: continue
            k=(r['cycle'],r['point'],r['replicas'],r['deploy'],r.get('container',''))
            if k in D: r['usage_mc']='%.3f'%D[k]
            w.writerow(r)
import sys as S
P=ARGS[1]; cyc5=set(int(c) for c in ARGS[2].split(","))
write('results-mix-cpu4',{1,2,3,4,5,6},P+'/mc4raw.csv'); write('results-mix-cpu5',cyc5,P+'/mc5raw.csv')
write('results-mix-cpu4',cyc5,P+'/mc4raw-same.csv')
SV=['frontend','productcatalogservice','recommendationservice','currencyservice','cartservice','adservice']
for n in ['1','2']:
    res={}
    for name in ('mc4raw','mc4raw-same','mc5raw'):
        with contextlib.redirect_stdout(io.StringIO()): d=load(P+'/'+name+'.csv')
        res[name]={s:params(d[(s,n)])['rho'] for s in SV if d.get((s,n))}
    print(f'== {n} 台   (mc4=6 回 / mc4 同じ回だけ / mc5 途中)')
    for s in SV:
        print(f"  {SHORT[s]:9} {res['mc4raw'][s]:.3f}  {res['mc4raw-same'][s]:.3f}  {res['mc5raw'][s]:.3f}  差(mc5−mc4同回) {res['mc5raw'][s]-res['mc4raw-same'][s]:+.3f}")
    for a,b in (('frontend','productcatalogservice'),('frontend','recommendationservice'),('productcatalogservice','recommendationservice')):
        print(f"  {SHORT[a]}−{SHORT[b]}: mc4 {res['mc4raw'][a]-res['mc4raw'][b]:+.4f}  mc5 {res['mc5raw'][a]-res['mc5raw'][b]:+.4f}")
