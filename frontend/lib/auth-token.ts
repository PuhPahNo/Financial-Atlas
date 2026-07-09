const encoder = new TextEncoder();
const decoder = new TextDecoder();

export const AUTH_COOKIE_NAME = process.env.AUTH_COOKIE_NAME || "atlas_session";
const AUTH_USERNAME = process.env.AUTH_USERNAME || "admin";
const AUTH_PASSWORD = process.env.AUTH_PASSWORD || "admin123";
const AUTH_SECRET = process.env.AUTH_SECRET || "dev-atlas-auth-secret-change-me";
export const AUTH_TTL_SECONDS = Number(process.env.AUTH_SESSION_TTL_SECONDS || 7 * 24 * 60 * 60);

/**
 * Fail closed in production: the fallbacks above are committed to the repo, and
 * AUTH_SECRET signs session cookies — anyone who has read the source could forge a
 * session if a deployment ever ran on them. Returns an error message when the
 * deployment is unsafe, null when it's fine (including all non-production envs).
 * Checked at request time (not module load) so `next build` works without runtime env.
 */
export function authConfigError(): string | null {
  if (process.env.NODE_ENV !== "production") return null;
  const missing: string[] = [];
  if (!process.env.AUTH_SECRET) missing.push("AUTH_SECRET");
  if (!process.env.AUTH_PASSWORD) missing.push("AUTH_PASSWORD");
  return missing.length ? `Auth is not configured: set ${missing.join(", ")} in the environment.` : null;
}

// Constant-time comparison that works in both Node and Edge runtimes (middleware has
// no node:crypto.timingSafeEqual). Comparison time depends only on input lengths, so
// an attacker can't recover secrets byte-by-byte from response timing.
function timingSafeEqual(a: string, b: string) {
  const aBytes = encoder.encode(a);
  const bBytes = encoder.encode(b);
  let diff = aBytes.length ^ bBytes.length;
  const len = Math.max(aBytes.length, bBytes.length);
  for (let i = 0; i < len; i += 1) {
    diff |= (aBytes[i] ?? 0) ^ (bBytes[i] ?? 0);
  }
  return diff === 0;
}

function bytesToBase64Url(bytes: Uint8Array) {
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlToBytes(value: string) {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = atob(padded);
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

async function signature(payload: string) {
  const key = await crypto.subtle.importKey("raw", encoder.encode(AUTH_SECRET), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const digest = await crypto.subtle.sign("HMAC", key, encoder.encode(payload));
  return bytesToBase64Url(new Uint8Array(digest));
}

export async function createAuthToken(username: string) {
  const now = Math.floor(Date.now() / 1000);
  const payload = bytesToBase64Url(encoder.encode(JSON.stringify({ sub: username, iat: now, exp: now + AUTH_TTL_SECONDS })));
  return `${payload}.${await signature(payload)}`;
}

export async function verifyAuthToken(token?: string | null) {
  if (authConfigError()) return null;
  if (!token || !token.includes(".")) return null;
  const [payload, sig] = token.split(".");
  if (!payload || !sig || !timingSafeEqual(sig, await signature(payload))) return null;
  try {
    const claims = JSON.parse(decoder.decode(base64UrlToBytes(payload)));
    if (claims.sub !== AUTH_USERNAME) return null;
    if (Number(claims.exp || 0) < Math.floor(Date.now() / 1000)) return null;
    return claims as { sub: string; iat: number; exp: number };
  } catch {
    return null;
  }
}

export function validCredentials(username: string, password: string) {
  if (authConfigError()) return false;
  // Evaluate both comparisons unconditionally so a valid username isn't discoverable
  // via short-circuit timing.
  const userOk = timingSafeEqual(username, AUTH_USERNAME);
  const passOk = timingSafeEqual(password, AUTH_PASSWORD);
  return userOk && passOk;
}
