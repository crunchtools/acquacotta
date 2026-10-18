/**
 * Browser-level tests for templates/index.html: tab order and plugin settings panels.
 * See index_harness/harness.js for how the page is served and stubbed.
 *
 * Run: node tests/js/test_index.js
 */
const assert = require('assert/strict');
const {
    run, navOrder, listOrder, savedTabOrders, focusedTab, activeView, labels, panelHome, panelHidden,
} = require('./index_harness/harness');

const DEFAULT_ORDER = ['timer', 'reports', 'history', 'todos', 'discussions', 'rt', 'settings'];

const tests = [];
const test = (name, cfg, fn) => tests.push({ name, cfg, fn });

test('saved tab_order is applied to the nav, missing tabs slotted in', {
    settings: { tab_order: ['settings', 'todos', 'timer'] },
}, async ({ page }) => {
    // Each missing tab lands after its nearest earlier default neighbour.
    const expected = ['settings', 'todos', 'discussions', 'rt', 'timer', 'reports', 'history'];
    assert.deepEqual(await navOrder(page), expected);
    const names = await labels(page);
    assert.deepEqual(await listOrder(page), expected.map(v => names[v]));
    // The buttons were moved, not rebuilt: their click handlers still switch views.
    await page.click('#tab-reports');
    assert.equal(await activeView(page), 'reports-view');
});

test('moveTab swaps neighbours, re-renders and saves; out-of-range is a no-op', {}, async ({ page }) => {
    await page.evaluate(() => moveTab(0, 1));
    const expected = ['reports', 'timer', ...DEFAULT_ORDER.slice(2)];
    assert.deepEqual(await navOrder(page), expected);
    const names = await labels(page);
    assert.deepEqual(await listOrder(page), expected.map(v => names[v]));
    assert.deepEqual(await savedTabOrders(page), [expected]);

    await page.evaluate(() => { moveTab(0, -1); moveTab(6, 1); });
    assert.deepEqual(await savedTabOrders(page), [expected], 'no extra save');
    assert.equal(await page.$eval('#tab-order-list .tab-order-item:first-child button', b => b.disabled), true);
});

test('the up/down buttons in the tab order list call moveTab', {}, async ({ page }) => {
    await page.click('#tab-settings');
    await page.click('#tab-order-list .tab-order-item:nth-child(3) button[title="Move earlier"]');
    const expected = ['timer', 'history', 'reports', ...DEFAULT_ORDER.slice(3)];
    assert.deepEqual(await navOrder(page), expected);
    assert.deepEqual(await savedTabOrders(page), [expected]);
});

test('drag-and-drop puts the dragged tab at the drop target index', {}, async ({ page }) => {
    await page.evaluate(() => {
        const rows = () => document.querySelectorAll('#tab-order-list .tab-order-item');
        const dt = new DataTransfer();
        const fire = (el, type) => el.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
        fire(rows()[0], 'dragstart');
        fire(rows()[3], 'dragover');
        fire(rows()[3], 'drop');
        fire(rows()[0], 'dragend');
    });
    const expected = ['reports', 'history', 'todos', 'timer', 'discussions', 'rt', 'settings'];
    assert.deepEqual(await navOrder(page), expected);
    assert.deepEqual(await savedTabOrders(page), [expected]);
    assert.equal(await page.$$eval('#tab-order-list .dragging, #tab-order-list .drag-over', els => els.length), 0);
});

test('dropping a row on itself changes nothing', {}, async ({ page }) => {
    await page.evaluate(() => {
        const row = document.querySelectorAll('#tab-order-list .tab-order-item')[2];
        const dt = new DataTransfer();
        for (const type of ['dragstart', 'dragover', 'drop', 'dragend']) {
            row.dispatchEvent(new DragEvent(type, { bubbles: true, cancelable: true, dataTransfer: dt }));
        }
    });
    assert.deepEqual(await navOrder(page), DEFAULT_ORDER);
    assert.deepEqual(await savedTabOrders(page), []);
});

test('resetTabOrder restores the default order and saves it', {
    settings: { tab_order: ['rt', 'settings', 'timer', 'todos', 'history', 'reports', 'discussions'] },
}, async ({ page }) => {
    await page.evaluate(() => resetTabOrder());
    assert.deepEqual(await navOrder(page), DEFAULT_ORDER);
    assert.deepEqual(await savedTabOrders(page), [DEFAULT_ORDER]);
});

test('hidden tabs are marked in the tab order list', {
    settings: { plugin_state_discussions: false },
}, async ({ page }) => {
    const hidden = await page.$$eval('#tab-order-list .tab-order-item', rows =>
        rows.filter(r => r.textContent.includes('(hidden)')).map(r => r.querySelector('span:nth-child(2)').textContent));
    assert.deepEqual(hidden, ['Discussions']);
});

