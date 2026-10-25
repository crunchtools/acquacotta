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

const DEFAULT_ORDER = ['timer', 'reports', 'history', 'todos', 'discussions', 'rt', 'social', 'settings'];

const tests = [];
const test = (name, cfg, fn) => tests.push({ name, cfg, fn });

test('saved tab_order is applied to the nav, missing tabs slotted in', {
    settings: { tab_order: ['settings', 'todos', 'timer'] },
}, async ({ page }) => {
    // Each missing tab lands after its nearest earlier default neighbour.
    const expected = ['settings', 'todos', 'discussions', 'rt', 'social', 'timer', 'reports', 'history'];
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

    await page.evaluate(() => { moveTab(0, -1); moveTab(7, 1); });
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
    const expected = ['reports', 'history', 'todos', 'timer', 'discussions', 'rt', 'social', 'settings'];
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
        tab_order: ['history', 'timer', 'discussions', 'todos', 'settings', 'reports', 'social', 'rt'],
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
    await page.evaluate(() => moveTab(7, -1)); // settings before social
    await page.focus('#tab-social');
    await page.keyboard.press('ArrowLeft');
    assert.equal(await focusedTab(page), 'settings');
    await page.keyboard.press('ArrowRight');
    assert.equal(await focusedTab(page), 'social');
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

const SHARED = 'https://example.com/a?b=1';
const SHARE_PATH = '/?view=social&share=' + encodeURIComponent(SHARED);

test('a share while signed out lands on Social, keeps the link, asks to sign in', {
    path: SHARE_PATH,
}, async ({ page }) => {
    assert.equal(await activeView(page), 'social-view');
    await page.waitForFunction(() => document.getElementById('social-status-msg').textContent.includes('Sign in'));
    assert.equal(await page.$eval('#social-text', el => el.value), '', 'the link is a card, not text');
    assert.match(await page.$eval('#social-card', el => el.textContent), /example\.com\/a/);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('acquacotta_pending_share')), SHARED);
    assert.equal(await page.evaluate(() => location.search), '', 'share param cleared from the address bar');
});

const SOCIAL_SIGNED_IN = {
    path: SHARE_PATH,
    auth: { logged_in: true, email: 'test@example.com' },
    socialIntegrations: {
        configured: true,
        has_gemini_api_key: true,
        default_channels: ['x1'],
        integrations: [
            { id: 'x1', name: 'Scott on X', identifier: 'x', picture: '', max_length: 40 },
            { id: 'li1', name: '<b>LinkedIn</b>', identifier: 'linkedin', picture: '', max_length: 3000 },
        ],
    },
    socialPreview: { url: SHARED, title: '"><img id=pwned src=x>', site: 'example.com', image: 'javascript:alert(1)' },
    socialDraft: {
        page: { url: SHARED, title: 'T' },
        drafts: [{ integration_id: 'all', text: 'A sharp take ' + SHARED, max_length: 15, over_limit: false }],
    },
};

const socialCalls = (page, name) => page.evaluate(n => window.__storageCalls.filter(c => c[0] === n), name);
const setSocialText = (page, text) => page.$eval('#social-text', (el, t) => { el.value = t; el.dispatchEvent(new Event('input')); }, text);
const composerReady = page => page.waitForFunction(() => !document.getElementById('social-compose').hidden);

test('a shared link becomes a card; untrusted fields render as text', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await page.waitForFunction(() => window.__storageCalls.some(c => c[0] === 'socialPreview'));
    await page.waitForFunction(() => !document.querySelector('.social-card.loading'));
    assert.equal(await page.$eval('#social-text', el => el.value), '');
    assert.equal(await page.$('#pwned'), null, 'page title is rendered as text');
    assert.equal(await page.$$eval('.social-card-thumb', els => els.length), 0, 'a non-data: image is dropped');
    assert.deepEqual(await page.$$eval('.social-chip', els => els.map(e => [e.getAttribute('aria-label'), e.getAttribute('aria-pressed')])),
        [['X (Scott on X)', 'true'], ['LinkedIn (<b>LinkedIn</b>)', 'false']]);
    assert.equal(await page.$('.social-chip b'), null, 'channel names never render as HTML');
    assert.equal((await socialCalls(page, 'socialDraft')).length, 0, 'no auto-draft');
    // X counts the link as 23: 40 - 23 = 17 left, which is under the 20 warning line.
    assert.equal(await page.$eval('#social-count', el => el.textContent), '17 left · X');
    assert.equal(await page.$eval('#social-count', el => el.classList.contains('warn')), true);
    assert.equal(await page.$eval('#social-go', el => el.textContent), 'Post to 1 channel');
});

