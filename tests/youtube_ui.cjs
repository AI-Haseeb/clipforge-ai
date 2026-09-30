// Run with PLAYWRIGHT_MODULE pointing to Playwright if it is not installed locally.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const root = path.resolve(__dirname, '../frontend');
  const server = http.createServer((request, response) => {
    const filename = path.resolve(root, '.' + (request.url.split('?')[0] === '/' ? '/index.html' : request.url.split('?')[0]));
    if (!filename.startsWith(root + path.sep) || !fs.existsSync(filename) || !fs.statSync(filename).isFile()) {
      response.writeHead(404).end(); return;
    }
    response.setHeader('Content-Type', ({ '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css' })[path.extname(filename)] || 'application/octet-stream');
    response.end(fs.readFileSync(filename));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const frontend = `http://127.0.0.1:${server.address().port}/`;
  let browser;
  try {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    let connected = true, publishBody, publishCalls = 0;
    let responseItems = [
      { short: 'short_01.mp4', source_url: '/data/jobs/test/shorts/short_01.mp4', video_id: 'mock1', url: 'https://youtu.be/mock1', warning: 'Video uploaded; custom thumbnail failed.' },
      { short: 'short_02.mp4', error: 'YouTube rejected the request (quotaExceeded).' },
    ];
    await context.route('http://127.0.0.1:8000/**', route => {
      const url = new URL(route.request().url());
      let json = {};
      if (url.pathname === '/youtube/auth/status') json = { connected };
      if (url.pathname === '/youtube/auth/start') json = { authorize_url: 'https://accounts.google.com/mock-oauth' };
      if (url.pathname === '/youtube/publish') {
        publishCalls++;
        publishBody = route.request().postDataJSON();
        json = { status: 'partial', items: responseItems };
      }
      return route.fulfill({ json, headers: { 'Access-Control-Allow-Origin': '*' } });
    });
    await context.route('https://accounts.google.com/**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Mock Google authorization</h1>' }));
    await context.route('https://studio.youtube.com/**', route => route.fulfill({ contentType: 'text/html', body: '<h1>Mock YouTube Studio</h1>' }));
    await context.route('http://localhost:8000/youtube/auth/callback**', route => route.fulfill({ contentType: 'text/html', body: `<script>window.opener.postMessage({type:'clipforge-youtube-connected'}, ${JSON.stringify(new URL(frontend).origin)});</script>` }));
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(frontend);
    await page.evaluate(() => {
      currentJobId = 'test';
      publishShorts = [1, 2].map(n => ({ name: `short_0${n}.mp4`, url: `/data/jobs/test/shorts/short_0${n}.mp4` }));
      publishThumbnails = [1, 2, 3].map(n => ({ name: `thumbnail_01${n === 1 ? '' : '_v' + n}.png`, url: `/data/jobs/test/thumbnails/thumbnail_01${n === 1 ? '' : '_v' + n}.png` }));
      selectedPublishShorts = new Set([0, 1]);
      resultSection.classList.remove('hidden');
      renderPublishCenter();
      activateResultTab('publishPanel');
    });
    await page.evaluate(() => refreshYoutubeConnectionState());
    assert.equal(await page.locator('#confirmYoutubePublish').innerText(), 'Publish Selected Shorts');
    await page.locator('[data-publish-thumb="0"][value="3"]').check();
    const studioPromise = page.waitForEvent('popup');
    await page.locator('#confirmYoutubePublish').click();
    const studio = await studioPromise;
    await studio.waitForURL('https://studio.youtube.com/');
    await page.waitForFunction(() => !youtubePublishing);
    assert.equal(page.url(), frontend);
    assert.equal(publishBody.items.length, 2);
    assert.equal(publishBody.items[0].thumbnail, 3);
    assert.deepEqual(await page.evaluate(() => [...selectedPublishShorts]), [1]);
    assert.match(await page.locator('#publishReview').innerText(), /custom thumbnail failed/);
    assert.match(await page.locator('#publishReview').innerText(), /quotaExceeded/);
    fs.mkdirSync(path.resolve(__dirname, '../tmp'), { recursive: true });
    await page.locator('#publishCenter').screenshot({ path: path.resolve(__dirname, '../tmp/youtube-partial-results.png') });
    await studio.close();

    // Retry sends only the failed selection, even when the popup is blocked.
    await page.evaluate(() => { window.savedOpen = window.open; window.open = () => null; });
    responseItems = [{ short: 'short_02.mp4', source_url: '/data/jobs/test/shorts/short_02.mp4', video_id: 'mock2', url: 'https://youtu.be/mock2' }];
    await page.locator('#confirmYoutubePublish').click();
    await page.waitForFunction(() => !youtubePublishing);
    assert.deepEqual(publishBody.items.map(item => item.short), ['short_02.mp4']);
    assert.equal(await page.locator('#publishReview a[href="https://studio.youtube.com/"]').getAttribute('target'), '_blank');
    assert.equal(page.url(), frontend);

    // Blocked OAuth offers a new-tab link and never navigates ClipForge.
    connected = false;
    await page.evaluate(() => { selectedPublishShorts = new Set([0]); renderPublishCenter(); });
    await page.locator('#confirmYoutubePublish').click();
    await page.waitForFunction(() => !youtubePublishing);
    assert.match(await page.locator('#publishReview').innerText(), /browser blocked/);
    assert.equal(await page.locator('#publishReview a').getAttribute('target'), '_blank');
    assert.equal(page.url(), frontend);
    assert.equal(publishCalls, 2);

    // Real browser tabs, with Google and the OAuth callback mocked.
    await page.evaluate(() => { window.open = window.savedOpen; });
    const authPromise = page.waitForEvent('popup');
    await page.locator('#confirmYoutubePublish').click();
    const auth = await authPromise;
    await auth.waitForURL('https://accounts.google.com/mock-oauth');
    assert.equal(page.url(), frontend);
    connected = true;
    await auth.goto('http://localhost:8000/youtube/auth/callback?mock=1');
    await page.waitForFunction(() => document.querySelector('#confirmYoutubePublish').textContent === 'Publish Selected Shorts');
    assert.equal(publishCalls, 2, 'OAuth callback must not auto-publish');
    await auth.close();
    assert.deepEqual(errors, []);
    console.log('PASS: connected button, thumbnail selection, partial results, failed-only retry, blocked popups, separate Google/Studio tabs, callback notification; APIs mocked.');
  } finally {
    if (browser) await browser.close();
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
