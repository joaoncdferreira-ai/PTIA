const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const userDataDir = "C:/Users/joaon/ptia-content-engine/.tmp/playwright-linkedin";
const postUrl = "https://www.linkedin.com/feed/update/urn:li:activity:7458075532681900032";

async function main() {
  console.log("Starting chromium in headed mode...");
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    viewport: { width: 1400, height: 950 },
  });
  const page = context.pages()[0] || await context.newPage();
  
  try {
    await page.goto(postUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(6000);
    
    // Dismiss cookie banner
    const cookieBtn = page.getByRole('button', { name: /Aceitar|Accept/i }).first();
    if (await cookieBtn.count() > 0 && await cookieBtn.isVisible()) {
      await cookieBtn.click();
      await page.waitForTimeout(1500);
    }
    
    await page.evaluate(() => window.scrollBy(0, 500));
    await page.waitForTimeout(3000);
    
    const comentarBtn = page.locator("button").filter({ hasText: /Comentar|Comment/i }).first();
    if (await comentarBtn.count() > 0) {
      await comentarBtn.click();
      await page.waitForTimeout(4000);
    }
    
    const commentBoxSelector = ".ql-editor, [role='textbox'], .comments-comment-box__editor, textarea";
    const commentBox = page.locator(commentBoxSelector).first();
    if (await commentBox.count() > 0 && await commentBox.isVisible()) {
      console.log("Comment box is visible! Tracing ancestors of the matched textbox...");
      
      const trace = await page.evaluate(() => {
        // Find the actual editor element using same selectors
        const editor = document.querySelector(".ql-editor, [role='textbox'], .comments-comment-box__editor, textarea");
        if (!editor) return { error: "editor not found in page evaluate" };
        
        const path = [];
        let current = editor;
        while (current && current !== document.body) {
          const buttons = Array.from(current.querySelectorAll("button, [role='button'], img")).map(b => ({
            tag: b.tagName,
            text: b.innerText || "",
            label: b.getAttribute("aria-label") || b.getAttribute("alt") || "",
            classes: b.className,
            html: b.outerHTML.slice(0, 150)
          }));
          path.push({
            tagName: current.tagName,
            classes: current.className,
            id: current.getAttribute("id") || "",
            buttonsCount: buttons.length,
            buttons: buttons
          });
          current = current.parentElement;
        }
        return path;
      });
      
      console.log("=== ANCESTOR TRACE ===");
      console.log(JSON.stringify(trace, null, 2));
      
    } else {
      console.log("Comment box is NOT visible.");
    }
    
  } catch (e) {
    console.error("Error:", e);
  } finally {
    await page.waitForTimeout(3000);
    await context.close();
    console.log("Done.");
  }
}

main();
