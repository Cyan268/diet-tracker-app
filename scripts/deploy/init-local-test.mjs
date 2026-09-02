// Creates ONLY an ignored local fixture. Never generates a production deployment.
import { mkdir, writeFile, access } from "node:fs/promises";
import { randomBytes } from "node:crypto";
import { resolve, join } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const directory = join(root, "deploy/.local/topology-test");
try {
  await access(directory);
  throw new Error("Local fixture already exists; refusing to overwrite secrets or test data.");
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}
await mkdir(directory, { recursive: true, mode: 0o700 });
const secrets = join(directory, "secrets");
await mkdir(secrets, { mode: 0o700 });
const password = randomBytes(32).toString("hex");
const files = {
  postgres_password: password,
  nutripilot_database_url: `postgresql+psycopg://nutripilot:${password}@postgres:5432/nutripilot`,
  nutripilot_jwt_secret: randomBytes(32).toString("hex"),
  nutripilot_credential_encryption_key: randomBytes(32).toString("hex"),
  nutripilot_rate_limit_hmac_secret: randomBytes(32).toString("hex"),
  nutripilot_demo_reset_password: "NutriPilot-Local-Demo-Only-2026!",
};
for (const [name, value] of Object.entries(files)) {
  // Parent is 0700; readable bind-mounted file for the non-root API container.
  await writeFile(join(secrets, name), value, { flag: "wx", mode: 0o444 });
}
await writeFile(
  join(directory, "config.env"),
  [
    "NUTRIPILOT_PROJECT_NAME=nutripilot-topology-test",
    "NUTRIPILOT_APP_IMAGE=nutripilot:vps-local",
    "NUTRIPILOT_RELEASE=topology-test-working-tree",
    "NUTRIPILOT_PUBLIC_HOST=localhost",
    "NUTRIPILOT_SITE_ADDRESS=http://localhost",
    "NUTRIPILOT_BIND_ADDRESS=127.0.0.1",
    "NUTRIPILOT_HTTP_PORT=8086",
    "NUTRIPILOT_HTTPS_PORT=8446",
    "NUTRIPILOT_EDGE_SUBNET=172.30.91.0/28",
    "NUTRIPILOT_PROXY_IP=172.30.91.2",
    "NUTRIPILOT_API_IP=172.30.91.3",
    "NUTRIPILOT_AUTH_VISITOR_REQUESTS_PER_WINDOW=5",
    `NUTRIPILOT_SECRETS_PATH=${secrets.replaceAll("\\", "/")}`,
    "",
  ].join("\n"),
  { flag: "wx", mode: 0o600 }
);
console.log(
  "Created isolated local fixture under deploy/.local/topology-test (secret values not printed)."
);
