import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIE_NAME, verifyAuthToken } from "@/lib/auth-token";

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

// CSRF guard for cookie-authenticated mutations. Browsers attach the Origin header to
// every cross-site (and same-origin) mutating request; if it doesn't match the host we
// were addressed as, the request was forged from another site. Requests without an
// Origin (curl, server-to-server) carry no ambient cookie risk and pass through.
function crossOriginBlocked(req: NextRequest) {
  if (!MUTATING_METHODS.has(req.method)) return false;
  const origin = req.headers.get("origin");
  if (!origin) return false;
  const host = req.headers.get("x-forwarded-host") ?? req.headers.get("host");
  try {
    return new URL(origin).host !== host;
  } catch {
    return true; // unparseable Origin (e.g. "null" from sandboxed iframes) — reject
  }
}

export async function middleware(req: NextRequest) {
  if (req.nextUrl.pathname.startsWith("/api/")) {
    if (crossOriginBlocked(req)) {
      return NextResponse.json(
        { error: { code: "FORBIDDEN", message: "Cross-origin request blocked." } },
        { status: 403 },
      );
    }
    return NextResponse.next();
  }

  const token = req.cookies.get(AUTH_COOKIE_NAME)?.value;
  const claims = await verifyAuthToken(token);
  if (claims) return NextResponse.next();

  const login = new URL("/login", req.url);
  login.searchParams.set("next", req.nextUrl.pathname + req.nextUrl.search);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/api/:path*", "/paper-trading/:path*", "/watchlists/:path*", "/screener/:path*"],
};
