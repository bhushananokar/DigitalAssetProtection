import request from "supertest";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mockStore = {
  createJob: vi.fn(async () => undefined),
  updateJob: vi.fn(async () => undefined),
  listJobs: vi.fn(async () => []),
  getJob: vi.fn(async () => null),
  isUrlScannedRecently: vi.fn(async () => false),
  markUrlScanned: vi.fn(async () => undefined),
};

vi.mock("./store.js", () => ({ store: mockStore }));
vi.mock("./scanners.js", () => ({
  runYouTubeScan: vi.fn(async () => undefined),
  runWebScan: vi.fn(async () => undefined),
}));
vi.mock("./config.js", () => ({
  config: { port: 3003 },
}));

describe("scanner API contract", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns started response immediately for POST /scanner/run", async () => {
    const { app } = await import("./index.js");
    const response = await request(app)
      .post("/scanner/run")
      .send({ org_id: "demo-org", keywords: ["ipl"], platforms: ["youtube", "web"] });

    expect(response.status).toBe(200);
    expect(response.body.status).toBe("started");
    expect(response.body.job_id).toBeTypeOf("string");
    expect(response.body.triggered_at).toBeTypeOf("string");
    expect(mockStore.createJob).toHaveBeenCalledTimes(1);
  });

  it("validates required request shape", async () => {
    const { app } = await import("./index.js");
    const response = await request(app).post("/scanner/run").send({ org_id: "demo-org" });
    expect(response.status).toBe(400);
    expect(response.body.code).toBe("INVALID_REQUEST");
  });

  it("validates platforms enum", async () => {
    const { app } = await import("./index.js");
    const response = await request(app)
      .post("/scanner/run")
      .send({ org_id: "demo-org", keywords: ["ipl"], platforms: ["twitter"] });
    expect(response.status).toBe(400);
    expect(response.body.code).toBe("INVALID_REQUEST");
  });
});
