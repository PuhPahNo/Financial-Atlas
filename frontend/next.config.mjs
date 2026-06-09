/** @type {import('next').NextConfig} */
let BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:8000";
// Render's fromService gives a bare host (no scheme); default it to https.
if (!/^https?:\/\//.test(BACKEND_URL)) BACKEND_URL = `https://${BACKEND_URL}`;

const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy API calls to the FastAPI backend (avoids CORS; one origin in dev).
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
  async headers() {
    // Next.js is the only public entry point (FastAPI is reached via the rewrite
    // above), so hardening headers here covers pages and proxied API responses.
    // CSP is frame-ancestors-only: a script-src policy would block Next's inline
    // bootstrap scripts without a nonce pipeline.
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
          // Ignored by browsers on plain-http localhost; effective behind Render's TLS.
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default nextConfig;
