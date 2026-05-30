const { chromium } = require("playwright");

async function bodyText(page) {
  return await page.locator("body").innerText({ timeout: 15000 }).catch((err) => `TEXT_ERROR: ${err.message}`);
}

async function screenshot(page, name) {
  await page.screenshot({ path: `C:/Users/joaon/ptia-content-engine/.tmp/${name}.png`, fullPage: true });
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
  await page.waitForTimeout(5000);
  await screenshot(page, "meta-pages-before-add");
  console.log("=== BEFORE ===");
  console.log((await bodyText(page)).slice(0, 4000));

  const addButtons = page.getByText("Adicionar", { exact: true });
  const count = await addButtons.count();
  console.log(`ADD_BUTTONS=${count}`);
  if (count === 0) {
    console.log("NO_ADD_BUTTON");
    return;
  }
  await addButtons.nth(count - 1).click({ force: true, timeout: 15000 });
  await page.waitForTimeout(4000);
  await screenshot(page, "meta-pages-after-add-click");
  console.log("=== AFTER_ADD_CLICK ===");
  console.log((await bodyText(page)).slice(0, 6000));

  await context.close();
})();
