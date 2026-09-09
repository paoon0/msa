---
name: edge-traffic-measurement
description: 【2026-09-08】サービス間通信量をエッジ単位で実測。上位2本で6割超、2位はcatalog↔reco(frontend経由しない)。★ヘッダが通信量の49%。★softirq予測はバイトでなくセグメント数
metadata:
  type: project
---

**資産: `km2/experiments/` の `edge-pairs.sh`(全Podにエフェメラルコンテナを入れ netns から `ss -tin` を読む)/ `edge-pairs-only.sh`(観測コンテナ導入済み用)/ `edge_pairs.py`(スナップショット2枚の差分)/ `results-edge-pairs.csv`。Pod単位版は `edge-traffic.sh` + `edge_traffic_row.py` + `results-edge-traffic.csv`。索引は summer2026/EXPERIMENTS.md。**

## 測り方
分離(normal)・全サービス1台固定・HPA無し・枠はマニフェストのまま。**購入型のみ**と**閲覧型のみ**を別々に流す(k6 の `RATE=0` で閲覧だけ流せるよう `checkout.js` に分岐を追加)。
- **Pod単位**: cAdvisor の `container_network_*`。ヘッダ込みの実線量。閲覧200と閲覧100の**差分**でプローブ等の定常分を除去。
- **ペア単位**: エフェメラルコンテナ(`kubectl debug --image=nicolaka/netshoot -c netprobe`)は Pod の netns を共有するので `ss -tin` が読める(**sudo 不要**)。窓の前後でスナップショットを取り差分。**各エッジが両端から観測され 0.1〜0.3% で一致**(検算になる)。

## ★実測(購入1周あたり、ペイロード)
| エッジ | B | シェア | セグメント | ヘッダ込B |
|---|---|---|---|---|
| **frontend↔productcatalog** | **5410** | **34.4%** | 98.6 | 11916 |
| **productcatalog↔recommendation** | **4428** | **28.1%** | 18.6 | 5654 |
| currency↔frontend | 1231 | 7.8% | 21.0 | 2617 |
| cart↔redis | 846 | 5.4% | 11.3 | 1592 |
| frontend↔reco | 686 | 4.4% | 11.8 | 1463 |
| 以下 cart↔frontend 507 / checkout↔shipping 425 / checkout↔frontend 407 / cart↔checkout 345 / checkout↔catalog 307 / checkout↔email 287 / checkout↔currency 284 / ad↔frontend 217 / checkout↔payment 188 / frontend↔shipping 179 |||||
| **合計** | **15748** | | **226.2** | **30674** |

閲覧1回あたりは合計4495B・66.8セグメント。上位2本で **74.4%**。

## ★発見
1. **上位2本で6割超**(購入62.5%/閲覧74.4%)。残り13本の合計より多い。
2. **2位が catalog↔reco = frontend を経由しないエッジ**。呼び出しは3回/周だけだが `ListProducts` が全9商品を返すため **1回1477B**(frontend→catalog の GetProduct は 49B/回)= **30倍重い**。
3. **ヘッダが通信量の49%**(購入・閲覧とも)。gRPCメッセージが小さく数が多いため。frontend↔catalog はヘッダ(6506B)がペイロード(5410B)を上回る。
4. ★**softirq の予測にはバイト数でなくセグメント数を使うべき**。frontend↔catalog はセグメントシェア43.6%×サービス間割合0.49=**21.4%**で実測 −22.5% と一致。catalog↔reco はバイト28%だがセグメント8%で、実測削減も5〜6%。**「削減はバイト寄り」という旧見立ての逆転**([[softirq-cpu-metric]] の発見1を要訂正)。
5. **k6↔frontend が全通信の約半分**(48〜52%)。束ねても消せないので、softirq削減の上限を決める。
6. `minrtt` はどのエッジも 0.006〜0.018ms とほぼ同じ。負荷時 `rtt` は 4.03〜8.99ms と2倍以上開くが、これは伝送でなく**相手の応答待ち**。

## ★呼び出しグラフの訂正(実測で判明)
- **`POST /cart` は 302 リダイレクトを返し k6 が追う**ので、購入1周は実際には**4回のページ読み込み**(3回でない)。追加で走る `GET /cart`(viewCartHandler)が getCurrencies/getCart/**getRecommendations**/**getShippingQuote** 等を呼ぶ。
- **frontend は shipping を直接呼ぶ**(カートページの送料見積)。「shipping を呼ぶのは checkout だけ」は誤り。
- 結果 **recommendation は1周に3回呼ばれる**(商品/カート/注文完了ページ)。

## 実装上の罠
**`kubectl exec ... > file` は出力が空になる**(エラーも出ない)。`| cat >> file` とパイプを1段挟めば通る。2026-09-08 に踏んで最初の走りが全滅した。
`ss` のアドレス表記は `[::ffff:10.1.98.29]:47106` と `10.1.98.37:57126` の2形式が混在する。両方に対応が必要。
エフェメラルコンテナは**後から削除できない**(Podを作り直すまで残る)。

関連: [[softirq-cpu-metric]] [[bundling-three-terms]] [[coloc-bundling-decision-rule]]
