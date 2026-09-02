const baseUrlArgument = process.argv[2] || process.env.NUTRIPILOT_DEPLOYMENT_URL;

if (!baseUrlArgument) {
  throw new Error("Usage: node scripts/smoke-deployment.mjs https://your-deployment.example");
}

const baseUrl = new URL(baseUrlArgument);
if (baseUrl.protocol !== "https:" && process.env.NUTRIPILOT_SMOKE_ALLOW_HTTP !== "true") {
  throw new Error(
    "Deployment smoke tests require HTTPS; set NUTRIPILOT_SMOKE_ALLOW_HTTP=true locally"
  );
}

const normalizedBaseUrl = baseUrl.href.replace(/\/$/, "");
const results = [];

async function check(name, path, assertion, options) {
  const startedAt = performance.now();
  const response = await fetch(`${normalizedBaseUrl}${path}`, {
    redirect: "error",
    signal: AbortSignal.timeout(90_000),
    ...options,
  });
  const elapsedMs = Math.round(performance.now() - startedAt);
  const body = await response.text();
  await assertion(response, body);
  results.push({ name, status: response.status, elapsed_ms: elapsedMs });
  return { response, body };
}

function expectStatus(expected) {
  return async (response) => {
    if (response.status !== expected) {
      throw new Error(`expected HTTP ${expected}, received ${response.status}`);
    }
  };
}

await check("web_root", "/", async (response, body) => {
  if (response.status !== 200 || !body.toLowerCase().includes("<html")) {
    throw new Error("root did not return the Expo Web HTML shell");
  }
  if (response.headers.get("cross-origin-opener-policy") !== "same-origin") {
    throw new Error("root is missing Cross-Origin-Opener-Policy: same-origin");
  }
  if (response.headers.get("cross-origin-embedder-policy") !== "credentialless") {
    throw new Error("root is missing Cross-Origin-Embedder-Policy: credentialless");
  }
});
await check("spa_fallback", "/auth", async (response, body) => {
  if (response.status !== 200 || !body.toLowerCase().includes("<html")) {
    throw new Error("/auth did not return the SPA shell");
  }
});
await check("liveness", "/api/v1/health/live", expectStatus(200));
await check("readiness", "/api/v1/health/ready", expectStatus(200));
await check("registration_policy", "/api/v1/meta/config", async (response, body) => {
  if (response.status !== 200) {
    throw new Error(`public config returned HTTP ${response.status}`);
  }
  const config = JSON.parse(body);
  if (config.registration_enabled !== false) {
    throw new Error("portfolio deployment must disable public registration");
  }
});
await check("missing_api", "/api/v1/does-not-exist", expectStatus(404));
await check("missing_asset", "/assets/does-not-exist.wasm", expectStatus(404));

const demoEmail = process.env.NUTRIPILOT_SMOKE_DEMO_EMAIL;
const demoPassword = process.env.NUTRIPILOT_SMOKE_DEMO_PASSWORD;
if ((demoEmail && !demoPassword) || (!demoEmail && demoPassword)) {
  throw new Error("Set both NUTRIPILOT_SMOKE_DEMO_EMAIL and NUTRIPILOT_SMOKE_DEMO_PASSWORD");
}
if (demoEmail && demoPassword) {
  const login = await check(
    "demo_login",
    "/api/v1/auth/login",
    async (response, body) => {
      if (response.status !== 200) {
        throw new Error(`demo login returned HTTP ${response.status}`);
      }
      const payload = JSON.parse(body);
      if (!payload.user?.is_demo || !payload.access_token) {
        throw new Error("demo login response is missing demo identity or access token");
      }
    },
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: demoEmail, password: demoPassword }),
    }
  );
  const tokens = JSON.parse(login.body);
  const accessToken = tokens.access_token;
  await check("authenticated_identity", "/api/v1/users/me", expectStatus(200), {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  await check("demo_logout", "/api/v1/auth/logout", expectStatus(204), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: tokens.refresh_token }),
  });
}

console.log(
  JSON.stringify(
    {
      status: "ok",
      base_url: normalizedBaseUrl,
      authenticated_demo_checked: Boolean(demoEmail),
      checks: results,
    },
    null,
    2
  )
);
