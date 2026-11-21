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

---

## 7. 追記 (2026-10-09) ρ（リクエスト型配合）まわりの探し方

- **古典の語彙が違う**: 「request mix」は新しい語。2005–2008 年は **"transaction mix" / "workload mix" / "capacity planning of multi-tier applications"**、
  VM 統合は **"correlation-aware" / "peak clustering" / "VM multiplexing"**、需要推定は **"resource demand estimation" / "service demand estimation"**。
  マイクロサービス語彙（pod, HPA, co-location）で引くと古典が出ない。語彙を時代ごとに変えて引く。
- **取得の実務**: ACM DL / Springer / ScienceDirect は WebFetch で 403 または認証リダイレクトになる。
  USENIX（legacy URL の full_papers/*.pdf）と arXiv は取れる。PDF は WebFetch が自動保存するので `pdftotext -layout` で抽出して grep するのが確実
  （WebFetch の要約は PDF バイナリを読めず失敗することがある）。
- **「ノード配置」と「Pod 内同居」を混同しない**: "co-location" "microservice" "Kubernetes" で出る大半は Pod を**どのノードに置くか**
  (scheduler) の研究で、本研究の Pod 内同居とは別軸。通信考慮配置 (NetMARKS, TraDE 等) もこちら。
- **ブログ・特許が混ざる**: WebSearch には特許（image-ppubs.uspto.gov）やブログが多く混ざる。書誌を採るのは arXiv/USENIX/DOI の実体に当たれたものだけ。
- 相関統合は **向きに注意**: VM 統合は「ずれた相手ほど得」、Pod 単位 HPA は「揃った相手ほど損なし」。逆向きなので類似語で混同しない。

---

## 8. 追記 (2026-10-19) 「特定のベンチマークアプリ (Sock Shop 等) の負荷シナリオ」を調べるとき

- **本文の「実験設定」節にしか書かれない**: abstract や検索スニペットに負荷の中身は出ない。arXiv の PDF を `curl -L https://arxiv.org/pdf/<番号>` で取り、
  `pdftotext` (レイアウト無し。2 段組は `-layout` だと文が崩れる) → `grep -n -i -E "locust|jmeter|k6|wrk|workload|users|requests per|trace|sock"` で実験節を引く。
  arXiv のメタデータ (`http://export.arxiv.org/api/query?id_list=<番号>`) の `journal_ref` / `comment` / `doi` で掲載先を確認できる (本文に載っていない場合が多い)。
- **ACM/Springer が 403 のとき**: 著者サイト PDF (例: dbermbach.github.io, cs.utsa.edu/~plama, continuity-project.github.io) か、EuropePMC の全文 XML
  (`https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML`、`-A "Mozilla/5.0"`) が取れる。WebFetch の要約は数字を取り違えうるので、必ず本文 XML/PDF で裏取りする。
- **修士論文・学位論文も当たる**: `"<ベンチマーク名>" merge microservices same container granularity` で USP の修士論文 (Buzato 2025) が出た。通常の論文検索では出ない。
  学位論文は `teses.usp.br` 等のリポジトリ PDF が直接取れる。
- **負荷の語彙**: 「ワークロード配合」は Sock Shop 周辺では **behavior mix / usage profile / operational profile / workload specification**
  (PPTAM, BenchFlow, Faban, WESSBAS の系譜、Avritzer・Camilli・van Hoorn)。"request mix" "browse buy ratio" では出ない。
  オートスケール系は **workload trace (WorldCup98 / Wikipedia / Alibaba)** で語り、リクエストの中身は書かない。
- **Sock Shop の別名に注意**: "Sock-Shop", "SockShop", "sock-shop", "Sock shop" の表記ゆれ。RCA 系 (Pham らの RCAEval 系) は「Sock Shop は 11〜15 サービス」と数が論文ごとに違う (13/14/15 の揺れ)。
- 「開ループ」の確認は `open-loop|closed-loop|Poisson|constant-arrival|arrival rate|think time` で grep。Sock Shop 周辺で明示するものは見つからなかった (2026-10-19 時点)。

---

## 9. 追記 (2026-10-19) 「測定環境 (CPU 周波数・ターボ・ガバナ) の扱い」を調べるとき

- **本文の「実験環境 / Methodology / Setup」の 1 文にしか出ない**。abstract や検索スニペットには出ないので、原典 PDF を取って `pdftotext` → `grep -n -i -E "turbo|dvfs|frequency scaling|governor|c-state|hyper-?thread|\bSMT\b|pstate|cpufreq|GHz"` が最も速い。
  2 段組でも `-layout` なしの素の抽出で十分拾える。ページ番号は `split('\f')` で数える (`pdftotext` は改ページを `\f` にする)。
- **直接 PDF が curl で取れた場所**: USENIX (`www.usenix.org/system/files/<conf><yy>-<author>.pdf`)、arXiv (`arxiv.org/pdf/<番号>`)、Cornell Delimitrou 研
  (`www.csl.cornell.edu/~delimitrou/papers/2019.asplos.parties.pdf` など `<年>.<会議>.<名>.pdf`)、Google 公開 (`static.googleusercontent.com/media/research.google.com/en//pubs/archive/43792.pdf` = Heracles)、
  SPEC ICPE 公式 (`research.spec.org/icpe_proceedings/2024/proceedings/p95.pdf`)、UMass LASS (`lass.cs.umass.edu/papers/pdf/…`)、MDU (`www.es.mdu.se/pdf_publications/<番号>.pdf`)、著者サイト (htor.inf.ethz.ch, pmctrack-linux.github.io)。
  ACM DL / ScienceDirect / TechRxiv は WebFetch・curl とも 403。
- **語彙**: 英語の「ターボを切る」は *disable TurboBoost / Turbo Boost off*、固定は *fixed frequency / userspace governor / performance governor*、省電力は *C-states / idle states / power management*。
  「周波数で利用率が歪む」は *frequency-invariant utilization* (Linux スケジューラ側の語)、*DVFS-aware service demand estimation* (性能モデリング側の語)、*APERF/MPERF*、*unhalted cycles* で引く。
  マイクロサービス語 (microservice, HPA, Kubernetes) と DVFS を掛けると査読論文は出ず、ブログ・特許・公式 doc が混ざる (特許 image-ppubs.uspto.gov は書誌に採らない)。
- **公式ドキュメントも一次資料になる**: Linux の `docs.kernel.org` (cgroup-v2 / schedutil / intel_pstate) は curl で HTML を取って、タグを除去して `grep` すると原文を確認できる。
  WebFetch の要約は "does not account for the frequency" のような核心の一文を言い換えるので、必ず curl で原文を確認する。
- **「周波数を固定する／しない」は論文の分野で作法が分かれる**: 遅延・ジッタ・オーバーヘッドを精密に測る系 (OSDI/NSDI の OS・ネットワーク系) は無効化を明記、
  ML ベースの資源管理・オートスケール系は何も書かない。母集団を選ぶときは分野を分けて数える。
- 方法論の文献 (再現性・報告) は **Hoefler & Belli (SC'15)**、**Papadopoulos ほか (TSE)**、**Maricq ほか (OSDI'18)** から芋づる式に辿る。

---

## 10. 追記 (2026-10-19) 「負荷の配合・強度の決め方 (workload mix / load level)」を調べるとき

- **語彙**: 英語の「配合」は *workload mix / request mix / transaction mix / operational profile*。「回帰で 1 リクエストあたりの CPU を出す」は *resource demand estimation / service demand estimation / utilization law regression*。
  「飽和点に対する割合」は *percentage of max load / saturation throughput / knee / calibration phase*。「共線性」は *multicollinearity / collinear workload classes*。
  `"request mix" "browse buy ratio"` ではほぼ出ない。*TPC-W browsing shopping ordering mix* と *demand estimation collinearity* が当たる。
- **著者名で引き違えやすい**: 『Kraft/Rolia の regression』は、Crossref では Kraft, Pacheco-Sanchez, Casale, Dawson (VALUETOOLS 2009)。Rolia は Rolia & Vetland (1995) と Kalbasi ほか (DEC)。**書誌は検索結果の記憶ではなく Crossref API で確かめる**:
  `curl -s "https://api.crossref.org/works?query.bibliographic=<題と著者>&rows=2&select=DOI,title,author,issued,container-title"`。DOI が分かっていれば `https://api.crossref.org/works/<DOI>`。有料かどうかは `https://api.unpaywall.org/v2/<DOI>?email=<メール>` の `is_oa`。
- **修士論文は共線性の議論が詳しい**: DEC の本体 (TSE 2012) は IEEE で取れないが、Kalbasi の修士論文 (Calgary, 2010) はカナダ国立図書館の PDF
  (`collectionscanada.gc.ca/obj/thesescanada/vol2/002/MR69450.PDF?is_thesis=1&oclc_number=806535411`) が curl で取れ、2.1–2.2 節に共線性の定義と対処法の比較がある。
- **Imperial の論文は Spiral の API で取る**: 検索結果の `spiral.imperial.ac.uk/entities/publication/<uuid>` を curl し、`bitstreams/<uuid>/download` を拾う。実体は `.../server/api/core/bitstreams/<uuid>/content`。bitstream が複数あり、片方は著者の顔写真 (JPEG) だったので `file` で PDF か確かめる。
- **ベンチマークの『配合』は README でなくコードにある**: DeathStarBench の比は `socialNetwork/wrk2/scripts/social-network/mixed-workload.lua` の `*_ratio` 変数 (raw.githubusercontent.com を curl)。
- **本の中身**: Jain の教科書は複製サイト (vdoc.pub) に第 1–3 章ほどだけある。第 17 章 (2^k 要因計画) は著者公開のチュートリアル資料 `https://www.cse.wustl.edu/~jain/tutorials/ftp/ied_tut.pdf` が取れる (証明書の都合で `curl -k` が要る)。引用の頁は実書籍で確認すること。
- **WebFetch は 403 になりやすい**: ResearchGate、ScienceDirect、CORE (Cloudflare)、Springer (認証リダイレクト)、ACM DL。arXiv・USENIX・SPEC (`research.spec.org`)・著者サイトは curl で取れる。取れないものは bib の note に『本文未読』と書く。
- **『検索要約の数字』は出典が混ざる**: Spinner らの『C={1,2,3}、U={20,50,80%}』は検索結果の要約に出たが、どの論文の記述か特定できなかった。要約の数字は**孫引き扱い**にして、本文で裏取りできるまで本文に書かない。

---

## 11. 追記 (2026-10-20) 「異なる型のリクエストを 1 つの負荷にまとめる／アプリ間で強度を揃える」を調べるとき

- **語彙**: 待ち行列の古典語で引く。*utilization law / operational laws / service demand / offered load / multiclass / bottleneck / saturation sector / population mix*。
  「CPU 重みの負荷」を直接言う語は無い (*weighted request rate* *CPU-weighted load* ではマイクロサービス論文は出ず、ブログが混ざる)。*request unit* は Cosmos DB のドキュメントが当たる。
  マイクロサービス側は *workload = request rate + request distribution over endpoints* の形で書かれる (COLA/Erlang)。
- **教科書は著者公開の章別 PDF が取れる**: Lazowska ほか *Quantitative System Performance* は `https://homes.cs.washington.edu/~lazowska/qsp/Images/Chap_NN.pdf` (NN=01〜19)。`pdftotext` (レイアウト無し) で grep できる。第 3 章=利用率の法則、第 5 章=限界、第 7 章=多クラス。
- **標準ベンチマーク仕様は本文を取る**: TPC-C 仕様 5.10 は Brown 大のコピー (`hstore.cs.brown.edu/.../tpcc_current.pdf`) が取れる。TPC-W は白書 (`tpc.org/tpcw/tpc-w_wh.pdf`、6 頁)。SPECweb2005 は `spec.org/web2005/docs/faq.html`。
- **古典の原典 (Denning & Buzen 1978、Zahorjan 1982) は ACM DL が HTML を返し取れない**。Unpaywall が OA と言っても実体は同じページ。教科書 (Lazowska) が基にしているので、教科書で内容を確認して原典は『書誌のみ』と記録する。
- **閉ループ前提の理論に注意**: 飽和セクタ (Balbo & Serazzi)・Anselmi & Cremonesi・balanced job bounds は**閉ループ (利用者数 N)**。k6 の開ループには半平面の共通部分で読み替える必要がある。
- WebSearch の要約は『〜と書いてある』と言い切るので、**必ず原典 PDF の該当節を grep して確認**する (今回、TPC-C の最小割合の数字と SPECweb の幾何平均は原文で一致を確認)。

---

## 12. 追記 (2026-11-10) 「Java 起動時 CPU × HPA」を調べるとき

- **語彙**: *JVM warm-up / JIT compilation / class loading / cold start / startup CPU burst / readiness probe initialDelaySeconds / startupProbe / cpu-initialization-period / runaway scaling*。学術に寄せると『auto-scaling benchmark pitfalls』『initialization overhead』で当たる (Dashtbani 2025 は題に Java が無く、本文の G1 に出る)。**題や abstract に JVM が無くても本文にある**ので、Sock Shop を使うオートスケール論文は pdftotext + `grep -i 'java\|jvm\|warm\|startup\|JIT'` で本文を掃く。
- 学術論文は少なく、検索結果の大半はベンダ・ブログ (StormForge、Azul、BlaBlaCar など)。『JVM 対策の総説』は学術では出ない。学術と技術記事は混ぜずに区別して書く。
- **K8s の挙動はドキュメントでなくソースで裏取り**: `https://raw.githubusercontent.com/kubernetes/website/main/content/en/docs/...md` と `https://raw.githubusercontent.com/kubernetes/kubernetes/master/pkg/controller/podautoscaler/replica_calculator.go` が curl で取れる (WebFetch は長いページを途中で切る)。`groupPods` が Ready/起動直後の扱いの実体。最終更新日は `api.github.com/repos/.../commits?path=...&per_page=1` で取る。
- **取れない**: Medium (Cloudflare で 403、curl も不可)、openjdk.org は WebFetch が 403 だが curl に User-Agent を付ければ通る。web.archive.org は WebFetch 不可。

---

## 13. 追記 (2026-11-10) 「HPA 論文が評価に使うベンチマーク OSS」を調べるとき

- **語彙**: *benchmark application / reference application / microservice benchmark / testbed / evaluated on*。アプリ名は表記ゆれが多い (Sock-Shop／SockShop／Sock Shop、Online Boutique／OnlineBoutique／Hipster Shop (旧名)、Train-Ticket／TrainTicket、HotelReservation／Hotel-Reservation／Hotel Reservation、Book Info／Bookinfo、Social-Network／SocialNetwork)。grep は `Sock.?Shop`、`Train.?Ticket`、`Book.?info` のように書く。
- **既存の調査 (サーベイ) では表が引けない**: Xu ほか "Auto-scaling Approaches for Microservice Applications: A Survey and Taxonomy" (arXiv:2507.17128) の表は手法の分類 (技術・指標・時期) で、**使ったベンチマークの列が無い**。論文ごとに実験節を読むしかない。
- **一番早い入口**: (1) **アプリ自身の GitHub README の「使われた論文」一覧** (TeaStore の README にある。TeaStore と HPA の論文はここから拾えた。通常の WebSearch では出なかった)。(2) Dashtbani & Tahvildari (arXiv:2510.02585) は『学術研究が使う公開ベンチ: Bookinfo／OB／Sock Shop／TrainTicket』と明言し、サービス数・言語も表にしている。(3) COLA の表 1 (5 アプリ・サービス数・削減率)。
- **arXiv の検索 API は https が要り、`-L` を付ける** (`http://` は 301 で空に見える)。`search_query=all:TeaStore AND all:autoscaling` のような AND 検索は取りこぼしが多い (0〜1 件)。**メタデータは `id_list=<番号>` が確実** (journal_ref／doi／comment)。comment に "accepted at OSDI '20" 等が入る。
- **書誌は Crossref で確認**: `https://api.crossref.org/works/<DOI>` で題・巻号ページ・著者順。ScalerEval は arXiv と Crossref で著者順が違った。検索要約が言う掲載先は鵜呑みにしない (COLA の arXiv は、Crossref では別題の EuroSys '24 Erlang が同著者で出る。同一内容かは本文照合が必要)。
- **WebSearch の要約は、本文と食い違うことがある**: BASE (arXiv:2402.12962) は要約が『OB・SS・TT を含む 5 ベンチ』と書いたが、取得した v2 の本文に benchmark 名が 1 つも出なかった。**必ず PDF を grep**。grep には Python で改行を潰して前後の文脈を出すスクリプト (`re.sub(r'\s+',' ',text)` → `re.finditer`) が速い。`grep -o` に `.{250}` を付けると ugrep が複雑さの上限でエラーになる。
- **アプリの特性は『リポジトリのファイル』で確認できる**: (1) 言語 = GitHub の `git/trees/<branch>?recursive=1` を取り、`pom.xml`／`go.mod`／`build.gradle`／`package.json` の有無でサービスごとに数える (Train-Ticket は `ts-*` 47 ディレクトリ中 42 が `pom.xml`、OTel Demo の recommendation は今は gradle=JVM)。(2) 宛先の変更しやすさ = `.env`、`config.json`、`dialer.go`、`start.sh`、`server.xml`、manifest の env を読む (TeaStore の Tomcat 待受は共有ベースイメージで 8080 固定、Hotel Reservation は Consul 経由)。(3) 保守 = `commits?per_page=1` の最終 commit 日と `archived`。(4) 負荷の型 = `locustfile.py`／`*.lua`／`mixed-workload*.lua`。
- **ライセンスは README と LICENSE ファイルが食い違うことがある** (DeathStarBench: README は GPL v2、LICENSE は Apache 2.0、GitHub API は Apache-2.0)。両方を見る。
- **取れなかったもの**: par.nsf.gov の PDF (壊れていた)、TU Darmstadt の `get_attach.php` (接続不可)、途中で切れる PDF は `-m 60` の時間切れで先頭だけ取れる (grep は可能だが全文ではない)。J-STAGE の PDF は `https://www.jstage.jst.go.jp/article/<誌>/<巻>/<号>/<論文ID>/_pdf` を `-A "Mozilla/5.0"` で curl すると取れた。

## 14. 追記 (2026-11-12) 「特定アプリ (HR 等) × 水平スケール」を調べるとき

- **arXiv API の `all:` 検索は abstract・題しか引かない** (全文ではない)。abstract に "Hotel Reservation" と書かない論文は拾えない。HR の使用有無は、候補の PDF を `pdftotext` して `grep -ci hotel` で数えるのが速い (0 件ならそのアプリは不使用と判断してよい。表記ゆれ "HotelReservation"・"HR benchmark" にも `hotel` で当たる)。
- 検索エンジンの要約は設定の数値 (HPA の目標値など) を作り話にしがち。MDPI・ACM DL・IEEE は 403 になるので、**要約の数値は本文で裏取りするまで『未確認』と書く**。
- 本文が取れない論文は、著者の GitHub の README (artifact) で使ったアプリと手法の骨格は確認できる (例: Erms)。ただし論文本文の代わりにはならない。確認度は『著者 README まで』と書く。
- 垂直 (cgroup・docker update) と水平 (レプリカ数) の区別は、本文の "vertical"・"replica"・"cgroup"・"docker update" を grep すると早い。related work の一括表現 ("horizontal or vertical scaling") を手法の説明と取り違えない。
- 「ベンチマーク OSS が水平スケールの評価に向くか」は COLA の評価の節 (Microservice Applications の段落) に理由が書かれている (DSB は VM 台数と割り当てが固定)。
- 有効だった連鎖: 「HR + HPA」→ 論文 A の related work の列挙 (SHOWAR/PEMA/ATOM) → 各 PDF を grep。ヒットが少ない主題では、候補を列挙して grep で足切りするほうが検索語を変えるより効率がよい。

## 追記 (2026-11-12): HPA 論文の『評価対象システム』を集めるとき
- arXiv API は **https://export.arxiv.org/api/query** (http では空の応答が返った)。`abs:"Horizontal Pod Autoscaler"` や `abs:HPA AND abs:Kubernetes AND abs:microservice` が有効。ただし abstract 検索なので、本文にしかアプリ名が出ない論文 (Train-Ticket 等) は 0 件になる。→ 候補を取ったら PDF を pdftotext して `HPA|KHPA|Horizontal Pod`・アプリ名・`Locust|k6|JMeter`・`EKS|GKE|nodes` を grep する。**2 段組の PDF は `pdftotext -layout` だと文が混ざる。-layout を付けず通常モードで取る。**
- 『HPA』の語が本文に **0 件** なら HPA 論文に数えない (DeepScaler、FIRM がそうだった)。基準が『K8s autoscaler』と書かれていても垂直 (割り当て量の更新) のことがある (Autothrottle の K8s-CPU)。
- 著者公開の PDF は Unpaywall (`api.unpaywall.org/v2/<DOI>?email=...`) の oa_locations から取れる (IEEE Access の Serracanta は UPC のリポジトリ)。imec／大学リポジトリの `handle` ページから `bitstreams/.../download` を拾える。
- WebSearch は Smart HPA／ScalerEval／PBScaler／STaleX が繰り返し上位に出て標本が偏る。**PMC (Sensors)、Research Square、arXiv の journal_ref を見る検索語 (『experimental evaluation of HPA』『stability』『CPU limits』) で別の層が出る。**

## 追記 (2026-11-13): pdftotext の失敗に注意
- `pdftotext a.pdf out.txt || pdftotext b.pdf out.txt` のように同じ出力ファイルへ上書きする書き方は、**壊れた PDF で失敗すると前の論文のテキストが残る**。別の論文の内容を読んだまま気づかない事故が起きかけた (SHOWAR が CPU-Limits のテキストになっていた)。出力名は論文ごとに分け、先頭の題と著者を目視で確認する。
- 2 段組の PDF は `-layout` だと行が混ざって検索しにくい。結果の数値探しは `-layout` なしで `tr -s ' \n' ' '` で 1 行にして grep -P で前後を切り出すと読める。

## 設定の「記載なし」を確かめるときの grep (2026-11-16)
- 論文の設定の記述 (HPA の対象・入口の台数・min/max・接続数) は**本文の 1〜2 文にしか無い**ことが多い。`pdftotext` (`-layout` なし = 2 段組が崩れにくい) に変換し、`nginx|stateful|mongo|redis|memcache|jaeger|keep-alive|connection|minReplicas|maxReplicas|exclud|helm|manifest|stabiliz|HPA|threshold|limit|wrk2|locust|replica` で grep。ヒットした行の前後 20 行を読む。結果は §13.13。
- 「K8s 基準 (K8s-CPU 等)」が HPA かは本文で確かめる。Autothrottle は CPU limit を決める垂直方式で HPA ではなかった。
- 評価のアプリ名も本文で確かめる (COLA は SN を使っていなかった)。

## (追記 2026-11-17) HPA の「測り方」が似た研究を探すとき (詳細は related_work.md §13.14)

- **arXiv の abstract 検索はほぼ効かない**。`Horizontal Pod Autoscaler` × `evaluation/threshold` は既知の 5 本程度に収束し、`settling` `control theory` `empirical study` `load test` は 0 件。HPA の特性評価は**査読誌 (Sensors, IEEE Access, AMCS, Cluster Computing)・修士論文 (DiVA)・GitHub** に散らばる。
- 効いた語: 『HPA performance evaluation increasing load replicas response time』(Nguyen 2020、Casalicchio、Electronics 2024)、『relative absolute metrics autoscaling』(Casalicchio)、『multilayered autoscaling performance evaluation』(Podolskiy)、『open-loop constant request rate replica count repeated runs』(**GitHub の学部論文リポジトリが出る**)、『Theodolite scalability benchmarking』(固定台数の方法論)。
- 効かなかった語: 『settling time』『time to stabilize』『impact of CPU requests on HPA』(実務ブログのみ。requests を振った実験論文は出ない)、『stabilization window sync period empirical』(同)。
- **MDPI (mdpi.com) は curl・WebFetch とも 403**。PMC に載る Sensors 2020 は取れるが、Electronics は取れない。Europe PMC・PMC で探すか、著者版を探す。ブラウザを装う User-Agent 偽装は権限で拒否される (やらない)。Unpaywall に連絡先メールを付ける照会もしない。
- 修士論文は DiVA (diva-portal.org) の FULLTEXT01.pdf が直接取れる。HPA の特性評価 (負荷水準 × 立ち上げ時間、各 3 回) の例が見つかった。
- スクラッチパッドの `pdf/`・`flat/` に過去に取った PDF の txt がある場合は、まず grep する (同じ論文を取り直さない)。
