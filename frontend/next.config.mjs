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
};

export default nextConfig;
