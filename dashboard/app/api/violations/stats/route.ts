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
      hypothesisId: "H1",
      location: "dashboard/app/api/violations/stats/route.ts:5",
      message: "stats_route_env_base",
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
        hypothesisId: "H1",
        location: "dashboard/app/api/violations/stats/route.ts:17",
        message: "stats_route_missing_base_return_500",
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

  const search = request.nextUrl.searchParams.toString();
  const upstream = await fetch(`${base}/violations/stats?${search}`, {
    method: "GET",
    next: { revalidate: 60 },
  });
  // #region agent log
  fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
    body: JSON.stringify({
      sessionId: "1309cd",
      runId: "pre-fix",
      hypothesisId: "H3",
      location: "dashboard/app/api/violations/stats/route.ts:34",
      message: "stats_route_upstream_response",
      data: { upstreamStatus: upstream.status, search },
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion

  const text = await upstream.text();
  // #region agent log
  fetch("http://127.0.0.1:7578/ingest/a77b7fa5-1608-4fab-928b-0a39f4afb14f", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "1309cd" },
    body: JSON.stringify({
      sessionId: "1309cd",
      runId: "pre-fix-shape",
      hypothesisId: "H5",
      location: "dashboard/app/api/violations/stats/route.ts:52",
      message: "stats_route_upstream_body_shape",
      data: {
        bodyPreview: text.slice(0, 300),
        hasViolationsBySeverity: text.includes("violations_by_severity"),
        hasCountBySeverity: text.includes("count_by_severity"),
      },
      timestamp: Date.now(),
    }),
  }).catch(() => {});
  // #endregion
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
