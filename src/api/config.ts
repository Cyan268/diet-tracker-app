const configuredBaseUrl = process.env.EXPO_PUBLIC_API_URL?.trim();
const sameOriginWebBaseUrl =
  typeof window !== "undefined" && window.location?.origin ? window.location.origin : undefined;

export const API_BASE_URL = (
  configuredBaseUrl ||
  sameOriginWebBaseUrl ||
  "http://127.0.0.1:8000"
).replace(/\/$/, "");
