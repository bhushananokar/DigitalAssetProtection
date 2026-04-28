import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const base = process.env.NEXT_PUBLIC_VIOLATIONS_URL;
  if (!base) {
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

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
