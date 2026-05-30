const { chromium } = require("playwright");

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-x";
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1400, height: 950 },
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://x.com/settings/profile", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForTimeout(5000);
  const text = await page.locator("body").innerText({ timeout: 10000 }).catch((err) => `TEXT_ERROR: ${err.message}`);
  await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/x-profile-current.png", fullPage: true });
  console.log(text.slice(0, 5000));
  console.log("X_BROWSER_READY");
  console.log("Se pedir login, faz login nesta janela e deixa-a aberta.");
})();
