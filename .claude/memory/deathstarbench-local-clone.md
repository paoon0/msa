---
name: deathstarbench-local-clone
description: DeathStarBench (Social Network) のローカルクローンは研究リポジトリの外 ~/ダウンロード/DeathStarBench に socialNetwork だけ置いてある
metadata:
  node_type: memory
  type: reference
  originSessionId: 79ed5039-ad0e-4c07-9dc8-15de8c3cc2cf
  modified: 2026-11-14T06:15:22.061Z
---

2026-11-14 にユーザの選択で、`delimitrou/DeathStarBench` を **研究リポジトリの外** `/home/mizuki/ダウンロード/DeathStarBench` にクローンした。
- 範囲は sparse checkout で `socialNetwork/` だけ (HR の `hotelReservation/` は入っていない。見るときは `git sparse-checkout add hotelReservation`)。
- `--depth 1`、commit 6ecb09706140f8730b5385c08f1386c654c3c526 (2024-06-27)。
- 研究リポジトリに入っていないので、もう 1 台のマシンには git で同期されない。実験で使う部分は Sock Shop と同じく `msa/socialnetwork/upstream/` へ無変更でコピーしてから手を入れる想定 (未実施)。
- 宛先・ポート・Helm の調査結果は `km2/approach/related_work.md` §13.3 の SN の追記。

- **2026-11-14 立ち上げ試験 (ユーザ指示)**: `microk8s helm3 template sn socialNetwork/helm-chart/socialnetwork --namespace sn-test > ~/ダウンロード/DeathStarBench/rendered/sn-test.yaml` → namespace `sn-test` に apply。27 Deployment 全て Ready (約 11 分、ほぼイメージ取得、再起動 0)。nginx のフォーク (dimoibiehg) はユーザ判断で既定のまま (a)。register・home-timeline read は 200。compose は投稿自体は保存されたが HTTP 500「ZADD: no key specified」= フォロワー 0 のまま (social graph 未投入) と推定、未確認。同日、ユーザ指示で exp の SS Deployment 9 個を削除 (Service は OB/SS とも残置、promq は Completed で残置)。
- **500 の正体を確認**: socfb-Reed98 を投入 (公式 init_social_graph.py と同じ payload を標準ライブラリで送るスクリプト、scratchpad の sn_init_graph.py。python3-venv が無く aiohttp を入れられなかったため)。ユーザ 962 人は全て 200、フォローは 10 分で 21,232 / 37,624 本 (約 35 本/s) まで入れて中断。フォロワーのいる username_0 の投稿は 200 でフォロワー user 15 のホームタイムラインに届いた。フォロワー 0 の testuser1 は再び 500「ZADD: no key specified」→ **フォロワー 0 のユーザが投稿すると 500 になる** (SN の仕様。負荷をかけるときは全ユーザにフォロワーがいるグラフを使う必要)。
- **2026-11-14 ログ点検**: 27 Pod 全て Running・再起動 0・Warning イベント 0。見つかったもの: (1) 起動直後に MongoDB 未起動で索引作成を約 93 回再試行 (各サービス) → その後は正常に応答、起動順の問題で害なし。(2) **username_1 の登録が失敗していたのに register は 200 を返した** (先に手で作った testuser1 が user_id=1 を使っていて重複キー E11000)。そのため username_1 を含むフォロー 96 件が「not registered」で失敗 → **SN の register の 200 は成功の証拠にならない**、件数は MongoDB で数える (user 数 962 = testuser1 込み・username_1 抜け)。きれいに入れ直すなら DB を空にしてから testuser1 を作らずに投入。(3) ZADD 500 が 2 件 (フォロワー 0 の投稿、既知)。(4) トレースの送信失敗 (Could not send span、接続拒否) = 計測用の記録が送れないだけでアプリの応答には無関係、未調査。
- **2026-11-14 HPA 機能確認 (ユーザ指示)**: chart の HPA は memory 60% も入り DB まで対象になるため、処理用 12 サービスだけ CPU 60%・1–5 台で apply (`rendered/sn-hpa-cpu60.yaml`)。k6 読み取り 30→300 回/s。HPA は動く (nginx・user-timeline 1→2→1) が、**nginx の 2 台目に k6 の keep-alive 接続が回らず CPU 0m** → 平均 50% で頭打ち、105 回/s しか出ない。記録は `rendered/hpa-test/`、論文メモは related_work.md §9.25。HPA・Job は sn-test に残置。
- **2026-11-15 公式 wrk2 でも再現**: クラスタ内の作業用 Pod `wrk2` (ubuntu、sn-test) で DSB の wrk2 をビルド (LuaJIT は submodule 2090842 を別取得)。mixed-workload 300 回/s → 到達 38.6 回/s、nginx 2 台目は片方だけ働く (17:52 に入れ替わり、原因未確認)、他 11 サービスは 1 台のまま。記録 `rendered/hpa-wrk2/`、§9.25。
- **2026-11-16 案 B (ユーザ選択「Bでいい」)**: k6 で毎回接続を張り直す + 公式 mixed を書き写し (`rendered/hpa-k6b/`)。nginx 1→5 台 (上限) で全台に仕事が回った = 振り分けは直る。ただし到達 57 回/s、nginx 全台が絞られ上限 5 台で頭打ち、1 回あたり nginx CPU 約 2.5 倍 (推定)。nginx の keepalive は DSB が意図的に長い (nginx.tpl 40–46 行 keepalive_requests 100000、「実験中は切らない」チェックリスト)。

関連: [[softirq-cpu-metric]] [[grpc-pinning-imbalance]]
