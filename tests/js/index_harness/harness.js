/**
 * Harness for tests/js/test_index.js: serves templates/index.html from a throwaway
 * local server with static/js/storage.js swapped for storage_stub.js (no OAuth, no
 * IndexedDB) and the CDN libraries swapped for cdn_stub.js, then runs each test in a
 * fresh Puppeteer browser context. A test fails if the page logs an error.
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const puppeteer = require('puppeteer');

const ROOT = path.resolve(__dirname, '..', '..', '..');
const HARNESS = __dirname;

const plugin = (id, extra) => ({
    id, name: id, description: `${id} plugin`, version: '1.0.0', active: true, ...extra,
});
const PLUGINS = {
    active_storage: 'sheets',
    plugins: [
        plugin('pomodoro', { plugin_type: 'core', mandatory: true }),
        plugin('sheets', { plugin_type: 'storage' }),
        plugin('todos', { plugin_type: 'extension', has_tab: true, tab_id: 'todos', has_counts: true }),
        plugin('discussions', { plugin_type: 'extension', has_tab: true, tab_id: 'discussions' }),
        plugin('rt', { plugin_type: 'extension', has_tab: true, tab_id: 'rt' }),
    ],
};


function renderIndex() {
    return fs.readFileSync(path.join(ROOT, 'templates', 'index.html'), 'utf8')
        .replace(/\{\{\s*url_for\('static',\s*filename='([^']+)'\)\s*\}\}/g, '/static/$1');
}

function startServer() {
    const types = { '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.html': 'text/html' };
    const send = (res, status, type, body) => { res.writeHead(status, { 'Content-Type': type }); res.end(body); };
    const server = http.createServer((req, res) => {
        const url = new URL(req.url, 'http://localhost');
        if (url.pathname === '/') return send(res, 200, 'text/html', renderIndex());
        if (url.pathname === '/static/js/storage.js') {
            return send(res, 200, types['.js'], fs.readFileSync(path.join(HARNESS, 'storage_stub.js')));
        }
        if (url.pathname.startsWith('/static/')) {
            const file = path.join(ROOT, path.normalize(url.pathname));
            if (file.startsWith(path.join(ROOT, 'static')) && fs.existsSync(file)) {
                return send(res, 200, types[path.extname(file)] || 'application/octet-stream', fs.readFileSync(file));
            }
            return send(res, 404, 'text/plain', 'not found');
        }
        if (url.pathname === '/api/auth/status') {
            return send(res, 200, 'application/json', JSON.stringify({ google_configured: false }));
        }
        if (url.pathname.startsWith('/api/')) return send(res, 200, 'application/json', '{}');
        return send(res, 404, 'text/plain', 'not found');
    });
    return new Promise(resolve => server.listen(0, '127.0.0.1', () => resolve(server)));
}

async function openPage(browser, baseUrl, cfg) {
    const context = await browser.createBrowserContext();
    const page = await context.newPage();
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', err => errors.push(err.message));
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });

    const cdnStub = fs.readFileSync(path.join(HARNESS, 'cdn_stub.js'), 'utf8');
    await page.setRequestInterception(true);
    page.on('request', req => {
        const url = new URL(req.url());
        if (url.origin === baseUrl) return req.continue();
        if (req.resourceType() === 'script') return req.respond({ contentType: 'text/javascript', body: cdnStub });
        if (req.resourceType() === 'stylesheet') return req.respond({ contentType: 'text/css', body: '' });
        return req.abort();
    });

    await page.evaluateOnNewDocument(c => { window.__TEST__ = c; }, {
        plugins: PLUGINS,
        settings: {},
        ...cfg,
    });
    return { page, context, errors };
}

// Boot is done once loadSettings() has rendered the tab order list and, unless the
// test is holding /api/plugins, loadPlugins() has rendered the plugin rows.
async function boot({ page }, baseUrl, cfg) {
    await page.goto(baseUrl + '/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.querySelectorAll('#tab-order-list .tab-order-item').length > 0);
    if (!cfg.holdPlugins) {
        await page.waitForFunction(() => document.querySelector('#plugins-list .plugin-settings-slot'));
    }
}

const navOrder = page => page.$$eval('nav[role="tablist"] [role="tab"]', tabs => tabs.map(t => t.dataset.view));
const listOrder = page => page.$$eval('#tab-order-list .tab-order-item', rows =>
    rows.map(r => r.querySelector('span:nth-child(2)').textContent));
const savedTabOrders = page => page.evaluate(() =>
    window.__storageCalls.filter(c => c[0] === 'saveSettings').map(c => c[1].tab_order));
const focusedTab = page => page.evaluate(() => document.activeElement.dataset.view);
const activeView = page => page.evaluate(() => document.querySelector('.view.active').id);
const labels = page => page.$$eval('nav[role="tablist"] [role="tab"]', tabs =>
    Object.fromEntries(tabs.map(t => [t.dataset.view, t.textContent.trim()])));

// Where a plugin's settings panel currently lives: 'parked', a plugin id, or null.
const panelHome = (page, id) => page.evaluate(pid => {
    const panel = document.getElementById(`${pid}-settings-panel`);
    if (!panel) return null;
    if (panel.parentElement.id === 'plugin-panels') return 'parked';
    const slot = panel.closest('.plugin-settings-slot');
    return slot ? slot.dataset.pluginId : 'elsewhere';
}, id);
const panelHidden = (page, id) => page.$eval(`#${id}-settings-panel`, p => p.hidden);

async function run(tests) {
    const server = await startServer();
    const baseUrl = `http://127.0.0.1:${server.address().port}`;
    const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    let failed = 0;
    for (const t of tests) {
        let ctx;
        try {
            ctx = await openPage(browser, baseUrl, t.cfg);
            await boot(ctx, baseUrl, t.cfg);
            await t.fn(ctx);
            assert.deepEqual(ctx.errors, [], 'page logged errors');
            console.log(`  ✓ ${t.name}`);
        } catch (e) {
            failed++;
            console.log(`  ✗ ${t.name}\n      ${e.message.split('\n').join('\n      ')}`);
            if (ctx && ctx.errors.length) console.log(`      page errors: ${ctx.errors.join(' | ')}`);
        } finally {
            if (ctx) await ctx.context.close();
        }
    }
    await browser.close();
    server.close();
    console.log(`\nindex.html browser tests: ${tests.length - failed} passed, ${failed} failed`);
    process.exit(failed ? 1 : 0);
}

module.exports = {
    run, navOrder, listOrder, savedTabOrders, focusedTab, activeView, labels, panelHome, panelHidden,
};
