import { NextRequest, NextResponse } from "next/server";

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function violationsBases(): string[] {
  return unique([
    process.env.VIOLATIONS_URL ?? "",
    process.env.NEXT_PUBLIC_VIOLATIONS_URL ?? "",
    "http://127.0.0.1:8090",
    "http://localhost:8090",
  ]);
}

export async function PATCH(
  request: NextRequest,
  { params }: { params: { violation_id: string } },
) {
  const payload = await request.text();
  const attempts: string[] = [];

  for (const base of violationsBases()) {
    try {
      const upstream = await fetch(`${base}/violations/${params.violation_id}/status`, {
        method: "PATCH",
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
      message: "Unable to reach violations service from status route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
