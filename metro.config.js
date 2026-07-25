const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

// expo-sqlite uses a WebAssembly worker in browsers.
config.resolver.assetExts.push("wasm");

// SharedArrayBuffer requires a cross-origin isolated page. These headers make
// the Expo development server match the requirements of expo-sqlite on web.
config.server.enhanceMiddleware = (middleware) => (request, response, next) => {
  response.setHeader("Cross-Origin-Embedder-Policy", "credentialless");
  response.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  return middleware(request, response, next);
};

module.exports = config;
