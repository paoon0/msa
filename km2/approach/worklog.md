# 作業ログ (worklog)

案B（Pod集約 vs 独立スケールのトレードオフ）の作業記録。新しいセッションごとに上へ追記する。

---

## 2026-06-18

### このセッションでやったこと（要約）

1. **コストモデルを計画書に丁寧に追記** — `km2/approach/research_plan.md` の付録A（数値例つき）。
2. **集約版マニフェストを実装** — `scaling/colocated/recopay.yaml`（reco+payment を1 Pod 同居・Envoy 共有・結合HPA）。
   - 旧 `colocated/recommendationservice.yaml` `paymentservice.yaml` は削除、`kustomization.yaml` を `recopay.yaml` 参照に更新。
3. **分離版を対照として対称化** — `separated/recommendationservice.yaml` の inject を true に揃え、`separated/paymentservice.yaml` に独立HPAを追加。
4. **HPA のスケール単位を全アーム統一** — Envoy 同居で Pod が2コンテナになるため、`type: Resource`（Pod平均＝Envoy込み）→ `type: ContainerResource`（アプリコンテナ指定）に変更。集約版は ContainerResource を2本並べて `desired = max(a,b)` を実現。
5. **コストの定義を確定** — 主コスト=**予約(requests)**、前提=requests の右サイズ化、実使用は副指標（計画書 §3.5・メモ `coloc-experiment-design` に記録）。
6. **loadgenerator3 を新規作成** — 方法2（直接 gRPC・位相制御負荷）。下記参照。

### 未決事項（次回拾う）

- **コンテナ名の不一致**：分離版 reco コンテナ=`recommend` / 集約版=`reccomend`（綴り違い）。計測の PromQL `container="..."` で事故るので統一推奨（A:`recommend` に揃える / B:そのまま）。**保留中**。

---

## loadgenerator3 — 方法2（直接 gRPC・位相制御負荷）

### 何をするツールか
`recommendationservice` と `paymentservice` へ frontend を介さず**直接 gRPC** を投げ、
各サービスの到着率を正弦波で動かして需要相関 ρ を制御する。

```
reco の率    a(t) = BASE_RPS + AMP_RPS·sin(2π t / PERIOD_S)
payment の率  b(t) = BASE_RPS + AMP_RPS·sin(2π t / PERIOD_S + φ)
ρ = cos(φ)        (φ = PHASE_DEG)
```

| 欲しい ρ | PHASE_DEG |
|---|---|
| +1（完全同期）| 0 |
| 0（無相関）| 90 |
| −0.8 | 143 |
| −1（完全逆相関）| 180 |

### 構成ファイル
- `src/loadgenerator3/loadgen.py` — 本体（asyncio + grpc.aio、オープンループのレート制御）
- `src/loadgenerator3/demo_pb2.py`, `demo_pb2_grpc.py` — reco から再利用した proto スタブ
- `src/loadgenerator3/requirements.txt` — `grpcio==1.59.2`, `protobuf==4.25.0`
- `src/loadgenerator3/Dockerfile` — `ENTRYPOINT ["python","-u","loadgen.py"]`
- `scaling/loadgenerator3.yaml` — 実行用 Job（分離版・集約版どちらにも apply 可。Service 名が同じなので宛先不変）

### つまみ（Job の env）
| env | 既定 | 意味 |
|---|---|---|
| `RECO_ADDR` | `recommendationservice:8080` | reco の宛先 |
| `PAY_ADDR` | `paymentservice:50051` | payment の宛先 |
| `BASE_RPS` | 30 | 平均到着率 [req/s] |
| `AMP_RPS` | 20 | 振幅 σ [req/s] |
| `PERIOD_S` | 120 | 1 周期 [s] |
| `PHASE_DEG` | 0 | ★ρ=cos(φ) |
| `RUN_TIME_S` | 780 | 総実行時間 [s]（13分。最後10分を本計測窓に）|
| `MAX_INFLIGHT` | 400 | 同時実行の上限（暴走防止）|

- payment への Charge は Luhn 妥当な Visa テスト番号 `4111111111111111`（exp 2030/12）を使用。
- 10秒ごとに到達RPS・成功/失敗を標準出力。

### 実行手順（次回ここから）
```sh
# 1. イメージのビルド & プッシュ（要・本人実行）
docker build -t mizuki0118/loadgen3:run1 src/loadgenerator3 && docker push mizuki0118/loadgen3:run1

# 2. スモークテスト推奨（軽負荷・短時間で着弾確認）
#    Job の env を BASE_RPS=5, RUN_TIME_S=60 にして apply → ok が増えるか確認
kubectl apply -f scaling/separated/ -n exp
kubectl apply -f scaling/loadgenerator3.yaml -n exp
kubectl logs -f job/loadgenerator3 -n exp

# 3. 本走: PHASE_DEG を変えて ρ を掃引（0 / 90 / 143 / 180 …）、各で分離版・集約版を計測
```

### 動作確認の状態
- `loadgen.py` は構文チェック（py_compile）通過。
- ホストに grpc/protobuf 未インストールのため、実行確認はコンテナ内（＝クラスタ上）で行う。**未実行**。
- 要確認ポイント（初回スモークで見る）：reco/payment に着弾して `ok` が増えるか、payment のテストカードが Charge で通るか。

### 次の一手の候補
1. loadgen3 をビルド → スモークテスト。
2. （計測側）`exact-window-measurement` の手法で総CPU(予約ベース)と必要レプリカ時系列を取るスクリプトを `km2/approach` に用意。
3. コンテナ名の統一（未決事項）。
