#!/usr/bin/env python3
"""ss -tin のスナップショット2枚から、サービスペアごとの通信量を出す。

入力: snapA.txt / snapB.txt (「### <pod名>」で区切られた ss -tin の生出力)
      ipmap.txt  ("IP サービス名" の行。Pod IP と ClusterIP の両方)
出力: エッジ表(標準出力)+ CSV

接続は gRPC の HTTP/2 が張りっぱなしなので、カウンタは積算値。
同じ接続(pod, ローカルポート, 相手)を突き合わせて差分を取る。
窓の途中で新しく張られた接続は B にしか無いので、その全量を計上する。
"""
import re, sys, csv
from collections import defaultdict

def load_map(path):
    m={}
    for line in open(path):
        p=line.split()
        if len(p)>=2: m[p[0]]=p[1]
    return m

def parse(path):
    """-> {(pod, local, peer): {bytes_sent, bytes_received, segs_out, segs_in, rtt}}"""
    out={}
    pod=None; local=None; peer=None
    for line in open(path):
        line=line.rstrip()
        if line.startswith('### '):
            pod=line[4:].strip(); continue
        # ss のアドレス表記は2種類ある: "[::ffff:10.1.98.29]:47106" と "10.1.98.37:57126"
        m=re.search(r'(?:\[::ffff:([\d.]+)\]|(\d+\.\d+\.\d+\.\d+)):(\d+)\s+'
                    r'(?:\[::ffff:([\d.]+)\]|(\d+\.\d+\.\d+\.\d+)):(\d+)', line)
        if m:
            local=f"{m.group(1) or m.group(2)}:{m.group(3)}"
            peer =f"{m.group(4) or m.group(5)}:{m.group(6)}"; continue
        m2=re.search(r'\b(\d[\d.]*\.\d+\.\d+\.\d+)?', '')  # noop
        if 'bytes_sent' in line or 'bytes_received' in line:
            d={}
            for k in ('bytes_sent','bytes_received','segs_out','segs_in','bytes_retrans'):
                mm=re.search(rf'\b{k}:(\d+)', line)
                d[k]=int(mm.group(1)) if mm else 0
            mm=re.search(r'\brtt:([\d.]+)/', line);   d['rtt']=float(mm.group(1)) if mm else 0.0
            mm=re.search(r'\bminrtt:([\d.]+)', line); d['minrtt']=float(mm.group(1)) if mm else 0.0
            if pod and local and peer: out[(pod,local,peer)]=d
            local=peer=None
    return out

a_path,b_path,map_path,out_csv,meas,label = sys.argv[1:7]
A=parse(a_path); B=parse(b_path); M=load_map(map_path)
meas=float(meas)

def svc(addr):
    ip=addr.split(':')[0]
    return M.get(ip, ip)

edges=defaultdict(lambda: dict(sent=0,recv=0,so=0,si=0,rtt=[],minrtt=[],conns=0))
for key,b in B.items():
    pod,local,peer=key
    a=A.get(key)
    d=dict(sent=b['bytes_sent']-(a['bytes_sent'] if a else 0),
           recv=b['bytes_received']-(a['bytes_received'] if a else 0),
           so=b['segs_out']-(a['segs_out'] if a else 0),
           si=b['segs_in']-(a['segs_in'] if a else 0))
    if min(d.values())<0:      # 接続が張り直された(カウンタが巻き戻った)場合はBの全量
        d=dict(sent=b['bytes_sent'],recv=b['bytes_received'],so=b['segs_out'],si=b['segs_in'])
    src=M.get(pod,pod); dst=svc(peer)
    if src==dst: continue
    e=edges[(src,dst)]
    e['sent']+=d['sent']; e['recv']+=d['recv']; e['so']+=d['so']; e['si']+=d['si']; e['conns']+=1
    e['rtt'].append(b['rtt']); e['minrtt'].append(b['minrtt'])

rows=[]
for (src,dst),e in edges.items():
    tot=e['sent']+e['recv']
    rows.append((tot,src,dst,e))
rows.sort(reverse=True)
print(f"=== {label}: 接続ごとの実測(計測窓 {meas:.0f} 秒)===")
print(f"{'送信元':24s}{'→ 宛先':24s}{'送信MB':>9}{'受信MB':>9}{'合計MB':>9}{'segs_out':>10}{'segs_in':>10}{'rtt ms':>8}{'最小rtt':>8}{'接続':>5}")
with open(out_csv,'a',newline='') as f:
    w=csv.writer(f)
    for tot,src,dst,e in rows:
        rtt=sum(e['rtt'])/len(e['rtt']) if e['rtt'] else 0
        mrtt=min(e['minrtt']) if e['minrtt'] else 0
        print(f"{src[:22]:24s}{dst[:22]:24s}{e['sent']/1e6:9.2f}{e['recv']/1e6:9.2f}{tot/1e6:9.2f}"
              f"{e['so']:10.0f}{e['si']:10.0f}{rtt:8.2f}{mrtt:8.3f}{e['conns']:5d}")
        w.writerow([label,src,dst,e['sent'],e['recv'],e['so'],e['si'],round(rtt,3),round(mrtt,4),e['conns']])
