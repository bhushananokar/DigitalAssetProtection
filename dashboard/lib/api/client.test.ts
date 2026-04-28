import { describe, expect, it, vi } from "vitest";
import { ApiRequestError, apiRequest } from "@/lib/api/client";

describe("apiRequest", () => {
  it("sets JSON content type for object bodies", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await apiRequest<{ ok: boolean }>("/test", {
      method: "POST",
      body: { key: "value" },
    });

    const [, init] = mockFetch.mock.calls[0];
    const headers = init.headers as Headers;
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init.body).toBe(JSON.stringify({ key: "value" }));
  });

  it("throws ApiRequestError from API envelope", async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({
        error: true,
        code: "SCAN_JOB_FAILED",
        message: "Scan failed",
        status: 500,
      }),
    });
    vi.stubGlobal("fetch", mockFetch);

    await expect(apiRequest("/test")).rejects.toBeInstanceOf(ApiRequestError);
  });
});
