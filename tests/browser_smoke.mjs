// Usage: PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs node this_file BASE_URL SCREENSHOT_DIR
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE ? pathToFileURL(process.env.PLAYWRIGHT_MODULE).href : 'playwright');
const [url, output] = process.argv.slice(2);
assert(url && output, 'Supply the locally served report URL and screenshot directory');
await fs.mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ['--enable-unsafe-swiftshader'] });
try {
  const context = await browser.newContext();
  const unexpected = [];
  await context.route('**/*', route => {
    if (new URL(route.request().url()).origin === new URL(url).origin) return route.continue();
    unexpected.push(route.request().url());
    return route.abort();
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('response', response => { if (response.status() >= 400) errors.push(`${response.status()} ${response.url()}`); });
  for (const [name, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.goto(url);
    await page.waitForFunction(() => document.querySelector('#viewer')?.dataset.loaded === 'true', null, { timeout: 20000 });
    assert.equal(await page.locator('button:disabled').count(), 0);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${name}: horizontal overflow`);
    const before = await page.locator('#viewer canvas').screenshot();
    await page.getByRole('button', { name: 'Rotate right', exact: true }).click();
    const after = await page.locator('#viewer canvas').screenshot();
    assert(!before.equals(after), `${name}: rotation did not change the model view`);
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
    await page.getByRole('button', { name: 'Reset view', exact: true }).click();
    await page.screenshot({ path: path.join(output, `${name}.png`), fullPage: true });
  }
  assert.deepEqual(unexpected, [], 'Viewer tried to use the internet');
  assert.deepEqual(errors, [], 'Browser errors');
  const offline = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
  const fallback = await offline.newPage();
  await fallback.goto(url);
  assert(await fallback.getByRole('heading', { name: 'Files and reproducibility' }).isVisible());
  assert(await fallback.locator('#renders img').first().isVisible());
  assert(await fallback.locator('#artifacts a[download]').count() > 0);
  console.log(JSON.stringify({ offline_dependencies: true, desktop: true, mobile: true, rotation_zoom_reset: true, no_script_fallback: true, errors }));
} finally {
  await browser.close();
}
