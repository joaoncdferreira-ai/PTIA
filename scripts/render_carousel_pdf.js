const { chromium } = require("playwright");
const path = require("path");
const fs = require("fs");

const htmlPath = path.resolve(__dirname, "../.tmp/carousel.html");
const pdfPath = path.resolve(__dirname, "../data/exports/ptia-weekly-carousel.pdf");

async function renderPdf() {
  if (!fs.existsSync(htmlPath)) {
    console.error(`ERRO: Ficheiro HTML temporário não encontrado em: ${htmlPath}`);
    process.exit(1);
  }

  // Ensure export directory exists
  const exportDir = path.dirname(pdfPath);
  if (!fs.existsSync(exportDir)) {
    fs.mkdirSync(exportDir, { recursive: true });
  }

  console.error("-> A iniciar Playwright headless para renderizar PDF...");
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    const fileUrl = "file:///" + htmlPath.replace(/\\/g, "/");
    console.error(`-> A carregar: ${fileUrl}`);
    
    await page.goto(fileUrl, { waitUntil: "networkidle", timeout: 30000 });
    
    console.error("-> A imprimir página para PDF (1080px x 1080px)...");
    await page.pdf({
      path: pdfPath,
      width: "1080px",
      height: "1080px",
      printBackground: true,
      margin: {
        top: "0px",
        right: "0px",
        bottom: "0px",
        left: "0px"
      }
    });

    console.error(`-> PDF gerado com sucesso em: ${pdfPath}`);
    console.log(JSON.stringify({ ok: true, pdf_path: pdfPath }));
  } catch (err) {
    console.error("ERRO ao gerar PDF com Playwright:", err.message);
    console.log(JSON.stringify({ ok: false, error: err.message }));
    process.exit(1);
  } finally {
    await browser.close();
  }
}

renderPdf();
