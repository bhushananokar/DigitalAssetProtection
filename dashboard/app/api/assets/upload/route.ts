import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const ingest = process.env.NEXT_PUBLIC_INGEST_URL;
  if (!ingest) {
    return NextResponse.json(
      { error: true, code: "CONFIG_ERROR", message: "NEXT_PUBLIC_INGEST_URL missing", status: 500 },
      { status: 500 },
    );
  }

  const response = await fetch(`${ingest}/assets/upload`, {
    method: "POST",
    headers: {
      "content-type": request.headers.get("content-type") ?? "",
    },
    body: request.body,
    duplex: "half",
  } as RequestInit);

  const text = await response.text();
  return new NextResponse(text, {
    status: response.status,
    headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
  });
}
