// The browser half of verify_chef.py: loads each page with every request to anything but the local zip server blocked,
// like Kolibri with no internet, and prints one line of JSON per page with what went wrong
//   node verify_pages.js '{"pages": [{"title": ..., "url": ...}], "chromium": <path or null>, "playwright": <module>}'
const config = JSON.parse(process.argv[2]);
const { chromium } = require(config.playwright);

(async () => {
  const browser = await chromium.launch(config.chromium ? { executablePath: config.chromium } : {});
  for (const { title, url } of config.pages) {
    const page = await browser.newPage();
    const blocked = new Set(), failed = [], errors = [];
    await page.route('**/*', route => {
      const requested = new URL(route.request().url());
      if (requested.hostname === 'localhost') return route.continue();
      blocked.add(route.request().url().slice(0, 200));
      return route.abort();
    });
    page.on('response', r => { if (r.status() >= 400) failed.push(r.status() + ' ' + r.url().replace(/^.*?\/zipcontent\//, '')); });
    page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
    try {
      await page.goto(url, { waitUntil: 'load', timeout: 60000 });
      // let lazily loaded scripts, fonts and MathJax finish
      await page.waitForTimeout(3000);
      if (await page.evaluate(() => !!(window.MathJax && MathJax.startup && MathJax.startup.promise))) {
        await page.evaluate(() => Promise.race([MathJax.startup.promise, new Promise(r => setTimeout(r, 15000))]));
      }
      const result = await page.evaluate(async () => {
        await document.fonts.ready;
        const fontRules = [...document.styleSheets]
          .flatMap(sheet => { try { return [...sheet.cssRules]; } catch (e) { return []; } })
          .filter(rule => rule instanceof CSSFontFaceRule);
        // a font that is only looked for on the reader's computer, src: local(...), failing is expected
        const webFont = family => fontRules.some(rule =>
          rule.style.fontFamily.replace(/["']/g, '') === family && rule.style.getPropertyValue('src').includes('url('));
        return {
          navigationLinks: document.querySelectorAll('[onclick*="navigateTo"]').length,
          brokenImages: [...document.images].filter(i => i.complete && i.naturalWidth === 0 && i.src && !i.src.startsWith('data:'))
            .map(i => i.src.replace(/^.*?\/zipcontent\//, '')),
          failedFonts: [...document.fonts].filter(f => f.status === 'error' && webFont(f.family.replace(/["']/g, ''))).map(f => f.family),
          math: document.querySelectorAll('mjx-container, .MathJax_CHTML, .MathJax_SVG, .MathJax').length,
          mathErrors: document.querySelectorAll('mjx-merror, .MathJax_Error, merror').length,
        };
      });
      console.log(JSON.stringify({ title, ...result, blocked: [...blocked], failed, errors }));
    } catch (e) {
      console.log(JSON.stringify({ title, navigationLinks: 0, brokenImages: [], failedFonts: [], math: 0, mathErrors: 0,
        blocked: [...blocked], failed: failed.concat(['could not load the page: ' + String(e).slice(0, 150)]), errors }));
    }
    await page.close();
  }
  await browser.close();
})();
