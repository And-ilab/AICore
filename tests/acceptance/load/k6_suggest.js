/**
 * II.7.4 k6 load: 75 virtual operators → POST /api/v1/sufler/suggest
 *
 * Prerequisites:
 *   - k6 installed (https://k6.io)
 *   - Backend running with seeded cc_production + operator session
 *
 * Usage:
 *   export SUFLER_BASE_URL=http://127.0.0.1:8000
 *   export SUFLER_LOAD_SESSIONID=<django-sessionid>
 *   k6 run tests/acceptance/load/k6_suggest.js
 *
 * Threshold: http_req_duration{name:sufler_suggest} p(95)<2000
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const BASE = __ENV.SUFLER_BASE_URL || "http://127.0.0.1:8000";
const SESSION = __ENV.SUFLER_LOAD_SESSIONID || "";
const suggestLatency = new Trend("sufler_suggest_latency_ms", true);

const QUERIES = [
  "как оформить дебетовую карту",
  "замена пин-кода карты",
  "лимит снятия наличных",
  "как открыть вклад",
  "комиссия за перевод",
];

export const options = {
  scenarios: {
    operators: {
      executor: "constant-vus",
      vus: Number(__ENV.SUFLER_LOAD_USERS || 75),
      duration: __ENV.SUFLER_LOAD_DURATION || "60s",
    },
  },
  thresholds: {
    "http_req_duration{name:sufler_suggest}": ["p(95)<2000"],
    checks: ["rate>0.99"],
  },
};

export default function () {
  const query = QUERIES[Math.floor(Math.random() * QUERIES.length)];
  const headers = {
    "Content-Type": "application/json",
    "X-Request-ID": `k6-${__VU}-${__ITER}`,
  };
  if (SESSION) {
    headers.Cookie = `sessionid=${SESSION}`;
  }
  const res = http.post(
    `${BASE}/api/v1/sufler/suggest`,
    JSON.stringify({ text: query, limit: 3 }),
    { headers, tags: { name: "sufler_suggest" } }
  );
  let pipelineMs = 0;
  try {
    const body = res.json();
    pipelineMs = Number((body.latency_ms || {}).total || 0);
    if (pipelineMs > 0) {
      suggestLatency.add(pipelineMs);
    }
  } catch (_) {
    // ignore parse errors — check below fails
  }
  check(res, {
    "status 200": (r) => r.status === 200,
    "has hints or blocked": (r) => {
      try {
        const b = r.json();
        return Array.isArray(b.hints) || b.blocked_reason;
      } catch (e) {
        return false;
      }
    },
  });
  sleep(0.3 + Math.random() * 0.7);
}
