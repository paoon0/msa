// Sock Shop 用の開ループ負荷 (k6 constant-arrival-rate)。km2/experiments/k6/checkout.js (Online Boutique) と同じ作り。
//
// 【2種類の利用者】
//   購入型(buy)   : 1周 = GET /login (Basic 認証) → POST /cart → POST /orders → DELETE /cart  (4 req/周)
//                   front-end → user (ログイン、注文時の住所・カード)、carts、orders → payment / shipping → rabbitmq → queue-master
//                   注文してもカートは空にならないので DELETE /cart で空にする (しないとカートが育ち、金額 100 超で payment が拒否する)。
//   閲覧型(browse): 1周 = GET /catalogue?size=6&page=n → GET /catalogue/{id}  (2 req/周)。買わない。front-end → catalogue → catalogue-db
// 【ユーザ】全 VU が同じユーザだとカートを取り合うので、setup() で NUSERS 人を登録 (住所・カード付き) し、VU ごとに割り当てる。
//   ユーザ名は実行ごとに接頭辞を変える (user-db に溜まるが測定には影響しない)。NUSERS は購入型の maxVUs 以上にする。
// 【計測窓】最初の WARMUP 秒を捨て、MEASURE 秒だけをカスタム指標に記録。dropped_win = RATE×MEASURE − 窓内で開始できた周。
import http from 'k6/http';
import encoding from 'k6/encoding';
import { Trend, Counter } from 'k6/metrics';

const BASE     = __ENV.BASE     || 'http://front-end:80';
const RATE     = parseInt(__ENV.RATE     || '10');    // 購入型 [周/秒]
const BROWSE   = parseInt(__ENV.BROWSE_RATE || '0');  // 閲覧型 [周/秒]。0 で無効
const WARMUP   = parseInt(__ENV.WARMUP   || '30');
const MEASURE  = parseInt(__ENV.MEASURE  || '180');
const PRE_VUS  = parseInt(__ENV.PRE_VUS  || '100');
const MAX_VUS  = parseInt(__ENV.MAX_VUS  || '1000');
const NUSERS   = parseInt(__ENV.NUSERS   || String(MAX_VUS));
// 接頭辞は setup() で 1 回だけ決めて data で各 VU に渡す (init は VU ごとに走るので、ここで時刻から作ると VU ごとにずれる)
const PREFIX_ENV = __ENV.USER_PREFIX || '';

// 安い商品だけ (1 個 18 ドル以下。payment は 100 超を拒否する)
const items = ['3395a43e-2d88-40de-b95f-e00e1502085b', '510a0d7e-8e83-4193-b483-e27e09ddc34d',
               '808a2de1-1aaa-4c25-a9b9-6612e8f29a38', '819e1fbf-8b7e-4f6d-811f-693534916a8b',
               '837ab141-399e-4c1f-9abc-bace40296bac', 'a0a4f044-b040-410d-8ead-4de0446aec7e',
               'd3588630-ad8e-49df-bbd7-3167f7efb246', 'zzz4f044-b040-410d-8ead-4de0446aec7e'];
const allItems = items.concat(['03fef6ac-1896-4ce8-bd69-b798f85c6e0b']);   // 閲覧は全 9 商品
const JSONH = { headers: { 'Content-Type': 'application/json' } };

const mDur   = new Trend('m_req_duration', true);
const mLogin = new Trend('m_login', true);
const mCart  = new Trend('m_cart', true);
const mOrder = new Trend('m_order', true);
const mStart = new Counter('m_started');
const mReqs  = new Counter('m_reqs');
const mIters = new Counter('m_iters');
const mFail  = new Counter('m_failed');
const mOrdFail = new Counter('m_order_failed');
const mbStart = new Counter('mb_started');
const mbDur   = new Trend('mb_duration', true);
const mbFail  = new Counter('mb_failed');

export const options = {
  discardResponseBodies: true,
  setupTimeout: '600s',
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  scenarios: scenarios(),
};

function scenarios() {
  const dur = `${WARMUP + MEASURE}s`;
  const sc = {};
  const total = Math.max(1, RATE) + Math.max(0, BROWSE);
  const share = (n, x) => (RATE > 0 && BROWSE > 0) ? Math.max(10, Math.round(n * x / total)) : n;
  if (RATE > 0) sc.buy = { executor: 'constant-arrival-rate', exec: 'buyFlow', rate: RATE, timeUnit: '1s', duration: dur,
                           preAllocatedVUs: share(PRE_VUS, RATE), maxVUs: Math.min(NUSERS, share(MAX_VUS, RATE)) };
  if (BROWSE > 0) sc.browse = { executor: 'constant-arrival-rate', exec: 'browseFlow', rate: BROWSE, timeUnit: '1s', duration: dur,
                                preAllocatedVUs: share(PRE_VUS, BROWSE), maxVUs: share(MAX_VUS, BROWSE) };
  return sc;
}

