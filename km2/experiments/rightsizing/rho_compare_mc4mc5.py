# mc4raw / mc5raw (rho_raw_mc4mc5.py の出力) から、全 10 サービスの ρ を 1 台・2 台別に前回→今回で並べる (2026-11-21)。
# 区間 = サイクルブートストラップ 95% [ ] と t 区間 ( )。1 台は飽和 2 点 (b100v150・b50v300) を外した ρ も。
# 使い方 (rightsizing/ で): python3 rho_compare_mc4mc5.py <rho_raw_mc4mc5.py の出力フォルダ>
import sys, io, contextlib, collections
ARGS=list(sys.argv); sys.argv=['x','results-mix-cpu4.csv','results-mix-cpu4.csv']
src=open('analyze_rho2.py').read().split('SEED = 20261010')[0]
with contextlib.redirect_stdout(io.StringIO()): exec(src)
P=ARGS[1]
SV=['frontend','productcatalogservice','recommendationservice','currencyservice','cartservice','adservice','checkoutservice','paymentservice','shippingservice','emailservice']
SAT={(100.0,150.0),(50.0,300.0)}
def get(name):
    with contextlib.redirect_stdout(io.StringIO()): return load(P+'/'+name+'.csv')
A=get('mc4raw'); B=get('mc5raw')
for n in ['1','2']:
    print(f'== {n} 台  ρ: 前回(6回) → 今回(6回) [サイクルブートストラップ 95%]  (t 区間)' + ('   | 飽和 2 点を外した ρ 前回→今回' if n=='1' else ''))
    for s in SV:
        out=[]
        for D,seed in ((A,20261010),(B,20261011)):
            rows=D[(s,n)]; p=params(rows)['rho']; bs=boot(rows,lambda rr:params(rr),seed)
            per=[params([x for x in rows if x[0]==c])['rho'] for c in sorted({x[0] for x in rows})]
            tl,th=tint(per); out.append((p,pct([b['rho'] for b in bs],.025),pct([b['rho'] for b in bs],.975),tl,th))
        extra=''
        if n=='1':
            f=lambda D:params([x for x in D[(s,n)] if (x[1],x[2]) not in SAT])['rho']
            extra=f'   | {f(A):.4f}→{f(B):.4f} ({f(B)-f(A):+.4f})'
        a,b=out
        print(f'  {SHORT[s]:9} {a[0]:.4f} [{a[1]:.4f},{a[2]:.4f}] → {b[0]:.4f} [{b[1]:.4f},{b[2]:.4f}] ({b[3]:.4f},{b[4]:.4f})  差 {b[0]-a[0]:+.4f}{extra}')
    for x,y in (('frontend','productcatalogservice'),('frontend','recommendationservice'),('productcatalogservice','recommendationservice')):
        r=[]
        for D in (A,B):
            per=[]
            cyc=sorted({q[0] for q in D[(x,n)]})
            for c in cyc:
                per.append(params([q for q in D[(x,n)] if q[0]==c])['rho']-params([q for q in D[(y,n)] if q[0]==c])['rho'])
            pe=params(D[(x,n)])['rho']-params(D[(y,n)])['rho']; tl,th=tint(per); r.append((pe,tl,th,per))
        print(f'  {SHORT[x]}−{SHORT[y]}: 前回 {r[0][0]:+.4f} ({r[0][1]:+.4f},{r[0][2]:+.4f}) → 今回 {r[1][0]:+.4f} ({r[1][1]:+.4f},{r[1][2]:+.4f})  今回のサイクル別 '+' / '.join(f'{v:+.4f}' for v in r[1][3]))
