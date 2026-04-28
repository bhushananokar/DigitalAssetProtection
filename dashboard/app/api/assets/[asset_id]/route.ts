import { NextRequest, NextResponse } from "next/server";

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function candidates(): string[] {
  return unique([
    process.env.INGEST_URL ?? "",
    process.env.NEXT_PUBLIC_INGEST_URL ?? "",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
  ]);
}

export async function GET(
  _request: NextRequest,
  { params }: { params: { asset_id: string } },
) {
  const attempts: string[] = [];

  for (const base of candidates()) {
    try {
      const upstream = await fetch(`${base}/assets/${params.asset_id}`, {
        method: "GET",
        cache: "no-store",
      });
      const text = await upstream.text();
      return new NextResponse(text, {
        status: upstream.status,
        headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
      });
    } catch (error) {
      attempts.push(`${base}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach ingest service from asset detail route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}

export async function DELETE(
  request: NextRequest,
  { params }: { params: { asset_id: string } },
) {
  const attempts: string[] = [];
  const hard = request.nextUrl.searchParams.get("hard") ?? "";
  const hardQuery = hard ? `?hard=${encodeURIComponent(hard)}` : "";

  for (const base of candidates()) {
    try {
      const upstream = await fetch(`${base}/assets/${params.asset_id}${hardQuery}`, {
        method: "DELETE",
      });
      const text = await upstream.text();
      return new NextResponse(text, {
        status: upstream.status,
        headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
      });
    } catch (error) {
      attempts.push(`${base}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach ingest service from asset delete route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
