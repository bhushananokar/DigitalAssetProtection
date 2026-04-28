import { NextRequest, NextResponse } from "next/server";

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

export async function POST(request: NextRequest) {
  const candidates = unique([
    process.env.INGEST_URL ?? "",
    process.env.NEXT_PUBLIC_INGEST_URL ?? "",
    "http://127.0.0.1:8080",
    "http://localhost:8080",
  ]);
  const formData = await request.formData();
  const errors: string[] = [];

  for (const ingest of candidates) {
    try {
      const response = await fetch(`${ingest}/assets/upload`, {
        method: "POST",
        body: formData,
      });
      const text = await response.text();
      return new NextResponse(text, {
        status: response.status,
        headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
      });
    } catch (error) {
      errors.push(`${ingest}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach ingest service from dashboard API route",
      status: 502,
      attempts: errors,
    },
    { status: 502 },
  );
}
