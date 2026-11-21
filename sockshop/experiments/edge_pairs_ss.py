#!/usr/bin/env python3
"""Sock Shop: 各 Pod の eth0 で録ったパケット (pcap) から、サービスペアごとの通信量を出す (2026-11-10)。
edge-traffic-ss.sh から呼ばれる。OB の km2/experiments/edge-traffic/edge_pairs.py と同じ目的だが、
OB は ss -tin の累計の引き算 (gRPC は接続張りっぱなし)、SS は HTTP で接続が開閉するのでパケットを全部数える。

数え方: 1 つのパケットは送り手と受け手の両方の Pod で録られるので、**送り手の Pod で録れた分 (送信元 = その Pod の IP) だけ**数える。
  src = 送り手のサービス、dst = 宛先 IP を IP 対応表で引いたサービス (Service の ClusterIP 宛ても Pod IP 宛ても同じ名前になる)。
  ip_bytes = IP パケットの全長 (IP + TCP/UDP ヘッダ込み、Ethernet ヘッダ 14 B は含まない)、payload_bytes = TCP/UDP の中身だけ。
  対応表に無い宛先は other。

使い方: python3 edge_pairs_ss.py <pcap のフォルダ> <IP 対応表> <出力 CSV> <ラベル>
  pcap のフォルダ: <pod 名>.pcap が並ぶ。IP 対応表: "IP 名前" の行 (Pod IP は deploy 名、ClusterIP は Service 名)。
  Pod の IP は IP 対応表に "pod:<pod 名> <IP>" の行でも入れておく (送り手の判定に使う)。
"""
import sys, os, struct, csv, collections, re

pdir, mapf, out, label = sys.argv[1:5]
ipmap, podip = {}, {}
for line in open(mapf):
    p = line.split()
    if len(p) < 2:
        continue
    if p[0].startswith('pod:'):
        podip[p[0][4:]] = p[1]
    else:
        ipmap[p[0]] = p[1]


def dep_of(pod):
    return re.sub(r'-[a-f0-9]{6,}-\w+$', '', pod)


agg = collections.defaultdict(lambda: [0, 0, 0])     # (src, dst, proto) -> [pkts, ip_bytes, payload_bytes]
span = {}
for fn in sorted(os.listdir(pdir)):
    if not fn.endswith('.pcap'):
        continue
    pod = fn[:-5]; me = podip.get(pod); src = dep_of(pod)
    data = open(os.path.join(pdir, fn), 'rb').read()
    if len(data) < 24 or me is None:
        print(f'  !! {pod}: pcap が空か IP 不明 ({len(data)} B)'); continue
    magic = struct.unpack('<I', data[:4])[0]
    en = '<' if magic in (0xa1b2c3d4, 0xa1b23c4d) else '>'
    nano = magic in (0xa1b23c4d, 0x4d3cb2a1)
    link = struct.unpack(en + 'I', data[20:24])[0]
    off, n, t0, t1, trunc = 24, 0, None, None, 0
    while off + 16 <= len(data):
        ts, tf, incl, orig = struct.unpack(en + 'IIII', data[off:off + 16]); off += 16
        pkt = data[off:off + incl]; off += incl
        if len(pkt) < incl:
            trunc += 1; break
        t = ts + tf / (1e9 if nano else 1e6)
        t0 = t if t0 is None else t0; t1 = t
        if link == 1:                        # Ethernet
            if len(pkt) < 14:
                continue
            et = struct.unpack('>H', pkt[12:14])[0]; ip = pkt[14:]
            if et == 0x8100 and len(pkt) >= 18:
                et = struct.unpack('>H', pkt[16:18])[0]; ip = pkt[18:]
            if et != 0x0800:
                continue
        elif link == 113:                    # Linux cooked
            ip = pkt[16:]
        else:
            continue
        if len(ip) < 20 or ip[0] >> 4 != 4:
            continue
        ihl = (ip[0] & 15) * 4; tot = struct.unpack('>H', ip[2:4])[0]; proto = ip[9]
        s, d = '.'.join(map(str, ip[12:16])), '.'.join(map(str, ip[16:20]))
        if s != me:
            continue                         # 受け取った分は送り手の Pod 側で数える
        if proto == 6 and len(ip) >= ihl + 13:
            pay = tot - ihl - (ip[ihl + 12] >> 4) * 4; pn = 'tcp'
        elif proto == 17:
            pay = tot - ihl - 8; pn = 'udp'
        else:
            pay = tot - ihl; pn = str(proto)
        a = agg[(src, ipmap.get(d, 'other'), pn)]
        a[0] += 1; a[1] += tot; a[2] += max(pay, 0); n += 1
    span[pod] = (t0, t1)
    print(f'  {pod}: 送信 {n} パケット、録れた時間 {0 if t0 is None else t1 - t0:.1f} s' + (f'  !! 途中で切れた' if trunc else ''))

new = not os.path.exists(out) or os.path.getsize(out) == 0
with open(out, 'a', newline='') as f:
    w = csv.writer(f)
    if new:
        w.writerow(['label', 'src', 'dst', 'proto', 'pkts', 'ip_bytes', 'payload_bytes'])
    for (s, d, p), (k, b, pl) in sorted(agg.items()):
        w.writerow([label, s, d, p, k, b, pl])

# 画面: ペア (向きをまとめる) ごとの IP バイト量と割合 (k6 と other を除いたサービス間の合計に対して)
pair, aside = collections.Counter(), collections.Counter()
for (s, d, p), (k, b, pl) in agg.items():
    if 'other' in (s, d) or 'k6load' in (s, d) or d.startswith('kube-system/') or s == d:
        aside[(s, d)] += b; continue
    pair[tuple(sorted((s, d)))] += b
tot = sum(pair.values()) or 1
print(f'  サービス間の合計 {tot / 1e6:.1f} MB (k6 ↔ front-end・DNS など kube-system 宛て・other は別に表示)')
for (a, b), v in aside.most_common():
    print(f'    (別) {a} → {b}  {v / 1e6:.2f} MB')
for (a, b), v in pair.most_common():
    print(f'    {a:>13} ↔ {b:<13} {v / 1e6:9.2f} MB  {v / tot * 100:5.1f}%')
