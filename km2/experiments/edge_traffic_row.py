#!/usr/bin/env python3
"""edge-traffic.sh から呼ばれ、Prometheus の応答を1行ずつ CSV に落とす。
Pod 名のハッシュ部分は落として、サービス名で揃える。"""
import os, sys, json, csv, re

arm, csv_path, cyc, rate, brw, meas = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], float(sys.argv[6])

def series(env):
    raw = os.environ.get(env, "")
    out = {}
    try:
        for r in json.loads(raw).get("data", {}).get("result", []):
            pod = r["metric"].get("pod", "?")
            out[pod] = float(r["value"][1])
    except Exception:
        pass
    return out

rx, tx, rp, tp = series("RX"), series("TX"), series("RP"), series("TP")

summary = {}
try:
    summary = json.loads(os.environ.get("SUMMARY", "") or "{}")
except Exception:
    pass
iter_rate = summary.get("iter_rate", 0) or 0
browse_rate = summary.get("browse_rate", 0) or 0

def svc(pod):
    # frontend-57fd4d6f4c-84rth → frontend
    return re.sub(r"-[0-9a-f]{6,10}-[0-9a-z]{5}$", "", pod)

pods = sorted(set(rx) | set(tx) | set(rp) | set(tp))
with open(csv_path, "a", newline="") as f:
    w = csv.writer(f)
    for p in pods:
        w.writerow([cyc, arm, rate, brw, round(iter_rate, 1), round(browse_rate, 1), svc(p),
                    round(rx.get(p, 0)), round(tx.get(p, 0)),
                    round(rp.get(p, 0)), round(tp.get(p, 0))])

tot_rx = sum(rx.values()); tot_tx = sum(tx.values())
work = (iter_rate + browse_rate) * meas
print(f"  -> 購入={iter_rate:.1f}/{rate} 閲覧={browse_rate:.1f}/{brw} | "
      f"名前空間の受信 {tot_rx/1e6:.1f} MB / 送信 {tot_tx/1e6:.1f} MB | Pod {len(pods)}個"
      + (f" | 1リクエストあたり受信 {tot_rx/work/1024:.2f} KB" if work else ""))
for p in pods:
    print(f"     {svc(p):24s} 受信 {rx.get(p,0)/1e6:8.2f} MB ({rp.get(p,0):9.0f} pkt)  "
          f"送信 {tx.get(p,0)/1e6:8.2f} MB ({tp.get(p,0):9.0f} pkt)")
