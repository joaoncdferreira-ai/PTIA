const { chromium } = require("playwright");

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-meta";
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1500, height: 950 },
  });
  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://business.facebook.com/latest/settings/instagram_account?business_id=1025009109954217", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForTimeout(5000);
  const addButtons = page.getByText("Adicionar", { exact: true });
  const count = await addButtons.count();
  console.log(`ADD_BUTTONS=${count}`);
  if (count > 0) {
    await addButtons.nth(count - 1).click({ force: true, timeout: 15000 });
  }
  await page.waitForTimeout(4000);
  const text = await page.locator("body").innerText({ timeout: 10000 }).catch((err) => `TEXT_ERROR: ${err.message}`);
  await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/meta-add-instagram.png", fullPage: true });
  console.log(text.slice(0, 6000));
  console.log("Deixa esta janela aberta. Se aparecer login/autorização do Instagram, completa manualmente.");
})();
