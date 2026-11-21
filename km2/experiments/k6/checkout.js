// 開ループ負荷(k6 constant-arrival-rate): 応答を待たず一定の到着レートで投げ続ける。
//
// 【2種類の利用者】(2026-09-02 追加)
//   購入型(checkout): 1周 = GET /product/{id} → POST /cart → POST /cart/checkout
//                     (POST /cart は 303→GET /cart を k6 が自動追従するので実HTTPは4req/周)
//   閲覧型(browse)  : 1周 = GET /product/{id} だけ。買わない。
//   なぜ要るか: いまの負荷は全員が購入型なので、全サービスの忙しさが完全に連動している。
//     現実には見るだけの人が大半で、その比率が変わると catalog/reco は忙しいまま
//     cart/checkout/payment/email が暇になる。この「需要のズレ」がないと粒度損は生まれない。
//   使い方: BROWSE_RATE を 0 より大きくすると閲覧型シナリオが有効になる。0 なら従来通り。
// 案C: 最初の WARMUP 秒(VU立ち上げの過渡)を捨て、以降 MEASURE 秒だけをカスタム指標に記録。
//   scenario の duration = WARMUP+MEASURE。built-in の dropped_iterations は「全体」しか取れないので、
//   計測窓だけの取りこぼしを別に出す(2026-09-01 追加):
//     計測窓で投げるはずだった周回数 = RATE × MEASURE(constant-arrival-rate は毎秒きっかり RATE 本開始する)
//     実際に開始できた周回数 = m_started(窓に入ってから開始した周を、完了を待たずに数える)
//     ⇒ dropped_win = RATE×MEASURE − m_started
//   ※ m_iters(完了数)ではなく m_started(開始数)を使うのが肝。完了数だと、窓の終わりに走っていて
//     打ち切られた周が「取りこぼし」に化けて、遅い回ほど過大に出てしまう。
// 開ループの肝: 遅れても RATE を維持しようと VU を maxVUs まで動員。足りねば dropped_iterations 増=容量超過。
import http from 'k6/http';
import { Trend, Counter } from 'k6/metrics';

const BASE     = __ENV.BASE     || 'http://frontend:80';
const RATE     = parseInt(__ENV.RATE     || '100');   // 購入型の到着レート [周/秒]
const BROWSE   = parseInt(__ENV.BROWSE_RATE || '0'); // 閲覧型の到着レート [周/秒]。0で無効
const WARMUP   = parseInt(__ENV.WARMUP   || '30');    // 捨てる秒数
const MEASURE  = parseInt(__ENV.MEASURE  || '180');   // 記録する秒数
const PRE_VUS  = parseInt(__ENV.PRE_VUS  || '500');
const MAX_VUS  = parseInt(__ENV.MAX_VUS  || '4000');
// 2026-11-20 追加: NO_REUSE=1 で要求ごとに TCP 接続を張り直す (k6 の noConnectionReuse)。
//   既定 (0) は VU ごとに接続を使い回す (keep-alive)。使い回すと ClusterIP の振り分けが接続単位でしか効かず、
//   慣らし初め (1 台) に張った接続が最初の frontend Pod に張り付いて、後から増えた Pod に負荷が行かない
//   (smoke-k3f3 で実測: 4 台中 1 台がほぼ全部を処理)。SN (DeathStarBench hpa-k6b) と同じ設定。
//   k6-job.yaml の __NOREUSE__ を埋めないスクリプトでは '__NOREUSE__' のままなので、使い回し (従来どおり) になる。
const NO_REUSE = (__ENV.NO_REUSE || '0') === '1';
// 2026-11-20 追加: CLOSE_EVERY=N (>0) で、VU ごとに要求 N 回に 1 回だけ "Connection: close" を付けて接続を閉じる
//   (= ときどき張り直す)。次の要求で新しく接続を張るとき Service がその時点の Pod から選び直すので、HPA が増やした Pod にも
//   少しずつ接続が移る。張り直しの手間は NO_REUSE=1 の約 1/N。既定 0 = 付けない (従来どおり)。
//   k6-job.yaml の __CLOSEEVERY__ を埋めないスクリプトでは NaN → 0 扱い。
const CLOSE_EVERY = parseInt(__ENV.CLOSE_EVERY || '0') || 0;
let nReq = 0;   // VU ごとの要求の通し番号 (k6 は VU ごとに別の JS 実行環境なので、VU ごとに数えられる)
function prm() {
  nReq += 1;
  return (CLOSE_EVERY > 0 && nReq % CLOSE_EVERY === 0) ? { headers: { Connection: 'close' } } : {};
}

