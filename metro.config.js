const { getDefaultConfig } = require("expo/metro-config");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");

const config = getDefaultConfig(__dirname);

// expo-sqlite uses a WebAssembly worker in browsers.
config.resolver.assetExts.push("wasm");

// SharedArrayBuffer requires a cross-origin isolated page. These headers make
// the Expo development server match the requirements of expo-sqlite on web.
config.server.enhanceMiddleware = (middleware) => (request, response, next) => {
  response.setHeader("Cross-Origin-Embedder-Policy", "credentialless");
  response.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  if (process.env.NUTRIPILOT_SQLITE_DIAGNOSTICS === "1" && request.url === "/__u4_sqlite_check") {
    response.setHeader("Content-Type", "text/html; charset=utf-8");
    response.end(readFileSync(join(__dirname, "test-support/web-sqlite-check.html")));
    return;
  }
  return middleware(request, response, next);
};

module.exports = config;
