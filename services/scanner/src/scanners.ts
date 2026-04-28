import { config } from "./config.js";
import { store } from "./store.js";
import type { MatchResponse, ScanJob } from "./types.js";

interface SharedContext {
  orgId: string;
  keywords: string[];
  job: ScanJob;
}

async function providerErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const data = (await response.json()) as {
      error?: { message?: string };
    };
    const detail = data.error?.message;
    if (detail) return `${fallback}: ${detail}`;
  } catch {
    // Ignore parse failures and fall back to status-only message.
  }
  return fallback;
}

function isImageUrl(url: string): boolean {
  return /\.(jpg|jpeg|png|gif|webp|svg)(\?.*)?$/i.test(url);
}

async function checkAndMatch(url: string, source: "YOUTUBE" | "WEB", label: string, ctx: SharedContext) {
  const duplicate = await store.isUrlScannedRecently(url, ctx.orgId);
  if (duplicate) return;

  const response = await fetch(`${config.matchingServiceUrl}/fingerprint/match`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_url: url }),
  });

  if (!response.ok) {
    throw new Error(`Matching service error: ${response.status}`);
  }

  const match = (await response.json()) as MatchResponse;
  ctx.job.urls_scanned += 1;
  if (match.matched) {
    ctx.job.matches_found += 1;
    const score = match.matches[0]?.similarity_score ?? 0;
    console.log(`[${source}] ${label} | matched: true | score: ${score}`);
  } else {
    console.log(`[${source}] ${label} | matched: false`);
  }

  await store.markUrlScanned(url, ctx.orgId);
}

export async function runYouTubeScan(ctx: SharedContext): Promise<void> {
  const query = ctx.keywords.join(" ");
  const url = new URL("https://www.googleapis.com/youtube/v3/search");
  url.searchParams.set("q", query);
  url.searchParams.set("part", "snippet");
  url.searchParams.set("type", "video");
  url.searchParams.set("maxResults", "10");
  url.searchParams.set("key", config.youtubeApiKey);

  const res = await fetch(url.toString());
  if (!res.ok) {
    const message = await providerErrorMessage(res, `YouTube API call failed: ${res.status}`);
    ctx.job.errors.push(message);
    console.warn(`[YOUTUBE] ${message}`);
    return;
  }

  const data = (await res.json()) as {
    items?: Array<{
      id?: { videoId?: string };
      snippet?: { thumbnails?: { medium?: { url?: string } } };
    }>;
  };

  for (const item of data.items ?? []) {
    const videoId = item.id?.videoId;
    const thumb = item.snippet?.thumbnails?.medium?.url;
    if (!videoId || !thumb) continue;
    await checkAndMatch(thumb, "YOUTUBE", videoId, ctx);
  }
}

export async function runWebScan(ctx: SharedContext): Promise<void> {
  const query = ctx.keywords.join(" ");
  const url = new URL("https://www.googleapis.com/customsearch/v1");
  url.searchParams.set("q", query);
  url.searchParams.set("cx", config.customSearchCx);
  url.searchParams.set("key", config.customSearchApiKey);
  url.searchParams.set("num", "10");

  const res = await fetch(url.toString());
  if (!res.ok) {
    const message = await providerErrorMessage(res, `Custom Search API call failed: ${res.status}`);
    ctx.job.errors.push(message);
    console.warn(`[WEB] ${message}`);
    return;
  }

  const data = (await res.json()) as {
    items?: Array<{
      link?: string;
      fileFormat?: string;
      pagemap?: { cse_image?: Array<{ src?: string }> };
    }>;
  };

  for (const item of data.items ?? []) {
    try {
      const link = item.link ?? "";
      const isImage = isImageUrl(link) || Boolean(item.fileFormat);
      const candidate = isImage ? link : item.pagemap?.cse_image?.[0]?.src;
      if (!candidate) continue;
      await checkAndMatch(candidate, "WEB", candidate, ctx);
    } catch (error) {
      ctx.job.errors.push(error instanceof Error ? error.message : "Unknown web scan error");
    }
  }
}
