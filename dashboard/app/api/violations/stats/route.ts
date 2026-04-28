import { NextRequest, NextResponse } from "next/server";

interface UpstreamStats {
  total_violations?: number;
  open_violations?: number;
  critical_violations?: number;
  count_by_severity?: Array<{ severity: string; count: number }>;
  violations_by_severity?: { low?: number; medium?: number; high?: number; critical?: number };
  count_by_platform?: Array<{ platform: string; count: number }>;
  violations_by_platform?: Array<{ platform: string; count: number }>;
  violations_per_day_30d?: Array<{ day: string; date?: string; count: number }>;
  violations_over_time?: Array<{ day?: string; date: string; count: number }>;
  top_assets?: Array<{ asset_id: string; count: number }>;
  top_affected_assets?: Array<{ asset_id: string; asset_name?: string; count: number }>;
}

interface DashboardStats {
  total_violations: number;
  open_violations: number;
  critical_violations: number;
  violations_by_severity: { low: number; medium: number; high: number; critical: number };
  violations_by_platform: Array<{ platform: string; count: number }>;
  violations_over_time: Array<{ date: string; count: number }>;
  top_affected_assets: Array<{ asset_id: string; asset_name: string; count: number }>;
}

function unique(values: string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function normalizeStats(raw: UpstreamStats): DashboardStats {
  const bySeverity = raw.violations_by_severity ?? {};
  const countBySeverity = raw.count_by_severity ?? [];
  const countMap = Object.fromEntries(
    countBySeverity.map((row) => [String(row.severity).toLowerCase(), Number(row.count ?? 0)]),
  );
  const severity = {
    low: Number(bySeverity.low ?? countMap.low ?? 0),
    medium: Number(bySeverity.medium ?? countMap.medium ?? 0),
    high: Number(bySeverity.high ?? countMap.high ?? 0),
    critical: Number(bySeverity.critical ?? countMap.critical ?? 0),
  };
  const platform = (raw.violations_by_platform ?? raw.count_by_platform ?? []).map((row) => ({
    platform: String(row.platform),
    count: Number(row.count ?? 0),
  }));
  const timeline = (raw.violations_over_time ?? raw.violations_per_day_30d ?? []).map((row) => ({
    date: String(row.date ?? row.day ?? ""),
    count: Number(row.count ?? 0),
  }));
  const topAssets = (raw.top_affected_assets ?? raw.top_assets ?? []).map((row) => {
    const enriched = row as { asset_id: string; count: number; asset_name?: string };
    return {
      asset_id: String(enriched.asset_id),
      asset_name: String(enriched.asset_name ?? enriched.asset_id),
      count: Number(enriched.count ?? 0),
    };
  });

  return {
    total_violations: Number(raw.total_violations ?? 0),
    open_violations: Number(raw.open_violations ?? 0),
    critical_violations: Number(raw.critical_violations ?? severity.critical),
    violations_by_severity: severity,
    violations_by_platform: platform,
    violations_over_time: timeline,
    top_affected_assets: topAssets,
  };
}

export async function GET(request: NextRequest) {
  const bases = unique([
    process.env.VIOLATIONS_URL ?? "",
    process.env.NEXT_PUBLIC_VIOLATIONS_URL ?? "",
    "http://127.0.0.1:8090",
    "http://localhost:8090",
  ]);
  const search = request.nextUrl.searchParams.toString();
  const attempts: string[] = [];

  for (const base of bases) {
    try {
      const upstream = await fetch(`${base}/violations/stats?${search}`, {
        method: "GET",
        next: { revalidate: 60 },
      });
      if (!upstream.ok) {
        const text = await upstream.text();
        return new NextResponse(text, {
          status: upstream.status,
          headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
        });
      }
      const data = (await upstream.json()) as UpstreamStats;
      return NextResponse.json(normalizeStats(data), { status: 200 });
    } catch (error) {
      attempts.push(`${base}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return NextResponse.json(
    {
      error: true,
      code: "UPSTREAM_UNREACHABLE",
      message: "Unable to reach violations service from stats route",
      status: 502,
      attempts,
    },
    { status: 502 },
  );
}
