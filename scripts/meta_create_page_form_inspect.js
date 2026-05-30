const { chromium } = require("playwright");

async function dump(page, label) {
  await page.waitForTimeout(3500);
  const text = await page.locator("body").innerText({ timeout: 15000 }).catch((err) => `TEXT_ERROR: ${err.message}`);
  await page.screenshot({ path: `C:/Users/joaon/ptia-content-engine/.tmp/${label}.png`, fullPage: true });
  console.log(`=== ${label} ===`);
  console.log(text.slice(0, 8000));
}

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-meta";
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1500, height: 950 },
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://business.facebook.com/latest/settings/pages?business_id=1025009109954217", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForTimeout(4500);
  const addButtons = page.getByText("Adicionar", { exact: true });
  await addButtons.nth((await addButtons.count()) - 1).click({ force: true, timeout: 15000 });
  await page.waitForTimeout(1500);
  await page.getByText("Criar nova Página do Facebook", { exact: true }).click({ force: true, timeout: 15000 });
  await dump(page, "meta-create-page-form");
  await context.close();
})();
