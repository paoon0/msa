---
name: microk8s-nightly-restart
description: MicroK8s が毎晩 2 回クラスタを自分で再起動している (2026-10-05 以降)。夜をまたぐ実験の点が欠ける・壊れる
metadata:
  node_type: memory
  type: project
  originSessionId: f19a71cf-0131-4423-8285-543cfa375857
  modified: 2026-10-21T01:46:51.221Z
---

journalctl で `apiserver-kicker` の "cert change detected" → kubelite・containerd 停止 → 全 Pod 再起動。
10/05 23:37 から毎晩 2 回、毎日約 10 分ずつ早まる (10/20 は 21:08 と 21:28)。直前に wlo1 の IPv6 一時アドレスが入れ替わる。

- SS mix-cpu2b (10/20): cyc2 の 2 台ブロックで発生 → 利用者が消え購入が全滅 → そのブロックを除外 (analyze_rho_ss.py)。
- 洗い出し済み (2026-10-22、km2/experiments/restart-audit.md、9/16 以降): 当たったのは 7 回。FOSE の値は無影響だが、9/2 の再起動で表 1 frontend+cart の 1 点が欠けていた (分母 19 の原因、アヌビス確認)。OB mix-cpu2・pdist-k3 分離・fixed4b-lb で計 4 点欠け、SS mix-cpu2b の 1 区間。再起動は遅くとも 8/18 から起きているが、9/15 以前の実験は調べない (ユーザ判断)。

**Why:** 測定スクリプトの「!! 再起動」検出で初めて見つかった。SS のスクリプトは検出するが、OB のドライバは再起動を数えていない。
**How to apply:** 止め方 = `sudo touch /var/snap/microk8s/current/var/lock/no-cert-reissue` (2026-10-27 13:07 設置済み。10/27 夜 19:58/20:18 ごろの予定時刻に再起動が出ないことを journalctl で要確認。最後の再起動は 10/26 20:08/20:28)。次に OB を回すときはドライバに Pod の RESTARTS 記録を足す (アヌビス提案)。 夜をまたぐ実験の前に、この時刻帯を確認する。止める手段 (no-cert-reissue ロック、IPv6 一時アドレス無効化) は管理者権限が要るのでユーザが行う。結果を集計するときは journalctl でこの時刻と計測窓の重なりを調べる。関連: [[rho-pair-selection-focus]]
