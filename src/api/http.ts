export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown
  ) {
    super(`API request failed with status ${status}`);
    this.name = "ApiError";
  }
}

export class NetworkError extends Error {
  constructor(cause: unknown) {
    super("Unable to reach API", { cause });
    this.name = "NetworkError";
  }
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) return undefined;
  const text = await response.text();
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function requestJson<T>(
  fetcher: FetchLike,
  url: string,
  init: RequestInit = {}
): Promise<T> {
  let response: Response;
  const controller = init.signal ? null : new AbortController();
  const timeout = controller ? setTimeout(() => controller.abort(), 15_000) : null;
  try {
    response = await fetcher(url, { ...init, signal: init.signal ?? controller?.signal });
  } catch (error) {
    throw new NetworkError(error);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
  const body = await parseBody(response);
  if (!response.ok) throw new ApiError(response.status, body);
  return body as T;
}
