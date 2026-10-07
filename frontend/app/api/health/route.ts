import { NextResponse } from "next/server";
export const dynamic = "force-dynamic";
export function GET() {
  return NextResponse.json(
    { ok: true, instance: process.env.ARIANA_DESKTOP_INSTANCE || null },
    { headers: { "Cache-Control": "no-store" } },
  );
}
