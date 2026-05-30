const { chromium } = require("playwright");

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-meta";
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1440, height: 950 },
    args: ["--disable-blink-features=AutomationControlled"],
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://business.facebook.com/settings/people", {
    waitUntil: "domcontentloaded",
  });
  console.log("META_BROWSER_READY");
  console.log("Faz login/configura a conta nesta janela. Deixa a janela aberta.");
})();
