import { NextRequest, NextResponse } from "next/server";

interface UpstreamViolations {
  violations?: unknown[];
  items?: unknown[];
  page?: number;
  total?: number;
}

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

export async function GET(request: NextRequest) {
  const search = request.nextUrl.searchParams.toString();
  const attempts: string[] = [];

  for (const base of violationsBases()) {
    try {
      const upstream = await fetch(`${base}/violations?${search}`, {
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
      const payload = (await upstream.json()) as UpstreamViolations;
      const violations = Array.isArray(payload.violations)
        ? payload.violations
        : Array.isArray(payload.items)
          ? payload.items
          : [];
      return NextResponse.json(
        {
          violations,
          page: Number(payload.page ?? 1),
          total: Number(payload.total ?? violations.length),
        },
        { status: 200 },
      );
    } catch (error) {
      attempts.push(`${base}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach violations service from list route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
