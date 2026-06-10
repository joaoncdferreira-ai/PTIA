const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";
const postUrl = "https://www.linkedin.com/feed/update/urn:li:activity:7458075532681900032";

async function main() {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: true,
  });
  const page = context.pages()[0] || await context.newPage();
  
  try {
    await page.goto(postUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(5000);
    
    // Dismiss cookie banner if present
    const cookieBtn = page.getByRole('button', { name: /Aceitar|Accept/i }).first();
    if (await cookieBtn.count() > 0 && await cookieBtn.isVisible()) {
      console.log("Cookie banner visible, clicking...");
      await cookieBtn.click();
      await page.waitForTimeout(1500);
    }
    
    await page.evaluate(() => window.scrollBy(0, 400));
    await page.waitForTimeout(3000);
    
    // Take screenshot
    await page.screenshot({ path: "C:/Users/joaon/ptia-content-engine/.tmp/dump-selectors.png" });
    console.log("Screenshot saved to .tmp/dump-selectors.png");
    
    // Get all button details
    const buttons = await page.evaluate(() => {
      return Array.from(document.querySelectorAll("button")).map(btn => ({
        text: btn.innerText || "",
        label: btn.getAttribute("aria-label") || "",
        classes: btn.className,
        html: btn.outerHTML.slice(0, 150)
      }));
    });
    
    console.log("=== ALL BUTTONS ON PAGE ===");
    console.log(JSON.stringify(buttons, null, 2));
    
  } catch (e) {
    console.error("Error:", e);
  } finally {
    await context.close();
  }
}

main();
