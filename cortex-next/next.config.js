/** @type {import('next').NextConfig} */
const BACKEND = process.env.BACKEND_URL || 'https://cortexviral.com';
const SPA = process.env.SPA_URL || 'https://cortexviral.com';

module.exports = {
  reactStrictMode: true,
  poweredByHeader: false,

  async rewrites() {
    return [
      // 1. Backend API calls — proxy to FastAPI
      { source: '/api/:path*', destination: `${BACKEND}/api/:path*` },

      // 2. Sitemap + robots — proxy to the backend's SSR-rendered XML
      { source: '/sitemap.xml', destination: `${BACKEND}/sitemap.xml` },
      { source: '/robots.txt',  destination: `${BACKEND}/robots.txt` },

      // 3. Dashboard SPA — proxy until Phase 2 ports it
      { source: '/dashboard',         destination: `${SPA}/dashboard` },
      { source: '/dashboard/:path*',  destination: `${SPA}/dashboard/:path*` },
      { source: '/admin',             destination: `${SPA}/admin` },
      { source: '/admin/:path*',      destination: `${SPA}/admin/:path*` },

      // 4. Public uploads / demo videos
      { source: '/tiktok_demo.mp4',        destination: `${SPA}/tiktok_demo.mp4` },
      { source: '/tiktok_demo_short.mp4',  destination: `${SPA}/tiktok_demo_short.mp4` },
      { source: '/tiktok_demo.webm',       destination: `${SPA}/tiktok_demo.webm` },
      { source: '/cortex-logo.png',        destination: `${SPA}/cortex-logo.png` },
    ];
  },
};
