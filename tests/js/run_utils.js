// Run: node tests/js/run_utils.js
// Loads test_utils.html in headless Chrome and exits with the page's test exit code.
const puppeteer = require('puppeteer');
const path = require('path');
const fs = require('fs');

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
  const page = await browser.newPage();

  // Enable console logging
  page.on('console', msg => console.log('Browser:', msg.text()));
  page.on('pageerror', err => console.error('Page error:', err.message));

  // Load the test page
  const testFile = path.join(__dirname, 'test_utils.html');
  console.log('Loading test file:', testFile);

  await page.goto('file://' + testFile, { waitUntil: 'networkidle0' });

  // Wait for tests to complete (check for data attribute)
  await page.waitForFunction(() => {
    return document.body.hasAttribute('data-test-exit-code');
  }, { timeout: 30000 });

  // Get results
  const results = await page.evaluate(() => ({
    exitCode: document.body.getAttribute('data-test-exit-code'),
    passed: document.body.getAttribute('data-test-passed'),
    failed: document.body.getAttribute('data-test-failed')
  }));

  console.log(`\nTest Results: ${results.passed} passed, ${results.failed} failed`);

  await browser.close();

  // Exit with appropriate code
  process.exit(parseInt(results.exitCode));
})();
