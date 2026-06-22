#!/usr/bin/python
#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ============================================================
# loadgenerator3 — 案B 実験用の「直接 gRPC・位相制御」負荷生成ツール (方法2)
#
#   recommendationservice と paymentservice の 2 サービスへ、frontend を
#   介さず直接 gRPC を投げる。各サービスの目標リクエスト率を正弦波で動かし、
#   2 本の位相差 φ で需要相関 ρ を制御する:
#
#       reco の率   a(t) = BASE + AMP·sin(2π t / PERIOD)
#       payment の率 b(t) = BASE + AMP·sin(2π t / PERIOD + φ)
#       ⇒ ρ = cos(φ)     (PHASE_DEG=0→ρ=+1, 90→0, 180→-1)
#
#   レート制御はオープンループ(到着率を直接作る)。各サービスを独立に駆動
#   できるので、他サービスのスケールに引きずられず ρ をピンポイントに掃引
#   できる(研究計画 §3.2 方法2)。
# ============================================================
import asyncio
import math
import os
import time

import grpc
import demo_pb2
import demo_pb2_grpc


def env(name, default):
    return os.environ.get(name, default)


# --- 接続先 ---
RECO_ADDR = env("RECO_ADDR", "recommendationservice:8080")
PAY_ADDR = env("PAY_ADDR", "paymentservice:50051")

# --- 負荷プロファイル(つまみ) ---
BASE_RPS = float(env("BASE_RPS", "30"))      # 平均リクエスト率 [req/s]
AMP_RPS = float(env("AMP_RPS", "20"))        # 正弦波の振幅 [req/s] (σ に相当)
PERIOD_S = float(env("PERIOD_S", "120"))     # 1 周期の長さ [s]
PHASE_DEG = float(env("PHASE_DEG", "0"))     # payment の位相差 [度] → ρ = cos(PHASE_DEG)
RUN_TIME_S = float(env("RUN_TIME_S", "780")) # 総実行時間 [s] (既定 13 分)

# 同時実行の上限(暴走防止)。サービスごと。
MAX_INFLIGHT = int(env("MAX_INFLIGHT", "400"))
# レート計算の刻み [s]。細かいほど到着が滑らか。
TICK_S = float(env("TICK_S", "0.05"))

PHASE_RAD = math.radians(PHASE_DEG)


def target_rate(t, phase):
    """時刻 t [s] における目標到着率 [req/s]。負にならないよう 0 で下限。"""
    r = BASE_RPS + AMP_RPS * math.sin(2.0 * math.pi * t / PERIOD_S + phase)
    return max(0.0, r)


class Stats:
    def __init__(self, name):
        self.name = name
        self.ok = 0
        self.err = 0
        self.launched = 0


def build_reco_request():
    return demo_pb2.ListRecommendationsRequest(user_id="loadgen3", product_ids=[])


def build_charge_request():
    return demo_pb2.ChargeRequest(
        amount=demo_pb2.Money(currency_code="USD", units=10, nanos=0),
        credit_card=demo_pb2.CreditCardInfo(
            credit_card_number="4111111111111111",  # Luhn 妥当な Visa テスト番号
            credit_card_cvv=123,
            credit_card_expiration_year=2030,
            credit_card_expiration_month=12,
        ),
    )


async def driver(name, addr, stub_factory, method_name, build_request, phase, sem, stats):
    """1 サービス分の負荷ドライバ。正弦波の到着率でリクエストを投げ続ける。"""
    async with grpc.aio.insecure_channel(addr) as channel:
        stub = stub_factory(channel)
        call = getattr(stub, method_name)

        async def one_request():
            async with sem:
                try:
                    await call(build_request(), timeout=10.0)
                    stats.ok += 1
                except grpc.aio.AioRpcError:
                    stats.err += 1
                except Exception:
                    stats.err += 1

        start = time.monotonic()
        credits = 0.0
        last = start
        while True:
            now = time.monotonic()
            t = now - start
            if t >= RUN_TIME_S:
                break
            dt = now - last
            last = now
            # この刻みで投げるべき本数を貯める(端数は次刻みへ繰り越し)
            credits += target_rate(t, phase) * dt
            while credits >= 1.0:
                stats.launched += 1
                asyncio.create_task(one_request())
                credits -= 1.0
            await asyncio.sleep(TICK_S)


async def reporter(reco_stats, pay_stats):
    """10 秒ごとに進捗を出力(到達 RPS の概算と成功/失敗)。"""
    prev = {"reco": 0, "pay": 0}
    while True:
        await asyncio.sleep(10.0)
        r_now, p_now = reco_stats.ok, pay_stats.ok
        r_rps = (r_now - prev["reco"]) / 10.0
        p_rps = (p_now - prev["pay"]) / 10.0
        prev["reco"], prev["pay"] = r_now, p_now
        print(
            f"[loadgen3] reco ok={reco_stats.ok} err={reco_stats.err} (~{r_rps:.1f}/s) | "
            f"pay ok={pay_stats.ok} err={pay_stats.err} (~{p_rps:.1f}/s)",
            flush=True,
        )


async def main():
    rho = math.cos(PHASE_RAD)
    print(
        f"[loadgen3] start: BASE={BASE_RPS} AMP={AMP_RPS} PERIOD={PERIOD_S}s "
        f"PHASE={PHASE_DEG}deg => rho=cos(phi)={rho:.3f} RUN_TIME={RUN_TIME_S}s",
        flush=True,
    )
    print(f"[loadgen3] reco -> {RECO_ADDR} (ListRecommendations)", flush=True)
    print(f"[loadgen3] pay  -> {PAY_ADDR} (Charge)", flush=True)

    reco_stats = Stats("reco")
    pay_stats = Stats("pay")
    reco_sem = asyncio.Semaphore(MAX_INFLIGHT)
    pay_sem = asyncio.Semaphore(MAX_INFLIGHT)

    rep = asyncio.create_task(reporter(reco_stats, pay_stats))
    await asyncio.gather(
        driver("reco", RECO_ADDR, demo_pb2_grpc.RecommendationServiceStub,
               "ListRecommendations", build_reco_request, 0.0, reco_sem, reco_stats),
        driver("pay", PAY_ADDR, demo_pb2_grpc.PaymentServiceStub,
               "Charge", build_charge_request, PHASE_RAD, pay_sem, pay_stats),
    )
    rep.cancel()
    # 走り切る前に発射したリクエストの decommission 待ち(短時間)
    await asyncio.sleep(2.0)
    print(
        f"[loadgen3] DONE: reco ok={reco_stats.ok} err={reco_stats.err} launched={reco_stats.launched} | "
        f"pay ok={pay_stats.ok} err={pay_stats.err} launched={pay_stats.launched}",
        flush=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
