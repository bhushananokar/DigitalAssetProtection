import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const base =
    process.env.NEXT_PUBLIC_VIOLATIONS_URL ??
    process.env.VIOLATIONS_URL ??
    "http://127.0.0.1:8090";
  // #region agent log
  fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
    body: JSON.stringify({
      sessionId: "1309cd",
      runId: "pre-fix",
      hypothesisId: "H2",
      location: "dashboard/app/api/violations/anomaly-count/route.ts:5",
      message: "anomaly_count_env_base",
      data: { basePresent: Boolean(base), baseValue: base ?? null },
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion
  if (!base) {
    // #region agent log
    fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
      body: JSON.stringify({
        sessionId: "1309cd",
        runId: "pre-fix",
        hypothesisId: "H2",
        location: "dashboard/app/api/violations/anomaly-count/route.ts:17",
        message: "anomaly_count_missing_base_return_500",
        data: { pathname: request.nextUrl.pathname },
        timestamp: Date.now(),
      }),
    }).catch(() => {});
    // #endregion
    return NextResponse.json(
      { error: true, code: "CONFIG_ERROR", message: "NEXT_PUBLIC_VIOLATIONS_URL missing", status: 500 },
      { status: 500 },
    );
  }

  const orgId = request.nextUrl.searchParams.get("org_id") ?? "demo-org";
  const upstream = await fetch(`${base}/violations?org_id=${orgId}&page=1&limit=1&anomaly_flagged=true`, {
    method: "GET",
    cache: "no-store",
  });
  // #region agent log
  fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
    body: JSON.stringify({
      sessionId: "1309cd",
      runId: "pre-fix",
      hypothesisId: "H3",
      location: "dashboard/app/api/violations/anomaly-count/route.ts:36",
      message: "anomaly_count_upstream_response",
      data: { upstreamStatus: upstream.status, orgId },
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion

  if (!upstream.ok) {
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  }

  const data = (await upstream.json()) as { total: number };
  return NextResponse.json({ total: data.total ?? 0 });
}
