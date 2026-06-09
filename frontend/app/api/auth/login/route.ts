import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE_NAME, AUTH_TTL_SECONDS, authConfigError, createAuthToken, validCredentials } from "@/lib/auth-token";

const attempts = new Map<string, { window: number; count: number }>();

function clientKey(req: NextRequest) {
  // Last X-Forwarded-For hop is the one appended by our own proxy (Render); earlier
  // entries are client-supplied and spoofable, so keying on them lets an attacker
  // mint a fresh rate-limit bucket per request.
  const forwarded = req.headers.get("x-forwarded-for");
  const hops = forwarded?.split(",") ?? [];
  return hops[hops.length - 1]?.trim() || "local";
}

function rateLimited(req: NextRequest) {
  const now = Math.floor(Date.now() / 1000);
  const window = Math.floor(now / 60);
  const perKeyLimit = Number(process.env.AUTH_RATE_LIMIT_PER_MINUTE || 12);
  const bump = (key: string) => {
    const current = attempts.get(key) ?? { window, count: 0 };
    const next = current.window === window ? { window, count: current.count + 1 } : { window, count: 1 };
    attempts.set(key, next);
    return next.count;
  };
  // Global backstop: even if per-IP keying is defeated, total attempts stay bounded.
  const globalLimited = bump("__global__") > perKeyLimit * 10;
  const keyLimited = bump(clientKey(req)) > perKeyLimit;
  if (attempts.size > 5000) {
    for (const [key, value] of attempts) {
      if (value.window < window) attempts.delete(key);
    }
  }
  return keyLimited || globalLimited;
}

export async function POST(req: NextRequest) {
  const configError = authConfigError();
  if (configError) {
    return NextResponse.json({ error: { code: "AUTH_NOT_CONFIGURED", message: configError } }, { status: 500 });
  }

  if (rateLimited(req)) {
    return NextResponse.json({ error: { code: "RATE_LIMITED", message: "Too many login attempts. Try again shortly." } }, { status: 429 });
  }

  const body = await req.json().catch(() => ({}));
  const username = String(body.username || "");
  const password = String(body.password || "");
  if (!validCredentials(username, password)) {
    return NextResponse.json({ error: { code: "UNAUTHORIZED", message: "Invalid username or password." } }, { status: 401 });
  }

  const res = NextResponse.json({ data: { ok: true, username }, meta: { ticker: null, served_by: "auth", stale: false } });
  res.cookies.set(AUTH_COOKIE_NAME, await createAuthToken(username), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: AUTH_TTL_SECONDS,
  });
  return res;
}
