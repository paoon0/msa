---
name: related-work-coloc
description: コンテナ同居/統合の先行研究と「単一ノードで差が出ない」文献的説明
metadata: 
  node_type: memory
  type: reference
  originSessionId: 39d0ddee-e91c-4bec-8ffc-4b7d7fde070b
---

本研究(K8s Pod 同居で資源効率↑)の先行研究調査(2026-06-15)。全文は `km2/approach/related_work.md`。

**直接の先行研究:**
- **Wickramanayaka, Keppitiyagama, Thilakarathna (2022)** "Communication-Affinity Aware Colocation and Merging of Containers", IJ Advances in ICT for Emerging Regions 15(3), DOI 10.4038/icter.v15i3.7251(OA)。ほぼ同一テーマ。3段階 Spreaded(overlay K_o)→Colocated(bridge K_b)→Merged(loopback K_l)、不等式 K_l<K_b<K_o。Binary Knapsack で配置。Docker Swarm + Sock-Shop。tcpdump で**通信バイト量(affinity)**を計測。colocation で52〜57%減、merging で+13%、計58.5%減・実行時間13.4%短縮。
- **Alvaro et al. (2024)** "NotNets: Accelerating Microservices by Bypassing the Network" arXiv:2404.06581。CPU サイクルの**25〜40%しか業務ロジックに使われない**(残りは通信: serialization/HTTP/gRPC core/kernel)。CXL 共有メモリで RPC をネットワークバイパス→echo レイテンシ約1桁減。

**最重要の示唆 = なぜ単一ノードで差が出ないか:** 大きな差は overlay の有無(K_o→K_b, 約52〜57%)で生まれ、bridge→loopback(K_b→K_l, 約13%)は小さい。Suo et al.(2018 INFOCOM)実測: overlay は host比スループット82.8%減。**本研究の単一ノード・Envoy無しでは overlay が無く、測れるのは一番小さい K_b→K_l 差だけ**→ CPU/req 差がノイズ床に埋もれるのは文献的に当然。有意差には ①マルチノード+CNI overlay か ②高負荷・多反復で小差を精密計測、が必要。

**差別化候補:** K8s Pod 同居 = コンテナ分離を保ったまま loopback を得る(ICTer の colocate と merge の中間状態)を、**CPU/req=資源効率**で定量化する点が空白。

**★勝てる軸(2026-06-15, ユーザ方針「Pod集約に有利な結果なら何でも可」):サービスメッシュのサイドカー税削減。** Envoy は 1 Pod に 1 個注入(~0.35〜0.6 vCPU+40〜72MB/1000RPS、アイドルでも~10m+50MB/Pod)。2サービスを1 Podに集約=Envoy 2→1。さらに同一Pod内 localhost は Istio iptables 捕捉から除外され両側 Envoy をバイパス(2 proxyホップ消滅)。桁の裏付け=アンビエントメッシュ動機(70 Pod でサイドカー約14 vCPU vs ztunnel 5〜10、L4 で CPU約73%減、p90 0.16ms vs 0.63ms)。計測手法引用=MeshInsight "Dissecting Service Mesh Overheads" arXiv:2207.00592。**今まで差が出なかった最終理由=メッシュ未注入で削るべき Envoy 税が無かった。** リポジトリは `istio/` で注入可能。最小実験: exp に istio-injection=enabled → 分離(Envoy2枚) vs 同居(Envoy1枚+localhostバイパス)を同一負荷で 総CPU/メモリ/p90・p99 比較。overlay 不要・単一ノードで大差の見込み。主張=「Pod集約=アンビエントメッシュのアプリ層版」。全文 km2/approach/related_work.md。

**引用すべき先行研究(全文は km2/approach/related_work.md):** B群=マイクロサービス粒度問題(Hassan 2020 SPE/arXiv:1903.11665 systematic mapping=**精読相当完了 2026-06-16**、空白「粒度適応のコスト・利益の動的評価」を明記=本研究が埋める; Hassan 2022 SPE DOI:10.1002/spe.3069 Systematic Scalability Analysis=定性フレームワーク止まり=空白未充填; Microservices Granularity vs Performance 2017)=定性的のみで未定量=空白確定。C群=オートスケーリング(Survey arXiv:2507.17128; Smart HPA arXiv:2403.07909; COLA arXiv:2112.14845=別Pod前提)=背景であり競合ではない。D=HPA ContainerResource(v1.30)=同居コンテナを個別スケールできる新機能(背景)。**2026-06-16 空白確認済み: 「K8s Pod 同居が資源効率・性能に与える影響を、分離を保ったまま CPU/req で定量化」研究はヒットなし=空白実在。残タスク: IEEE/ACM DL横断検索。**

関連: [[coloc-resource-efficiency-study]] [[exact-window-measurement]]
