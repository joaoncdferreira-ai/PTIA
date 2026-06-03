const { chromium } = require("playwright");

async function test() {
  console.log("Launching browser context...");
  const context = await chromium.launchPersistentContext("C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin", {
    headless: false,
    viewport: { width: 1280, height: 800 },
  });
  const page = context.pages()[0] || await context.newPage();
  try {
    const targetUrl = "https://www.linkedin.com/company/unbabel/";
    console.log("Navigating to target profile:", targetUrl);
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
    
    console.log("Waiting for profile load...");
    await page.waitForTimeout(6000);
    
    const html = await page.content();
    console.log("HTML length:", html.length);
    
    // Test Patterns
    let companyId = null;
    const universalIdMatch = html.match(/companyUniversalId["']?\s*:\s*["']?(\d+)/i);
    if (universalIdMatch) companyId = universalIdMatch[1];
    
    const normalizedMatch = html.match(/urn:li:fs_normalized_company:(\d+)/i);
    const organizationMatch = html.match(/urn:li:organization:(\d+)/i);
    
    console.log("universalIdMatch:", universalIdMatch ? universalIdMatch[0] : "null");
    console.log("normalizedMatch:", normalizedMatch ? normalizedMatch[0] : "null");
    console.log("organizationMatch:", organizationMatch ? organizationMatch[0] : "null");
    console.log("Final Extracted ID:", companyId);
    
  } catch (err) {
    console.error("Error:", err.message);
  } finally {
    await context.close();
  }
}
test();
