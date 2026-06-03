import { NextResponse } from "next/server";
import { AUTH_COOKIE_NAME } from "@/lib/auth-token";

export async function POST() {
  const res = NextResponse.json({ data: { ok: true }, meta: { ticker: null, served_by: "auth", stale: false } });
  res.cookies.set(AUTH_COOKIE_NAME, "", { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production", path: "/", maxAge: 0 });
  return res;
}