export function setup() {
  const PREFIX = PREFIX_ENV || `k6${Date.now() % 100000000}`;
  let ok = 0;
  if (RATE > 0) {
    for (let i = 0; i < NUSERS; i++) {
      const jar = http.cookieJar();
      jar.clear(BASE);
      const u = `${PREFIX}-${i}`;
      const r = http.post(`${BASE}/register`, JSON.stringify({ username: u, password: 'pw', email: `${u}@x.y`, firstName: 'K', lastName: 'Six' }), JSONH);
      const a = http.post(`${BASE}/addresses`, JSON.stringify({ number: '1', street: 'S', city: 'C', postcode: 'P', country: 'X' }), JSONH);
      const c = http.post(`${BASE}/cards`, JSON.stringify({ longNum: '4111111111111111', expires: '12/30', ccv: '123' }), JSONH);
      if (r.status === 200 && a.status === 200 && c.status === 200) ok++;
    }
    console.log(`setup: ${ok}/${NUSERS} users registered (prefix ${PREFIX})`);
  }
  return { start: Date.now(), ok: ok, prefix: PREFIX };
}

export function buyFlow(data) {
  const measuring = (Date.now() - data.start) / 1000 >= WARMUP;
  if (measuring) mStart.add(1);
  const u = `${data.prefix}-${(__VU - 1) % NUSERS}`;
  http.cookieJar().clear(BASE);                 // 前の周のセッションを残さない
  const it = items[Math.floor(Math.random() * items.length)];
  const rs = [];
  rs.push(http.get(`${BASE}/login`, { headers: { Authorization: 'Basic ' + encoding.b64encode(`${u}:pw`) } }));
  rs.push(http.post(`${BASE}/cart`, JSON.stringify({ id: it }), JSONH));
  rs.push(http.post(`${BASE}/orders`, null));
  rs.push(http.del(`${BASE}/cart`));
  if (measuring) {
    mLogin.add(rs[0].timings.duration);
    mCart.add(rs[1].timings.duration);
    mOrder.add(rs[2].timings.duration);
    if (rs[2].status !== 201) mOrdFail.add(1);
    for (const r of rs) {
      mDur.add(r.timings.duration);
      mReqs.add(1);
      if (r.status >= 400 || r.status === 0) mFail.add(1);
    }
    mIters.add(1);
  }
}

export function browseFlow(data) {
  const measuring = (Date.now() - data.start) / 1000 >= WARMUP;
  if (measuring) mbStart.add(1);
  const p = allItems[Math.floor(Math.random() * allItems.length)];
  const rs = [http.get(`${BASE}/catalogue?size=6&page=${1 + Math.floor(Math.random() * 2)}`), http.get(`${BASE}/catalogue/${p}`)];
  if (measuring) {
    for (const r of rs) {
      mbDur.add(r.timings.duration);
      if (r.status >= 400 || r.status === 0) mbFail.add(1);
    }
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const g = (x, k) => (m[x] && m[x].values[k] != null) ? m[x].values[k] : null;
  const reqs = g('m_reqs', 'count') || 0, iters = g('m_iters', 'count') || 0, fail = g('m_failed', 'count') || 0;
  const started = g('m_started', 'count') || 0, bStarted = g('mb_started', 'count') || 0;
  const out = {
    target_rate: RATE, measure_s: MEASURE, iters: iters, iter_rate: iters / MEASURE, reqs: reqs, rps: reqs / MEASURE,
    dropped: g('dropped_iterations', 'count') || 0,
    dropped_win: RATE > 0 ? Math.max(0, Math.round(RATE * MEASURE - started)) : 0,
    started: started, failed_rate: reqs ? fail / reqs : 0, order_failed: g('m_order_failed', 'count') || 0,
    p50: g('m_req_duration', 'med'), p99: g('m_req_duration', 'p(99)'),
    login_p50: g('m_login', 'med'), cart_p50: g('m_cart', 'med'), order_p50: g('m_order', 'med'), order_p99: g('m_order', 'p(99)'),
    browse_rate_target: BROWSE, browse_started: bStarted, browse_rate: BROWSE > 0 ? bStarted / MEASURE : 0,
    browse_dropped_win: BROWSE > 0 ? Math.max(0, Math.round(BROWSE * MEASURE - bStarted)) : 0,
    browse_p50: g('mb_duration', 'med'), browse_p99: g('mb_duration', 'p(99)'), browse_failed: g('mb_failed', 'count') || 0,
  };
  return { stdout: '\n@@@K6_BEGIN@@@\n' + JSON.stringify(out) + '\n@@@K6_END@@@\n' };
}
