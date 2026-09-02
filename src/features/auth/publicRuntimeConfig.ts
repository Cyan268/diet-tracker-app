import { API_BASE_URL } from "@/api/config";
import { requestJson, type FetchLike } from "@/api/http";
import type { PublicRuntimeConfigResponse } from "@/api/types";

export async function fetchPublicRuntimeConfig(
  fetcher: FetchLike = fetch,
  baseUrl: string = API_BASE_URL
): Promise<PublicRuntimeConfigResponse> {
  return requestJson<PublicRuntimeConfigResponse>(fetcher, `${baseUrl}/api/v1/meta/config`);
}
