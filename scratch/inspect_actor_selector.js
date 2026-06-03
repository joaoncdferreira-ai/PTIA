const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";

(async () => {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: true,
    viewport: { width: 1400, height: 950 },
  });
  
  const page = context.pages()[0] || await context.newPage();
  
  try {
    const postUrl = "https://www.linkedin.com/feed/update/urn:li:activity:7467180315145383936";
    console.log(`Navigating to ${postUrl}`);
    await page.goto(postUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(4000);
    
    // Find Gostar button, find its eba433ab ancestor container, and then find first img
    console.log("Locating correct action bar container...");
    const likeBtn = page.locator("button").filter({ hasText: "Gostar" }).first();
    if (await likeBtn.count() > 0) {
      console.log("Gostar button found!");
      const container = likeBtn.locator("xpath=ancestor::div[contains(@class, 'eba433ab')]").first();
      const avatar = container.locator("img").first();
      
      if (await avatar.count() > 0) {
        console.log("Correct user avatar found! Clicking it...");
        await avatar.click();
        await page.waitForTimeout(2500);
        
        const tmpDir = path.join(__dirname, "../.tmp");
        const screenshotPath = path.join(tmpDir, `actor-dropdown-clicked.png`);
        await page.screenshot({ path: screenshotPath });
        console.log(`Screenshot saved to: ${screenshotPath}`);
      } else {
        console.log("Could not find img inside eba433ab container.");
      }
    } else {
      console.log("Gostar button not found.");
    }
    
  } catch (err) {
    console.error("Error:", err.message);
  } finally {
    await context.close();
  }
})();
