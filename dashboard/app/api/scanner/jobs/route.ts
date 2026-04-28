import { NextRequest, NextResponse } from "next/server";

interface ScannerJobRow {
  job_id?: unknown;
  triggered_at?: unknown;
  status?: unknown;
  urls_scanned?: unknown;
  matches_found?: unknown;
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function unwrapValue(value: unknown): unknown {
  if (
    typeof value === "object" &&
    value !== null &&
    "value" in (value as Record<string, unknown>)
  ) {
    return (value as { value: unknown }).value;
  }
  return value;
}

function normalizeJob(row: ScannerJobRow) {
  return {
    job_id: String(unwrapValue(row.job_id) ?? ""),
    triggered_at: String(unwrapValue(row.triggered_at) ?? ""),
    status: String(unwrapValue(row.status) ?? "running"),
    urls_scanned: Number(unwrapValue(row.urls_scanned) ?? 0),
    matches_found: Number(unwrapValue(row.matches_found) ?? 0),
  };
}

function scannerBases(): string[] {
  return unique([
    process.env.SCANNER_URL ?? "",
    process.env.NEXT_PUBLIC_SCANNER_URL ?? "",
    "http://127.0.0.1:3003",
    "http://localhost:3003",
  ]);
}

export async function GET(request: NextRequest) {
  const search = request.nextUrl.searchParams.toString();
  const attempts: string[] = [];

  for (const base of scannerBases()) {
    try {
      const upstream = await fetch(`${base}/scanner/jobs?${search}`, {
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
      const payload = (await upstream.json()) as { jobs?: ScannerJobRow[] };
      const jobs = Array.isArray(payload.jobs) ? payload.jobs.map(normalizeJob) : [];
      return NextResponse.json({ jobs }, { status: 200 });
    } catch (error) {
      attempts.push(`${base}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach scanner service from jobs route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
