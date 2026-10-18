import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  experimental: {
    // Allow the API's 200 MiB file limit plus multipart headers and boundaries.
    proxyClientMaxBodySize: 201 * 1024 * 1024,
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.MEETING_API_INTERNAL_URL || "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
};
export default config;
