const encoder = new TextEncoder();
const decoder = new TextDecoder();

export const AUTH_COOKIE_NAME = process.env.AUTH_COOKIE_NAME || "atlas_session";
export const AUTH_USERNAME = process.env.AUTH_USERNAME || "admin";
export const AUTH_PASSWORD = process.env.AUTH_PASSWORD || "admin123";
export const AUTH_SECRET = process.env.AUTH_SECRET || "dev-atlas-auth-secret-change-me";
export const AUTH_TTL_SECONDS = Number(process.env.AUTH_SESSION_TTL_SECONDS || 7 * 24 * 60 * 60);

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
  if (!token || !token.includes(".")) return null;
  const [payload, sig] = token.split(".");
  if (!payload || !sig || sig !== await signature(payload)) return null;
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
  return username === AUTH_USERNAME && password === AUTH_PASSWORD;
}