const products = ['0PUK6V6EV0','1YMWWN1N4O','2ZYFJ3GM2N','66VCHSJNUP','6E92ZMYYFZ',
                  '9SIQT8TOJO','L9ECAV7KIM','LS4PSXUNUM','OLJCESPC7Z'];

// ウォームアップ後だけ記録するカスタム指標
const mDur   = new Trend('m_req_duration', true);
// 種類別(どのリクエストが遅いか=詰まっている場所の特定に使う)
const mProd  = new Trend('m_product', true);   // GET  /product/{id}  … frontend→catalog/ad/reco
const mCart  = new Trend('m_cart', true);      // POST /cart          … frontend→cart(+303追従でGET /cart)
const mChk   = new Trend('m_checkout', true);  // POST /cart/checkout … frontend→checkout→(cart,catalog,shipping,payment,email,currency)
const mStart = new Counter('m_started');   // 購入型: 計測窓で「開始できた」周(完了は問わない)
// 閲覧型(商品ページを見るだけ)の指標。購入型と混ぜない
const mbStart = new Counter('mb_started');
const mbDur   = new Trend('mb_duration', true);
const mbFail  = new Counter('mb_failed');
const mReqs  = new Counter('m_reqs');
const mIters = new Counter('m_iters');
const mFail  = new Counter('m_failed');

export const options = {
  discardResponseBodies: true,
  noConnectionReuse: NO_REUSE,
  summaryTrendStats: ['avg','med','p(90)','p(95)','p(99)','max'],
  scenarios: scenarios(),
};

// 閲覧型が有効なときだけシナリオを2本にする。
// VU は到着レートの比で配分する(足りないと開ループが維持できず取りこぼしになる)。
function scenarios() {
  const dur = `${WARMUP + MEASURE}s`;
  // 閲覧型だけを流したいとき(RATE=0)。エッジ単位の通信量を測るのに使う:
  // 閲覧型は checkout / email / payment / shipping を一切呼ばないので、
  // それらの Pod のネットワーク量がゼロになり、残りのエッジが分離して読める。
  if (RATE <= 0) {
    return {
      browse: { executor: 'constant-arrival-rate', exec: 'browseFlow',
                rate: BROWSE, timeUnit: '1s', duration: dur,
                preAllocatedVUs: PRE_VUS, maxVUs: MAX_VUS },
    };
  }
  if (BROWSE <= 0) {
    return {
      checkout: { executor: 'constant-arrival-rate', exec: 'checkoutFlow',
                  rate: RATE, timeUnit: '1s', duration: dur,
                  preAllocatedVUs: PRE_VUS, maxVUs: MAX_VUS },
    };
  }
  const total = RATE + BROWSE;
  const share = (n, x) => Math.max(10, Math.round(n * x / total));
  return {
    checkout: { executor: 'constant-arrival-rate', exec: 'checkoutFlow',
                rate: RATE, timeUnit: '1s', duration: dur,
                preAllocatedVUs: share(PRE_VUS, RATE), maxVUs: share(MAX_VUS, RATE) },
    browse:   { executor: 'constant-arrival-rate', exec: 'browseFlow',
                rate: BROWSE, timeUnit: '1s', duration: dur,
                preAllocatedVUs: share(PRE_VUS, BROWSE), maxVUs: share(MAX_VUS, BROWSE) },
  };
}

// 開始時刻をログにも出す (2026-11-02 追加)。handleSummary に setup_data が渡らない k6 でも、
// 呼び出し側が kubectl logs から計測窓の時刻を読めるようにする
export function setup() { const start = Date.now(); console.log('@@@K6_START@@@ ' + start); return { start: start }; }

