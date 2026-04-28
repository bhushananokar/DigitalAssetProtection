import { NextRequest, NextResponse } from "next/server";

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function scannerBases(): string[] {
  return unique([
    process.env.SCANNER_URL ?? "",
    process.env.NEXT_PUBLIC_SCANNER_URL ?? "",
    "http://127.0.0.1:3003",
    "http://localhost:3003",
  ]);
}

export async function POST(request: NextRequest) {
  const payload = await request.text();
  const attempts: string[] = [];

  for (const base of scannerBases()) {
    try {
      const upstream = await fetch(`${base}/scanner/run`, {
        method: "POST",
        headers: { "content-type": request.headers.get("content-type") ?? "application/json" },
        body: payload,
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
      message: "Unable to reach scanner service from run route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
