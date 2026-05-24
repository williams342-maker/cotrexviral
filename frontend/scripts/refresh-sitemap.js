/**
 * Pre-build hook: regenerates /public/sitemap.xml + /public/robots.txt
 * from the backend's authoritative SEO logic.
 *
 * Run automatically before `yarn build` via the "prebuild" script in
 * package.json. If the backend is unreachable, falls back to the existing
 * static file (so deploys never fail because the backend pod is asleep).
 */
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');

const BACKEND =
  process.env.SITEMAP_BACKEND_URL ||
  process.env.REACT_APP_BACKEND_URL ||
  'https://social-sync-ai-1.preview.emergentagent.com';

const PUBLIC_DIR = path.join(__dirname, '..', 'public');

const fetch = (url) =>
  new Promise((resolve, reject) => {
    const lib = url.startsWith('https://') ? https : http;
    lib.get(url, (res) => {
      if (res.statusCode !== 200) {
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (chunk) => (body += chunk));
      res.on('end', () => resolve(body));
    }).on('error', reject);
  });

const refresh = async (remotePath, localFile) => {
  const target = path.join(PUBLIC_DIR, localFile);
  try {
    const body = await fetch(`${BACKEND}${remotePath}`);
    fs.writeFileSync(target, body, 'utf8');
    const urls = (body.match(/<loc>/g) || []).length;
    console.log(`✓ refreshed ${localFile} (${urls} URLs, ${body.length} bytes)`);
  } catch (e) {
    if (fs.existsSync(target)) {
      console.warn(`⚠  could not refresh ${localFile} from ${BACKEND} (${e.message}). Keeping existing file.`);
    } else {
      throw new Error(`Cannot fetch ${remotePath} and no fallback exists at ${target}: ${e.message}`);
    }
  }
};

(async () => {
  await refresh('/api/seo/sitemap.xml', 'sitemap.xml');
  await refresh('/api/seo/robots.txt', 'robots.txt');
})().catch((e) => {
  console.error('sitemap refresh failed:', e.message);
  process.exit(1);
});
