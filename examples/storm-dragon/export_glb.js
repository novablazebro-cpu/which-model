const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const SP = process.argv[2];
const local = path.join(SP, 'three/node_modules/three');
const wrapped = path.join(SP, 'dragon/_wrapped.html');
(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  await page.route('https://cdn.jsdelivr.net/npm/three@0.160.0/**', r => r.fulfill({ path: path.join(local, r.request().url().split('three@0.160.0/')[1]), contentType: 'application/javascript' }));
  await page.route('https://fonts.googleapis.com/**', r => r.fulfill({ body: '', contentType: 'text/css' }));
  await page.goto('file://' + wrapped);
  await page.waitForFunction(() => window.__dragonReady === true, null, { timeout: 60000 });
  const b64 = await page.evaluate(() => window.__exportGLB());
  fs.writeFileSync(path.join(SP, 'dragon/storm_dragon.glb'), Buffer.from(b64, 'base64'));
  await browser.close();
})().catch(e => { console.error('FAILED', e.message); process.exit(1); });
