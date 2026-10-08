// Drives the review page in a real browser. Run by tests/test_review_page.py with the service URL.
// Prints what it saw as JSON on stdout; the Python test checks the service state afterwards.
const { chromium } = require("playwright");

(async () => {
  const url = process.argv[2];
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  await page.goto(url);

  const card = page.locator('article[data-id="pay-1"]');
  await card.waitFor();
  const shown = await card.innerText();
  const injected = await page.locator("#injected").count();
  await card.locator(".note-input").fill("Checked against the PO");
  await card.getByRole("button", { name: "Approve" }).click();
  await card.waitFor({ state: "detached" });
  await page.locator("#recent").getByText("You approved").waitFor();

  await page.getByRole("button", { name: "Step away" }).click();
  await page.getByText("You are away.").waitFor();
  const asked = await page.locator("#asked").innerText();

  console.log(JSON.stringify({ errors, injected, shown, asked }));
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