export function checkoutFlow(data) {
  const measuring = (Date.now() - data.start) / 1000 >= WARMUP;
  if (measuring) mStart.add(1);            // 開始時点で数える(打ち切られても計上される)
  const p = products[Math.floor(Math.random() * products.length)];
  const rs = [];
  rs.push(http.get(`${BASE}/product/${p}`, prm()));
  rs.push(http.post(`${BASE}/cart`, { product_id: p, quantity: '1' }, prm()));
  rs.push(http.post(`${BASE}/cart/checkout`, {
    email: 'test@test.com', street_address: 'Tokyo', zip_code: '100000',
    city: 'Tokyo', state: 'Tokyo', country: 'Tokyo',
    credit_card_number: '4111111111111111',
    credit_card_expiration_month: '1', credit_card_expiration_year: '2090',
    credit_card_cvv: '100',
  }, prm()));
  if (measuring) {
    mProd.add(rs[0].timings.duration);
    mCart.add(rs[1].timings.duration);
    mChk.add(rs[2].timings.duration);
    for (const r of rs) {
      mDur.add(r.timings.duration);
      mReqs.add(1);
      if (r.status >= 400 || r.status === 0) mFail.add(1);
    }
    mIters.add(1);
  }
}

// 閲覧型: 商品ページを見るだけ(frontend → productcatalog / recommendation / ad)
export function browseFlow(data) {
  const measuring = (Date.now() - data.start) / 1000 >= WARMUP;
  if (measuring) mbStart.add(1);
  const p = products[Math.floor(Math.random() * products.length)];
  const r = http.get(`${BASE}/product/${p}`, prm());
  if (measuring) {
    mbDur.add(r.timings.duration);
    if (r.status >= 400 || r.status === 0) mbFail.add(1);
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const g = (x, k) => (m[x] && m[x].values[k] != null) ? m[x].values[k] : null;
  const reqs = g('m_reqs', 'count') || 0;
  const iters = g('m_iters', 'count') || 0;
  const fail = g('m_failed', 'count') || 0;
  const started = g('m_started', 'count') || 0;
  const droppedWin = Math.max(0, Math.round(RATE * MEASURE - started));
  const bStarted = g('mb_started', 'count') || 0;
  const bDropped = BROWSE > 0 ? Math.max(0, Math.round(BROWSE * MEASURE - bStarted)) : 0;
  const out = {
    target_rate: RATE, measure_s: MEASURE,
    iters: iters, iter_rate: iters / MEASURE,          // 達成 周/秒(ウォームアップ除外)
    reqs: reqs, rps: reqs / MEASURE,                    // 達成 req/s
    dropped: g('dropped_iterations', 'count') || 0,     // 全体(ウォームアップ込み。参考値)
    dropped_win: droppedWin,                            // ★計測窓だけの取りこぼし(判定はこちらを使う)
    started: started,                                   // 計測窓で開始できた周
    failed_rate: reqs ? fail / reqs : 0,
    p50: g('m_req_duration', 'med'),
    p90: g('m_req_duration', 'p(90)'),
    p95: g('m_req_duration', 'p(95)'),
    p99: g('m_req_duration', 'p(99)'),
    avg: g('m_req_duration', 'avg'),
    max: g('m_req_duration', 'max'),
    // 種類別 p50/p99 (詰まっている場所の特定用)
    prod_p50: g('m_product', 'med'),  prod_p99: g('m_product', 'p(99)'),
    cart_p50: g('m_cart', 'med'),     cart_p99: g('m_cart', 'p(99)'),
    chk_p50:  g('m_checkout', 'med'), chk_p99:  g('m_checkout', 'p(99)'),
    // 閲覧型(BROWSE_RATE=0 のときは 0 のまま)
    browse_rate_target: BROWSE,
    browse_started: bStarted,
    browse_rate: BROWSE > 0 ? bStarted / MEASURE : 0,
    browse_dropped_win: bDropped,
    browse_p50: g('mb_duration', 'med'), browse_p99: g('mb_duration', 'p(99)'),
    browse_failed: g('mb_failed', 'count') || 0,
    // 時刻 (2026-11-02 追加、unix ミリ秒)。k6 の計測窓 = k6_start_ms + WARMUP 秒 から MEASURE 秒。
    // 呼び出し側が Prometheus に問い合わせた区間と突き合わせるために出す
    k6_start_ms: (data.setup_data && data.setup_data.start) || null,
    k6_warmup_s: WARMUP,
    no_conn_reuse: NO_REUSE,
    close_every: CLOSE_EVERY,                          // 2026-11-20 追加: 要求 N 回に 1 回接続を閉じる (0 = しない)                           // 2026-11-20 追加: 要求ごとに接続を張り直したか
    k6_summary_ms: Date.now(),
  };
  return { stdout: '\n@@@K6_BEGIN@@@\n' + JSON.stringify(out) + '\n@@@K6_END@@@\n' };
}
