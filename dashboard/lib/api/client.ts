import type { ApiError } from "@/lib/types";

export class ApiRequestError extends Error implements ApiError {
  error: true = true;
  code: string;
  status: number;

  constructor(payload: ApiError) {
    super(payload.message);
    this.code = payload.code;
    this.status = payload.status;
  }
}

interface RequestOptions {
  method?: string;
  body?: BodyInit | Record<string, unknown>;
  headers?: HeadersInit;
  next?: NextFetchRequestConfig;
}

export async function apiRequest<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const isMultipart = options.body instanceof FormData;
  const isRawBody = typeof options.body === "string" || options.body instanceof Blob;
  const headers = new Headers(options.headers ?? {});

  let body: BodyInit | undefined;
  if (options.body === undefined) {
    body = undefined;
  } else if (isMultipart || isRawBody) {
    body = options.body as BodyInit;
  } else {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.body);
  }

  const response = await fetch(url, {
    method: options.method ?? "GET",
    headers,
    body,
    next: options.next,
  });

  if (!response.ok) {
    // #region agent log
    fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
      body: JSON.stringify({
        sessionId: "1309cd",
        runId: "pre-fix",
        hypothesisId: "H4",
        location: "dashboard/lib/api/client.ts:45",
        message: "api_request_non_ok_response",
        data: { url, status: response.status },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
    // #endregion
    let payload: ApiError;
    try {
      payload = (await response.json()) as ApiError;
    } catch {
      payload = {
        error: true,
        code: "REQUEST_FAILED",
        message: `Request failed with status ${response.status}`,
        status: response.status,
      };
    }
    throw new ApiRequestError(payload);
  }

  return (await response.json()) as T;
}
