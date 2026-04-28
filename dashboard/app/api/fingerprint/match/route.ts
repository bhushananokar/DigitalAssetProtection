import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const base = process.env.FINGERPRINT_URL;
  if (!base) {
    return NextResponse.json(
      { error: true, code: "CONFIG_ERROR", message: "FINGERPRINT_URL missing", status: 500 },
      { status: 500 },
    );
  }

  const response = await fetch(`${base}/fingerprint/match`, {
    method: "POST",
    headers: {
      "content-type": request.headers.get("content-type") ?? "application/json",
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