test('the card URL is appended on send, after one confirming tap', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Worth a read');
    await page.click('#social-go');
    assert.match(await page.$eval('#social-go', el => el.textContent), /Tap again to post to 1/);
    assert.equal((await socialCalls(page, 'socialSchedule')).length, 0, 'first tap only arms');
    await page.click('#social-go');
    await page.waitForFunction(() => window.__storageCalls.some(c => c[0] === 'socialSchedule'));
    const [[, req]] = await socialCalls(page, 'socialSchedule');
    assert.deepEqual(req, { mode: 'now', posts: [{ integration_id: 'x1', identifier: 'x', text: 'Worth a read\n\n' + SHARED }] });
    await page.waitForFunction(() => document.getElementById('social-go').textContent.includes('Posted to 1'));
    assert.equal(await page.$eval('#social-text', el => el.value), '', 'composer clears');
    assert.equal(await page.$eval('#social-card', el => el.innerHTML), '', 'card clears');
});

test('an armed button is cancelled by a tap elsewhere or a channel change', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Hi');
    await page.click('#social-go');
    await page.click('#social-count');
    assert.equal(await page.$eval('#social-go', el => el.classList.contains('armed')), false, 'tap outside disarms');
    await page.click('#social-go');
    await page.click('#social-chip-1');
    assert.equal(await page.$eval('#social-go', el => el.textContent), 'Post to 2 channels', 'chip change disarms and relabels');
    assert.equal((await socialCalls(page, 'socialSchedule')).length, 0);
});

test('over the limit names the channel and blocks posting', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await page.click('.social-card-remove');
    await setSocialText(page, 'x'.repeat(45));
    assert.equal(await page.$eval('#social-count', el => el.textContent), '-5 · too long for X');
    assert.equal(await page.$eval('#social-chip-0', el => el.classList.contains('over')), true);
    assert.equal(await page.$eval('#social-go', el => el.disabled), true);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('acquacotta_pending_share')), null, 'removing the card drops the share');
});

test('scheduling defaults to the next open slot and sends it', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Later');
    await page.click('#social-mode-link');
    await page.waitForFunction(() => /^Next open slot · /.test(document.getElementById('social-when-next').textContent));
    assert.deepEqual((await socialCalls(page, 'socialSlot')).map(c => c.slice(1)), [['x1', undefined]]);
    assert.equal(await page.$eval('#social-when-next', el => el.getAttribute('aria-pressed')), 'true');
    assert.equal(await page.$eval('#social-time', el => el.hidden), true, 'no picker unless asked for');
    assert.equal(await page.$eval('#social-slot-prev', el => el.disabled), true, 'nothing earlier than the first slot');
    assert.match(await page.$eval('#social-go', el => el.textContent), /^Schedule 1 channel · /);
    await page.click('#social-go');
    await page.click('#social-go');
    await page.waitForFunction(() => window.__storageCalls.some(c => c[0] === 'socialSchedule'));
    const [[, req]] = await socialCalls(page, 'socialSchedule');
    assert.equal(req.mode, 'schedule');
    assert.equal(req.date, '2999-06-01T14:20:00.000Z', 'what you see is what gets scheduled');
});

test('› and ‹ step through open slots', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Later');
    await page.click('#social-mode-link');
    await page.waitForFunction(() => !document.getElementById('social-slot-next').disabled);
    await page.click('#social-slot-next');
    await page.waitForFunction(() => !document.getElementById('social-slot-prev').disabled);
    await page.click('#social-slot-next');
    await page.waitForFunction(() => (window.__storageCalls.filter(c => c[0] === 'socialSlot').length === 3) && !document.getElementById('social-slot-next').disabled);
    const afters = (await socialCalls(page, 'socialSlot')).map(c => c[2]);
    assert.deepEqual(afters, [undefined, '2999-06-01T14:20:00.000Z', '2999-06-01T19:20:00.000Z'], '› asks for the slot after the shown one');
    await page.click('#social-slot-prev');
    assert.equal((await socialCalls(page, 'socialSlot')).length, 3, '‹ reuses slots already seen');
    await page.click('#social-go');
    await page.click('#social-go');
    await page.waitForFunction(() => window.__storageCalls.some(c => c[0] === 'socialSchedule'));
    const [[, req]] = await socialCalls(page, 'socialSchedule');
    assert.equal(req.date, '2999-06-01T19:20:00.000Z');
});

