const { chromium } = require("playwright");

async function dump(page, label) {
  await page.waitForTimeout(4000);
  const text = await page.locator("body").innerText({ timeout: 15000 }).catch((err) => `TEXT_ERROR: ${err.message}`);
  await page.screenshot({ path: `C:/Users/joaon/ptia-content-engine/.tmp/meta-${label}.png`, fullPage: true });
  console.log(`\n=== ${label} ===`);
  console.log(page.url());
  console.log(text.slice(0, 5000));
}

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-meta";
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1500, height: 950 },
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://business.facebook.com/latest/settings/business_users/?business_id=1025009109954217", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await dump(page, "people");

  const pagesLink = page.getByText("Páginas", { exact: true }).first();
  await pagesLink.click({ timeout: 15000, force: true });
  await dump(page, "pages");

  const instagramLink = page.getByText("Contas do Instagram", { exact: true }).first();
  await instagramLink.click({ timeout: 15000, force: true });
  await dump(page, "instagram");

  await context.close();
})();
