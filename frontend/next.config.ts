import type { NextConfig } from "next";

// Django runs next to this app; Next proxies the API and the two shop mounts to it.
const backend = process.env.SITEMEND_API_URL ?? "http://127.0.0.1:14124";

const nextConfig: NextConfig = {
  poweredByHeader: false,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/edge", destination: `${backend}/edge/` },
      { source: "/edge/:path*", destination: `${backend}/edge/:path*` },
      { source: "/origin", destination: `${backend}/origin/` },
      { source: "/origin/:path*", destination: `${backend}/origin/:path*` },
    ];
  },
};

export default nextConfig;
