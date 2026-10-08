// Photograph pages with Playwright. Called by scripts/screenshots.py, which passes a JSON list of shots:
//   {url, out, width, height, scheme, waitFor, until, section}
// `until` crops the picture just below that element; `section` keeps only the nth <section>.
const { chromium } = require("playwright");

(async () => {
  const shots = JSON.parse(process.argv[2]);
  const browser = await chromium.launch();
  for (const s of shots) {
    const page = await browser.newPage({
      viewport: { width: s.width, height: s.height || 900 },
      deviceScaleFactor: 2,
      colorScheme: s.scheme || "light",
    });
    await page.goto(s.url, { waitUntil: "networkidle" });
    if (s.waitFor) await page.waitForSelector(s.waitFor);
    let clip;
    if (s.until) {
      const box = await page.locator(s.until).first().boundingBox();
      clip = { x: 0, y: 0, width: s.width, height: Math.ceil(box.y + box.height + 24) };
    } else if (s.section !== undefined) {
      const box = await page.locator("section").nth(s.section).boundingBox();
      clip = { x: 0, y: Math.max(0, box.y - 24), width: s.width, height: Math.ceil(box.height + 48) };
    }
    await page.screenshot({ path: s.out, fullPage: true, clip });
    await page.close();
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
