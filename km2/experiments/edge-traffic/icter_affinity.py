#!/usr/bin/env python3
"""/proc/net/dev のスナップショット2枚の差分を取り、Pod×インタフェース別の通信量を CSV に追記する。

/proc/net/dev の書式:
  Inter-|   Receive                    |  Transmit
   face |bytes packets errs drop fifo frame compressed multicast|bytes packets ...
  eth0: 12345 100 0 0 0 0 0 0  6789 80 0 0 0 0 0 0

デバイス層のバイト数なのでヘッダ(カプセル化)を含む = ICTer の affinity と同じ意味。
"""
import sys, os, csv, re

def parse(path):
    out={}   # (pod, iface) -> (rx_bytes, rx_pkts, tx_bytes, tx_pkts)
    pod=None
    for line in open(path):
        line=line.rstrip()
        if line.startswith('### '):
            pod=line[4:].strip(); continue
        m=re.match(r'\s*([A-Za-z0-9_.@-]+):\s*(.*)$', line)
        if not m or pod is None: continue
        iface=m.group(1); f=m.group(2).split()
        if len(f)<16: continue
        try: out[(pod,iface)]=(int(f[0]),int(f[1]),int(f[8]),int(f[9]))
        except ValueError: continue
    return out

a,b,out_csv = sys.argv[1:4]
A,B=parse(a),parse(b)
cyc=os.environ.get('CYC','1'); arm=os.environ.get('ARM','?')
it=os.environ.get('ITER','0'); meas=os.environ.get('MEAS','180')
rows=[]
for key,vb in B.items():
    va=A.get(key,(0,0,0,0))
    d=[max(0,vb[i]-va[i]) for i in range(4)]
    if sum(d)==0: continue
    pod,iface=key
    rows.append([cyc,arm,pod,iface,d[0],d[2],d[1],d[3],it,meas])
with open(out_csv,'a',newline='') as f:
    w=csv.writer(f); w.writerows(rows)
tot={}
for r in rows:
    tot.setdefault(r[3],[0,0])
    tot[r[3]][0]+=r[4]; tot[r[3]][1]+=r[5]
print("  [%s/%s] インタフェース別 合計: " % (arm,cyc) +
      "  ".join(f"{k}: rx={v[0]/1e6:.1f}MB tx={v[1]/1e6:.1f}MB" for k,v in sorted(tot.items())))
