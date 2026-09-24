#!/usr/bin/env python3
"""FOSE2026 §5「affinity の順に並べると frontend+cart (4.1%)・frontend+checkout (2.5%) …」の再計算。

results-edge-pairs.csv (2026-09-08, edge-pairs.sh: 各 Pod にエフェメラルコンテナを入れ netns の `ss -tin` を
窓の前後で読み、接続ごとの差分を取ったもの) から、サービスペアごとの通信量が
サービス間通信全体に占める割合を出す。

  列: label, pod, peer, bytes_sent, bytes_received, segs_out, segs_in, rtt, minrtt, n
  - ラベル 購入100_閲覧0 (= buy(100) のみ) を使う
  - 各エッジは両端の Pod から観測されるので、(pod, peer) を正規化して片側だけ採る
  - peer が IP 直指定の行 (k6 等) は除外
  - ICTer と同じ「カプセル化ヘッダ込み」に揃えるため、ヘッダ込みバイト = ペイロード + 66 B × セグメント数
    (Ethernet 14 + IPv4 20 + TCP 32 (タイムスタンプ付き) = 66 B/セグメント)
  - 分母はサービス間エッジ 15 本の合計

使い方: python3 edge_pair_shares.py   (km2/experiments/ で実行)
"""
import csv, re, collections

HDR = 66
H = collections.Counter(); B = collections.Counter(); S = collections.Counter(); seen = set()
for r in csv.reader(open('results-edge-pairs.csv', encoding='utf-8')):
    if r[0] != '購入100_閲覧0':
        continue
    pod = re.sub(r'-[0-9a-f]+-[0-9a-z]+$', '', r[1]); peer = r[2]
    if re.match(r'^\d', peer):
        continue
    k = tuple(sorted((pod, peer)))
    if k in seen:
        continue
    seen.add(k)
    b = int(r[3]) + int(r[4]); s = int(r[5]) + int(r[6])
    B[k] = b; S[k] = s; H[k] = b + HDR * s
tb, ts, th = sum(B.values()), sum(S.values()), sum(H.values())

print(f"{'edge':44s} {'ヘッダ込':>8s} {'ペイロード':>8s} {'セグメント':>8s}")
for k in sorted(H, key=H.get, reverse=True):
    print(f"{'|'.join(k):44s} {100*H[k]/th:7.1f}% {100*B[k]/tb:7.1f}% {100*S[k]/ts:7.1f}%")

print("\n論文 §5 の6組 (ヘッダ込みバイト量の割合):")
for name, k in [('frontend+catalog', ('frontend', 'productcatalogservice')),
                ('frontend+reco', ('frontend', 'recommendationservice')),
                ('frontend+cart', ('cartservice', 'frontend')),
                ('frontend+checkout', ('checkoutservice', 'frontend')),
                ('checkout+email', ('checkoutservice', 'emailservice')),
                ('frontend+email', ('emailservice', 'frontend'))]:
    print(f"  {name:18s} {100*H.get(k, 0)/th:5.1f}%" + ('   (エッジなし)' if k not in H else ''))