test('Pick a time sends the picked time', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Later');
    await page.click('#social-mode-link');
    await page.waitForFunction(() => /^Next open slot · /.test(document.getElementById('social-when-next').textContent));
    await page.click('#social-when-pick');
    const slot = new Date('2999-06-01T14:20:00Z');
    const local = new Date(slot.getTime() - slot.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    assert.equal(await page.$eval('#social-time', el => el.value), local, 'picker starts at the next open slot');
    await page.$eval('#social-time', el => { el.value = '2000-01-01T09:00'; el.dispatchEvent(new Event('change')); });
    await page.click('#social-go');
    assert.match(await page.$eval('#social-result', el => el.textContent), /passed/);
    await page.$eval('#social-time', el => { el.value = '2999-01-01T09:00'; el.dispatchEvent(new Event('change')); });
    await page.click('#social-go');
    await page.click('#social-go');
    await page.waitForFunction(() => window.__storageCalls.some(c => c[0] === 'socialSchedule'));
    const [[, req]] = await socialCalls(page, 'socialSchedule');
    assert.equal(req.mode, 'schedule');
    assert.equal(req.date, new Date('2999-01-01T09:00').toISOString());
});

test('a failed slot lookup still schedules into the next open slot', { ...SOCIAL_SIGNED_IN, socialSlotError: 'Postiz down' }, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Later');
    await page.click('#social-mode-link');
    await page.waitForFunction(() => /Could not look up the next open slot/.test(document.getElementById('social-result').textContent));
    assert.equal(await page.$eval('#social-when-next', el => el.textContent), 'Next open slot');
    assert.equal(await page.$eval('#social-go', el => el.textContent), 'Schedule 1 channel · next open slot');
    await page.click('#social-go');
    await page.click('#social-go');
    await page.waitForFunction(() => window.__storageCalls.some(c => c[0] === 'socialSchedule'));
    const [[, req]] = await socialCalls(page, 'socialSchedule');
    assert.equal(req.mode, 'schedule');
    assert.equal('date' in req, false, 'the server still asks Postiz at send time');
});

test('Draft from link fills the text without repeating the card URL', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await page.waitForFunction(() => !document.getElementById('social-draft-btn').hidden);
    await page.click('#social-draft-btn');
    await page.waitForFunction(() => document.getElementById('social-text').value === 'A sharp take');
    const [call] = await socialCalls(page, 'socialDraft');
    assert.equal(call[1], SHARED);
    assert.deepEqual(call[2].map(c => [c.id, c.max_length]), [['all', 15]], 'room left for the appended link');
});

test('a Postiz failure keeps the text and lets you retry', {
    ...SOCIAL_SIGNED_IN, socialScheduleError: 'Postiz rejected the API key',
}, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Keep me');
    await page.click('#social-go');
    await page.click('#social-go');
    await page.waitForFunction(() => document.getElementById('social-result').textContent.includes('Failed'));
    assert.match(await page.$eval('#social-result', el => el.textContent), /rejected the API key/);
    assert.equal(await page.$eval('#social-text', el => el.value), 'Keep me');
    assert.equal(await page.$eval('#social-go', el => el.disabled), false);
});

test('channels render from the device cache before Postiz answers', {
    ...SOCIAL_SIGNED_IN, path: '/?view=social', socialIntegrationsDelayMs: 3000,
    localStorage: { acquacotta_social_channels: JSON.stringify({ configured: true, default_channels: [], integrations: [{ id: 'm1', name: 'Me', identifier: 'mastodon', max_length: 500 }] }) },
}, async ({ page }) => {
    await page.waitForFunction(() => document.querySelectorAll('.social-chip').length > 0);
    assert.deepEqual(await page.$$eval('.social-chip', els => els.map(e => e.getAttribute('aria-label'))), ['Mastodon (Me)'],
        'cached channels while Postiz is still answering');
    await page.waitForFunction(() => document.querySelectorAll('.social-chip').length === 2, { timeout: 8000 });
    assert.match(await page.evaluate(() => localStorage.getItem('acquacotta_social_channels')), /Scott on X/, 'cache refreshed');
});

run(tests);
