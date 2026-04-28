import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const base = process.env.NEXT_PUBLIC_VIOLATIONS_URL;
  if (!base) {
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
