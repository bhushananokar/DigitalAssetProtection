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
