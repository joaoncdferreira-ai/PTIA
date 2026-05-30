const { chromium } = require("playwright");

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-meta";
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1500, height: 950 },
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://business.facebook.com/settings/people", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForTimeout(5000);
  const title = await page.title().catch(() => "");
  const url = page.url();
  const text = await page.locator("body").innerText({ timeout: 10000 }).catch((err) => `TEXT_ERROR: ${err.message}`);
  await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/meta-business-current.png", fullPage: true });
  console.log(JSON.stringify({
    title,
    url,
    text: text.slice(0, 6000),
  }, null, 2));
  await context.close();
})();
