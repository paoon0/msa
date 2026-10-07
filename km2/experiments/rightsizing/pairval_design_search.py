import subprocess,csv,collections,json
R='/home/mizuki/ダウンロード/msa/km2/experiments/rightsizing/'
import tempfile; D=tempfile.mkdtemp(prefix='pairval-design-') + '/'   # 2026-10-08 の探索は Claude の作業領域で実行した (結果は pairval-design-search.txt)
REFS=[(50,0),(100,0),(50,50),(100,50),(50,100),(100,100)]
THS=[0.50,0.55,0.60,0.65,0.70]
res=[];data={}
for rb,rv in REFS:
  for th in THS:
    tag=f'b{rb}v{rv}_t{th:.2f}'
    subprocess.run(['python3',R+'predict_pairs.py','--ref-buy',str(rb),'--ref-view',str(rv),'--theta',str(th),'--grid-buy','50','100','--grid-view','0','50','100','150','--out-pred',D+f'p_{tag}.csv','--out-req',D+f'r_{tag}.csv'],stdout=subprocess.DEVNULL,check=True)
    rows=[r for r in csv.DictReader(open(D+f'p_{tag}.csv')) if r['s']!='adservice' and r['t']!='adservice']
    allrows=list(csv.DictReader(open(D+f'p_{tag}.csv')))
    rq={r['deploy']:r for r in csv.DictReader(open(D+f'r_{tag}.csv'))}
    n=len(rows); det=sum(r['category']!='不明' for r in rows)
    ari=[r for r in rows if r['category']=='損あり']; nas=[r for r in rows if r['category']=='損なし']
    pa={r['pair'] for r in ari}; pn={r['pair'] for r in nas}
    flip=pa&pn
    ext=[r for r in rows if '外挿' in r['flags']]
    maxn=max(int(r['n_st']) for r in allrows if r['n_st']!='')
    # fleet
    nsv={}
    for r in allrows:
        for k,svc in (('n_s','s'),('n_t','t')):
            if r[k]!='': nsv[(r[svc],r['buy'],r['view'],r['start'])]=int(r[k])
    req={s:int(float(rq[s]['request_m'])) for s in rq}
    mx=0
    for r in allrows:
        if r['n_st']=='' : continue
        key=lambda s:(s,r['buy'],r['view'],r['start'])
        base=sum(req[s]*nsv[key(s)] for s in req if s!='redis-cart' and key(s) in nsv)+req['redis-cart']
        b=base-nsv[key(r['s'])]*req[r['s']]-nsv[key(r['t'])]*req[r['t']]+int(r['n_st'])*(req[r['s']]+req[r['t']])
        mx=max(mx,b)
    res.append(dict(tag=tag,rb=rb,rv=rv,th=th,n=n,det=det/n,na=len(nas),npn=len(pn),ari=len(ari),npa=len(pa),flip=len(flip),ext=len(ext),extpairs=len({r['pair'] for r in ext}),maxn=maxn,fleet=mx))
print('基準 θ | 確定率 | 損なし(セル/ペア) | 損あり(セル/ペア) | 入れ替わりペア | 外挿(セル/ペア) | 最大台数 | 最大枠合計[m]')
for r in res:
    print(f"b{r['rb']}v{r['rv']:<3} {r['th']:.2f} | {r['det']*100:5.1f}% | {r['na']:3d}/{r['npn']:2d} | {r['ari']:3d}/{r['npa']:2d} | {r['flip']:2d} | {r['ext']:2d}/{r['extpairs']} | {r['maxn']} | {r['fleet']}")
json.dump(res,open(D+'res.json','w'))
