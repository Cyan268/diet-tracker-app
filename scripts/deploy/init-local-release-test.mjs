import { access, mkdir, readFile, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "../..");
const source = join(root, "deploy/.local/u1-01/config.env");
const directory = join(root, "deploy/.local/u1-02");

try {
  await access(directory);
  throw new Error("U1-02 local fixture already exists; refusing to overwrite release state.");
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}

const original = await readFile(source, "utf8");
await mkdir(directory, { recursive: true, mode: 0o700 });
await mkdir(join(directory, "state"), { mode: 0o700 });

function releaseConfig(image, release) {
  const replacements = new Map([
    ["NUTRIPILOT_PROJECT_NAME", "nutripilot-u1-release-local"],
    ["NUTRIPILOT_APP_IMAGE", image],
    ["NUTRIPILOT_RELEASE", release],
    ["NUTRIPILOT_HTTP_PORT", "8087"],
    ["NUTRIPILOT_HTTPS_PORT", "8447"],
    ["NUTRIPILOT_EDGE_SUBNET", "172.30.92.0/28"],
    ["NUTRIPILOT_PROXY_IP", "172.30.92.2"],
    ["NUTRIPILOT_API_IP", "172.30.92.3"],
  ]);
  return original
    .split(/\r?\n/)
    .map((line) => {
      const separator = line.indexOf("=");
      if (separator < 0) return line;
      const key = line.slice(0, separator);
      return replacements.has(key) ? `${key}=${replacements.get(key)}` : line;
    })
    .join("\n");
}

await writeFile(
  join(directory, "previous.env"),
  releaseConfig("nutripilot:vps-u1-02-previous", "u1-02-previous"),
  { flag: "wx", mode: 0o600 }
);
await writeFile(
  join(directory, "candidate.env"),
  releaseConfig("nutripilot:vps-u1-02-candidate", "u1-02-candidate"),
  { flag: "wx", mode: 0o600 }
);

console.log("Created isolated U1-02 release fixture; no secret values were copied or printed.");
