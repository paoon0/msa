# 先行研究の探し方 (search_tips)

> 注記: 本ファイルは git 未追跡のまま誤って削除され、**元の本文は失われた**。
> 以下は Claude のメモ([[related-work-coloc]])に残る
> 実際の探索履歴・語彙・空白確認の経緯から **2026-06-16 に再構成**したもの。
> 元ファイルと細部が異なる可能性がある。以後は必ず `git add` してコミットすること。

本研究(K8s Pod 同居が資源効率・性能に与える影響の定量化)を念頭に、
先行研究を**漏れなく・効率よく**探し、「空白(gap)」を確定させるための手順をまとめる。

---

## 0. 大前提 — 日本語ではなく英語で探す

学術論文はほぼ英語。日本語検索では先行研究はほぼ出ない。
まず**研究テーマを英語キーワードに分解**してから探し始める。

本研究の核となる英語語彙:
- co-location / colocation, container, pod, sidecar
- microservice(s), granularity, decomposition, merging
- autoscaling / auto-scaling, HPA (Horizontal Pod Autoscaler), replica
- resource efficiency, consolidation, bin packing
- workload correlation / anti-correlation, demand correlation
- service mesh, Istio, Envoy, overhead

---

## 1. どこを探すか(データベース)

| ソース | 用途 | URL |
|---|---|---|
| **Google Scholar** | 最初の網羅検索・被引用数・"Cited by" 追跡 | scholar.google.com |
| **arXiv** | プレプリント(システム系は arXiv が早い) | arxiv.org |
| **IEEE Xplore** | INFOCOM / ICDCS など主要会議 | ieeexplore.ieee.org |
| **ACM Digital Library** | SoCC / SIGCOMM / EuroSys など | dl.acm.org |
| **DOI 直引き** | 既知論文の確定版 | doi.org/<DOI> |
| **Connected Papers** | 1本を起点に関連論文を可視化 | connectedpapers.com |
| **Semantic Scholar** | 引用グラフ・TLDR 要約 | semanticscholar.org |

> 本研究で実際にヒットした主要会議: INFOCOM(Shen 2014), SIGCOMM(Canal Mesh 2024)。
> arXiv 経由: NotNets(2404.06581), COLA(2112.14845), MeshInsight(2207.00592),
> Autoscaling Survey(2507.17128), Smart HPA(2403.07909), Hassan(1903.11665)。
> OA ジャーナル: ICTer (DOI 10.4038/icter.v15i3.7251)。

---

## 2. 検索クエリの組み立て方

### 2.1 コア概念 × 切り口 の掛け算で探す
テーマを「コア概念」と「切り口」に分け、組み合わせて複数回検索する。

```
("container" OR "pod") AND ("colocation" OR "co-location" OR "merging")
("microservice") AND ("granularity" OR "decomposition") AND ("performance" OR "cost")
("kubernetes" OR "HPA") AND ("autoscaling") AND ("replica" OR "container resource")
("VM" OR "workload") AND ("consolidation") AND ("correlation" OR "anti-correlation")
("service mesh" OR "sidecar" OR "envoy") AND ("overhead")
```

### 2.2 演算子の活用(Google Scholar / 一般)
- `"..."` … 完全一致(フレーズ固定)
- `OR` … 同義語をまとめる(必ず大文字)
- `-word` … 除外
- `site:arxiv.org` / `filetype:pdf` … 範囲を絞る
- 期間フィルタ … 直近5年に絞って最新動向、無制限で古典(seminal)を拾う

### 2.3 「自分の貢献に当たる語」を必ず一度は単独で検索
本研究の固有の組み合わせ:
```
"pod" "colocation" "autoscaling" "correlation"
"replica coupling" microservice
"granularity" "dynamic" cost benefit microservice
```
→ これでヒットが**無い**ことが、空白(gap)実在の一次証拠になる。

---

## 3. 1本見つけたら横へ広げる(スノーボーリング)

良い論文を1本見つけたら、芋づる式に広げるのが最も効率的:

1. **後ろ向き(backward)**: その論文の **References(参考文献)** を辿る → 古典・基礎へ。
2. **前向き(forward)**: Google Scholar の **"Cited by"** を辿る → その後の発展・最新へ。
3. **同著者**: 著者名で検索(例: Hassan は粒度問題で複数本 → 2020 と 2022)。
4. **Connected Papers / Semantic Scholar** で引用グラフを可視化し、クラスタを把握。

> 本研究では Hassan(2020 → 2022)、VM 統合系(Shen → Kim → Tetris)を著者・引用で芋づる展開した。

---

## 4. 取捨選択 — どう仕分けるか

見つけた論文は「自分の研究との関係」でグループ分けする(本研究の例):

- **直接の先行研究**: コンテナ同居・統合そのもの(ICTer 2022 / NotNets 2024)。本研究の起点。
- **B群 = 空白を埋める対象**: マイクロサービス粒度(定性的のみ・未定量)。
- **C群 = 背景**: オートスケーリング一般(競合ではない)。
- **D = 背景**: HPA ContainerResource(v1.30)。同居コンテナを個別スケールできる新機能。

各論文について最低限メモすべき項目:
- 何を主張し、どう測ったか(指標・環境)
- 本研究と**どこが同じで、どこが違うか**
- 引用するなら A/B/C/D のどれか

---

## 5. 「空白」を主張として確定させる手順

1. コア語彙 × 切り口で**複数クエリ**を回し、ヒットを A〜D に仕分ける。
2. 自分の固有の組み合わせ(§2.3)で検索し、**該当なし**を確認する。
3. 近い研究について「なぜそれが空白を埋めていないか」を一文で言えるようにする
   (例: 「定性的で未定量」「別 Pod 前提で結合問題が対象外」)。
4. IEEE Xplore / ACM DL でも**横断検索**して、arXiv/Scholar の漏れを潰す。
5. 仕分け結果と空白の根拠を `related_work.md` に記録する。

> 2026-06-16 時点の結論: 「Pod 同居が資源効率・性能に与える影響を、分離を保ったまま定量化」は
> ヒットなし = **空白実在**。残タスク: IEEE/ACM DL 横断検索。

---

## 6. 実務メモ

- 見つけた論文は **DOI か arXiv 番号**で記録する(URL は切れる)。
- PDF とメモは**必ず git にコミット**する(未追跡のまま放置しない ← 今回の教訓)。
- アクセスできない有料論文は、著者サイト・arXiv 版・所属機関のプロキシを当たる。