test('arrow keys follow the custom order and skip hidden tabs', {
    settings: {
        tab_order: ['history', 'timer', 'discussions', 'todos', 'settings', 'reports', 'rt'],
        plugin_state_discussions: false,
    },
}, async ({ page }) => {
    assert.equal(await page.$eval('#tab-discussions', t => t.style.display), 'none');
    await page.focus('#tab-timer');
    await page.keyboard.press('ArrowRight');
    assert.equal(await focusedTab(page), 'todos', 'skips hidden discussions');
    assert.equal(await activeView(page), 'todos-view');

    await page.keyboard.press('ArrowLeft');
    assert.equal(await focusedTab(page), 'timer', 'skips hidden discussions going back');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await focusedTab(page), 'history');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await focusedTab(page), 'rt', 'wraps to the last tab in custom order');
    await page.keyboard.press('ArrowRight');
    assert.equal(await focusedTab(page), 'history', 'wraps to the first tab');

    await page.keyboard.press('End');
    assert.equal(await focusedTab(page), 'rt');
    await page.keyboard.press('Home');
    assert.equal(await focusedTab(page), 'history');
});

test('arrow keys pick up a reorder made after load', {}, async ({ page }) => {
    await page.evaluate(() => moveTab(6, -1)); // settings before rt
    await page.focus('#tab-rt');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await focusedTab(page), 'settings');
    await page.keyboard.press('ArrowRight');
    assert.equal(await focusedTab(page), 'rt');
});

test('an open plugin panel survives loadPlugins() with its form values', {}, async ({ page }) => {
    assert.equal(await panelHome(page, 'rt'), 'rt');
    assert.equal(await panelHidden(page, 'rt'), true);

    await page.click('#tab-settings');
    await page.click('#plugin-settings-btn-rt');
    assert.equal(await panelHidden(page, 'rt'), false);
    await page.type('#rt-cfg-base-url', 'https://rt.example.com');
    await page.evaluate(() => { window.__rtInput = document.getElementById('rt-cfg-base-url'); });

    await page.evaluate(() => loadPlugins());

    assert.equal(await panelHome(page, 'rt'), 'rt');
    assert.equal(await panelHidden(page, 'rt'), false);
    assert.equal(await page.$eval('#rt-cfg-base-url', el => el.value), 'https://rt.example.com');
    assert.equal(await page.evaluate(() => window.__rtInput === document.getElementById('rt-cfg-base-url')), true,
        'same element, not a rebuilt one');
    assert.equal(await page.$eval('#plugin-settings-btn-rt', b => b.getAttribute('aria-expanded')), 'true');
    assert.equal(await panelHidden(page, 'todos'), true, 'closed panels stay closed');
    assert.equal(await page.$$eval('[id="rt-settings-panel"]', els => els.length), 1);
});

test('a panel parks while its plugin is off and comes back open', {}, async ({ page }) => {
    await page.evaluate(() => togglePluginSettings('rt', true));
    await page.$eval('#rt-cfg-query', el => { el.value = 'Owner = "__CurrentUser__"'; });

    await page.evaluate(() => { settings.plugin_state_rt = false; return loadPlugins(); });
    assert.equal(await panelHome(page, 'rt'), 'parked');
    assert.equal(await page.$('#plugin-settings-btn-rt'), null);

    await page.evaluate(() => { settings.plugin_state_rt = true; return loadPlugins(); });
    assert.equal(await panelHome(page, 'rt'), 'rt');
    assert.equal(await panelHidden(page, 'rt'), false);
    assert.equal(await page.$eval('#rt-cfg-query', el => el.value), 'Owner = "__CurrentUser__"');
});

test("openPluginSettings('rt') before the plugin rows render", {
    holdPlugins: true,
    auth: { logged_in: true, email: 'test@example.com' },
    rtConfig: { base_url: 'https://rt.example.com', basic_user: 'scott', has_basic_pass: true },
}, async ({ page }) => {
    assert.equal(await panelHome(page, 'rt'), 'parked');
    await page.evaluate(() => { window.__opened = openPluginSettings('rt'); });
    await page.evaluate(() => window.__releasePlugins());
    await page.evaluate(() => window.__opened);

    assert.equal(await activeView(page), 'settings-view');
    assert.equal(await panelHome(page, 'rt'), 'rt');
    assert.equal(await panelHidden(page, 'rt'), false);
    assert.equal(await page.$eval('#plugin-settings-btn-rt', b => b.getAttribute('aria-expanded')), 'true');
    assert.equal(await page.$eval('#rt-cfg-base-url', el => el.value), 'https://rt.example.com');
    assert.equal(await page.evaluate(() => document.activeElement.id), 'rt-cfg-base-url');
});

run(tests);
