import { NextRequest, NextResponse } from "next/server";

interface ScannerJobDetail {
  job_id?: unknown;
  triggered_at?: unknown;
  completed_at?: unknown;
  status?: unknown;
  urls_scanned?: unknown;
  matches_found?: unknown;
  errors?: unknown;
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

function normalizeJob(job: ScannerJobDetail) {
  const rawErrors = unwrapValue(job.errors);
  const errors = Array.isArray(rawErrors)
    ? rawErrors.map((e) => String(unwrapValue(e) ?? "")).filter(Boolean)
    : [];

  const completed = unwrapValue(job.completed_at);
  return {
    job_id: String(unwrapValue(job.job_id) ?? ""),
    triggered_at: String(unwrapValue(job.triggered_at) ?? ""),
    completed_at: completed ? String(completed) : null,
    status: String(unwrapValue(job.status) ?? "running"),
    urls_scanned: Number(unwrapValue(job.urls_scanned) ?? 0),
    matches_found: Number(unwrapValue(job.matches_found) ?? 0),
    errors,
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

export async function GET(
  _request: NextRequest,
  { params }: { params: { job_id: string } },
) {
  const attempts: string[] = [];

  for (const base of scannerBases()) {
    try {
      const upstream = await fetch(`${base}/scanner/jobs/${params.job_id}`, {
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
      const payload = (await upstream.json()) as ScannerJobDetail;
      return NextResponse.json(normalizeJob(payload), { status: 200 });
    } catch (error) {
      attempts.push(`${base}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach scanner service from job detail route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
