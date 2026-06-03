const { chromium } = require("playwright");
const path = require("path");

(async () => {
  const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";
  console.log("A abrir browser persistente (HEADLESS FALSE)...");
  
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false, // Try with headless false to see if it bypasses login redirect!
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  console.log("A aceder à página inicial do LinkedIn...");
  await page.goto("https://www.linkedin.com/feed/", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  
  await page.waitForTimeout(5000);
  
  const title = await page.title();
  const url = page.url();
  console.log(`URL Atual: ${url}`);
  console.log(`Título da página: ${title}`);
  
  const screenshotPath = path.join("C:/Users/joaon/ptia-content-engine/.tmp", "linkedin-session-check.png");
  await page.screenshot({ path: screenshotPath });
  console.log(`Screenshot gravado em: ${screenshotPath}`);
  
  const isLoggedIn = url.includes("/feed") && !url.includes("/login");
  console.log(`Está logado? ${isLoggedIn ? "SIM" : "NÃO"}`);
  
  await context.close();
})();
