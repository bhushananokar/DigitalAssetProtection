import { NextRequest, NextResponse } from "next/server";

interface UpstreamAssets {
  assets?: unknown[];
  items?: unknown[];
  page?: number;
  total?: number;
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

export async function GET(request: NextRequest) {
  const bases = unique([
    process.env.INGEST_URL ?? "",
    process.env.NEXT_PUBLIC_INGEST_URL ?? "",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
  ]);
  const search = request.nextUrl.searchParams.toString();
  const attempts: string[] = [];

  for (const base of bases) {
    try {
      const upstream = await fetch(`${base}/assets?${search}`, {
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
      const payload = (await upstream.json()) as UpstreamAssets;
      const assets = Array.isArray(payload.assets)
        ? payload.assets
        : Array.isArray(payload.items)
          ? payload.items
          : [];

      return NextResponse.json({
        assets,
        page: Number(payload.page ?? 1),
        total: Number(payload.total ?? assets.length),
      });
    } catch (error) {
      attempts.push(`${base}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach ingest service from assets route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
