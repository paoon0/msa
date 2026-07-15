// 開ループ負荷(k6 constant-arrival-rate): 応答を待たず一定の到着レートで投げ続ける。
// locust の checkout フローを移植: 1周 = GET /product/{id} → POST /cart → POST /cart/checkout。
//   (POST /cart は 303→GET /cart を k6 が自動追従するので実HTTPは4req/周)
// 案C: 最初の WARMUP 秒(VU立ち上げの過渡)を捨て、以降 MEASURE 秒だけをカスタム指標に記録。
//   scenario の duration = WARMUP+MEASURE。built-in指標(dropped等)は全体だが、遅延/スループットは
//   ウォームアップ除外の m_* 指標で報告する。
// 開ループの肝: 遅れても RATE を維持しようと VU を maxVUs まで動員。足りねば dropped_iterations 増=容量超過。
import http from 'k6/http';
import { Trend, Counter } from 'k6/metrics';

const BASE     = __ENV.BASE     || 'http://frontend:80';
const RATE     = parseInt(__ENV.RATE     || '100');   // iterations/sec (1周=1checkout)
const WARMUP   = parseInt(__ENV.WARMUP   || '30');    // 捨てる秒数
const MEASURE  = parseInt(__ENV.MEASURE  || '180');   // 記録する秒数
const PRE_VUS  = parseInt(__ENV.PRE_VUS  || '500');
const MAX_VUS  = parseInt(__ENV.MAX_VUS  || '4000');

const products = ['0PUK6V6EV0','1YMWWN1N4O','2ZYFJ3GM2N','66VCHSJNUP','6E92ZMYYFZ',
                  '9SIQT8TOJO','L9ECAV7KIM','LS4PSXUNUM','OLJCESPC7Z'];

// ウォームアップ後だけ記録するカスタム指標
const mDur   = new Trend('m_req_duration', true);
const mReqs  = new Counter('m_reqs');
const mIters = new Counter('m_iters');
const mFail  = new Counter('m_failed');

export const options = {
  discardResponseBodies: true,
  summaryTrendStats: ['avg','med','p(90)','p(95)','p(99)','max'],
  scenarios: {
    checkout: {
      executor: 'constant-arrival-rate',
      rate: RATE,
      timeUnit: '1s',
      duration: `${WARMUP + MEASURE}s`,
      preAllocatedVUs: PRE_VUS,
      maxVUs: MAX_VUS,
    },
  },
};

export function setup() { return { start: Date.now() }; }

export default function (data) {
  const measuring = (Date.now() - data.start) / 1000 >= WARMUP;
  const p = products[Math.floor(Math.random() * products.length)];
  const rs = [];
  rs.push(http.get(`${BASE}/product/${p}`));
  rs.push(http.post(`${BASE}/cart`, { product_id: p, quantity: '1' }));
  rs.push(http.post(`${BASE}/cart/checkout`, {
    email: 'test@test.com', street_address: 'Tokyo', zip_code: '100000',
    city: 'Tokyo', state: 'Tokyo', country: 'Tokyo',
    credit_card_number: '4111111111111111',
    credit_card_expiration_month: '1', credit_card_expiration_year: '2090',
    credit_card_cvv: '100',
  }));
  if (measuring) {
    for (const r of rs) {
      mDur.add(r.timings.duration);
      mReqs.add(1);
      if (r.status >= 400 || r.status === 0) mFail.add(1);
    }
    mIters.add(1);
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const g = (x, k) => (m[x] && m[x].values[k] != null) ? m[x].values[k] : null;
  const reqs = g('m_reqs', 'count') || 0;
  const iters = g('m_iters', 'count') || 0;
  const fail = g('m_failed', 'count') || 0;
  const out = {
    target_rate: RATE, measure_s: MEASURE,
    iters: iters, iter_rate: iters / MEASURE,          // 達成 周/秒(ウォームアップ除外)
    reqs: reqs, rps: reqs / MEASURE,                    // 達成 req/s
    dropped: g('dropped_iterations', 'count') || 0,     // 全体(捌けず落とした周)
    failed_rate: reqs ? fail / reqs : 0,
    p50: g('m_req_duration', 'med'),
    p90: g('m_req_duration', 'p(90)'),
    p95: g('m_req_duration', 'p(95)'),
    p99: g('m_req_duration', 'p(99)'),
    avg: g('m_req_duration', 'avg'),
    max: g('m_req_duration', 'max'),
  };
  return { stdout: '\n@@@K6_BEGIN@@@\n' + JSON.stringify(out) + '\n@@@K6_END@@@\n' };
}
