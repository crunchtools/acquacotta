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
    await page.waitForFunction(() => document.getElementById('social-status').textContent.includes('Sign in'));
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

const visible = (page, sel) => page.$eval(sel, el => el.offsetParent !== null);
const sent = async page => {
    await page.waitForFunction(() => window.__storageCalls.some(c => c[0] === 'socialSchedule'));
    return (await socialCalls(page, 'socialSchedule'))[0][1];
};
const scheduleReady = async page => {
    await page.click('#social-mode-schedule');
    await page.waitForFunction(() => /^Schedule · /.test(document.getElementById('social-go').textContent)
        && !document.getElementById('social-go').textContent.includes('next open slot'));
};

test('one tap posts now, with the card URL appended', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Worth a read');
    await page.click('#social-go');
    assert.deepEqual(await sent(page), { mode: 'now', posts: [{ integration_id: 'x1', identifier: 'x', text: 'Worth a read\n\n' + SHARED }] });
    await page.waitForFunction(() => document.getElementById('social-go').textContent === 'Posted ✓');
    assert.match(await page.$eval('#social-status', el => el.textContent), /^Posted /);
    assert.equal(await page.$eval('#social-text', el => el.value), '', 'composer clears');
    assert.equal(await page.$eval('#social-card', el => el.innerHTML), '', 'card clears');
});

test("a shared link's image is sent so every channel posts it as a photo", {
    ...SOCIAL_SIGNED_IN,
    socialPreview: { url: SHARED, title: 'T', site: 'example.com', image: '', image_url: 'https://cdn.example.com/i.png' },
}, async ({ page }) => {
    await composerReady(page);
    await page.waitForFunction(() => !document.querySelector('.social-card.loading'));
    await setSocialText(page, 'Worth a read');
    await page.click('#social-go');
    assert.equal((await sent(page)).image_url, 'https://cdn.example.com/i.png', 'the og image rides along on post');
});

test('removing the card drops the image from the post', {
    ...SOCIAL_SIGNED_IN,
    socialPreview: { url: SHARED, title: 'T', site: 'example.com', image: '', image_url: 'https://cdn.example.com/i.png' },
}, async ({ page }) => {
    await composerReady(page);
    await page.waitForFunction(() => !document.querySelector('.social-card.loading'));
    await page.click('.social-card-remove');
    await setSocialText(page, 'Just text');
    await page.click('#social-go');
    const req = await sent(page);
    assert.equal(req.image_url, undefined, 'no image once the card is removed');
    assert.equal(req.posts[0].text, 'Just text', 'and no URL appended either');
});

test('Post now shows no scheduling UI', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    assert.equal(await page.$eval('#social-mode-now', el => el.getAttribute('aria-checked')), 'true');
    assert.equal(await visible(page, '#social-when'), false, 'no slot row in Post now');
    assert.equal((await socialCalls(page, 'socialSlots')).length, 0, 'no slot lookup until Schedule');
});

test('over the limit names the channel and blocks posting', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await page.click('.social-card-remove');
    await setSocialText(page, 'x'.repeat(45));
    assert.equal(await page.$eval('#social-count', el => el.textContent), '−5 · too long for X');
    assert.equal(await page.$eval('#social-chip-0', el => el.classList.contains('over')), true);
    assert.equal(await page.$eval('#social-go', el => el.disabled), true);
    assert.equal(await page.evaluate(() => sessionStorage.getItem('acquacotta_pending_share')), null, 'removing the card drops the share');
});

test('Schedule defaults to the next open slot and one tap schedules it', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Later');
    await scheduleReady(page);
    assert.equal(await visible(page, '#social-when'), true);
    assert.equal(await page.$eval('#social-when-caption', el => el.textContent), 'Next open slot');
    const [[, channel, start, end]] = await socialCalls(page, 'socialSlots');
    assert.equal(channel, 'x1');
    const midnight = new Date(); midnight.setHours(0, 0, 0, 0);
    const weekOn = new Date(midnight); weekOn.setDate(weekOn.getDate() + 7);
    assert.equal(start, midnight.toISOString(), 'the week starts at local midnight');
    assert.equal(end, weekOn.toISOString(), 'and ends at the local midnight a week on');
    const first = await page.evaluate(() => socialSlots[0].toISOString());
    await page.click('#social-go');
    const req = await sent(page);
    assert.equal(req.mode, 'schedule');
    assert.equal(req.date, first, 'what the row shows is what gets scheduled');
    await page.waitForFunction(() => document.getElementById('social-go').textContent === 'Scheduled ✓');
    assert.match(await page.$eval('#social-status', el => el.textContent), /^Scheduled for /);
    assert.equal(await page.$eval('#social-mode-now', el => el.getAttribute('aria-checked')), 'true', 'back to Post now');
});

test('the slot sheet lists the week by day; picking a slot schedules it', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Later');
    await scheduleReady(page);
    await page.click('#social-when');
    assert.equal(await page.$eval('#social-sheet', el => el.open), true);
    assert.equal(await page.$$eval('.social-day', els => els.length), 7, 'one row per day');
    assert.equal(await page.$eval('.social-day-label', el => el.textContent), 'Today');
    const chips = await page.$$('.social-slot:not(.skeleton)');
    assert.ok(chips.length >= 18, 'three windows a day');
    assert.equal(await page.$$eval('.social-slot[aria-pressed="true"]', els => els.length), 1, 'the chosen slot is marked');
    const target = await page.evaluate(() => socialSlots[socialSlots.length - 1].getTime());
    await page.click(`.social-slot[onclick="socialPickSlot(${target})"]`);
    assert.equal(await page.$eval('#social-sheet', el => el.open), false, 'picking closes the sheet');
    assert.equal(await page.$eval('#social-when-caption', el => el.textContent), 'Open slot');
    await page.click('#social-go');
    assert.equal((await sent(page)).date, new Date(target).toISOString());
});

test('Next week appends seven more days', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Much later');
    await scheduleReady(page);
    await page.click('#social-when');
    await page.click('#social-more');
    await page.waitForFunction(() => document.querySelectorAll('.social-day').length === 14 && !document.querySelector('.social-slot.skeleton'));
    const calls = await socialCalls(page, 'socialSlots');
    const midnight = new Date(); midnight.setHours(0, 0, 0, 0);
    const next = new Date(midnight); next.setDate(next.getDate() + 7);
    assert.equal(calls[1][2], next.toISOString(), 'the second week starts where the first ended');
    const target = await page.evaluate(() => socialSlots[socialSlots.length - 1].getTime());
    await page.click(`.social-slot[onclick="socialPickSlot(${target})"]`);
    assert.match(await page.$eval('#social-go', el => el.textContent), /^Schedule · \w{3} \d+, /, 'beyond a week the button shows the date');
});

test('an exact time is the escape hatch', SOCIAL_SIGNED_IN, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'At four');
    await scheduleReady(page);
    await page.click('#social-when');
    await page.click('#social-exact-toggle');
    await page.$eval('#social-time', el => { el.value = '2000-01-01T09:00'; });
    await page.click('#social-exact button.primary');
    assert.equal(await page.$eval('#social-status', el => el.textContent), 'That time has passed');
    await page.$eval('#social-time', el => { el.value = '2999-01-01T16:45'; });
    await page.click('#social-exact button.primary');
    assert.equal(await page.$eval('#social-when-caption', el => el.textContent), 'Exact time');
    await page.click('#social-go');
    assert.equal((await sent(page)).date, new Date('2999-01-01T16:45').toISOString());
});

test('if Postiz is unreachable, Schedule still works and the row retries', { ...SOCIAL_SIGNED_IN, socialSlotsError: 'Postiz down' }, async ({ page }) => {
    await composerReady(page);
    await setSocialText(page, 'Later');
    await page.click('#social-mode-schedule');
    await page.waitForFunction(() => document.getElementById('social-when-caption').textContent === 'Couldn’t reach Postiz');
    assert.equal(await page.$eval('#social-go', el => el.textContent), 'Schedule · next open slot');
    await page.click('#social-when');
    await page.waitForFunction(() => window.__storageCalls.filter(c => c[0] === 'socialSlots').length === 2);
    assert.equal(await page.$eval('#social-sheet', el => el.open), false, 'tapping the row retries');
    await page.click('#social-go');
    const req = await sent(page);
    assert.equal(req.mode, 'schedule');
    assert.equal('date' in req, false, 'the server asks Postiz at send time');
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
    await page.waitForFunction(() => document.getElementById('social-status').textContent.includes('Failed'));
    assert.match(await page.$eval('#social-status', el => el.textContent), /rejected the API key/);
    assert.equal(await page.$eval('#social-status', el => el.classList.contains('error')), true);
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

// ---- Social → Posts ----
const CH = {
    x: { id: 'x1', name: 'Scott on X', identifier: 'x', picture: '' },
    li: { id: 'li1', name: 'Scott McCarty', identifier: 'linkedin', picture: '' },
    m: { id: 'm1', name: '@fatherlinux', identifier: 'mastodon', picture: '' },
};
const POSTS = [
    { id: 'old', days: -10, hour: 9, state: 'PUBLISHED', text: 'Ten days back', channel: CH.x },
    { id: 'lw1', group: 'lw', days: -3, hour: 9, state: 'PUBLISHED', text: 'Last week, partly failed', channel: CH.x },
    { id: 'lw2', group: 'lw', days: -3, hour: 9, state: 'ERROR', text: 'Last week, partly failed', channel: CH.li },
    { id: 'late', days: -1, hour: 9, state: 'QUEUE', text: 'Should have gone out', channel: CH.x },
    { id: 'up1', group: 'up', days: 2, hour: 10, minute: 20, state: 'QUEUE', text: 'Upcoming <b>post</b>', channel: CH.x },
    { id: 'up2', group: 'up', days: 2, hour: 10, minute: 20, state: 'QUEUE', text: 'Upcoming <b>post</b>', channel: CH.li },
    { id: 'draft', days: 4, hour: 15, state: 'DRAFT', text: 'A draft', channel: CH.li },
    { id: 'far', days: 9, hour: 9, state: 'QUEUE', text: 'Next week', channel: CH.x },
];
const POSTS_SIGNED_IN = { path: '/#social/posts', auth: { logged_in: true, email: 'test@example.com' }, socialPosts: POSTS };
const postsReady = page => page.waitForFunction(() => document.getElementById('social-posts').getAttribute('aria-busy') === 'false'
    && !document.querySelector('.social-post.skeleton') && !document.getElementById('social-pane-posts').hidden);
const dayLabels = page => page.$$eval('#social-posts .social-day-label', els => els.map(e => e.textContent));
const rowStates = page => page.$$eval('#social-posts .social-post', els => els.map(e => [e.querySelector('.social-post-text').textContent, e.querySelector('summary .social-post-state')?.textContent || '', e.classList.contains('failed')]));
const postsStatus = page => page.$eval('#social-posts-status', el => el.textContent);
const localDay = n => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return d.toISOString(); };
const channelLines = page => page.$$eval('.social-post[open] .social-post-ch', els => els.map(e => [e.querySelector('.social-post-ch-name').textContent, e.querySelector('.social-post-state').textContent]));

test('Posts opens on Today; empty days fold into one line; last week is collapsed and reports its failures', POSTS_SIGNED_IN, async ({ page }) => {
    await postsReady(page);
    const [[, start, end]] = await socialCalls(page, 'socialPosts');
    assert.equal(start, localDay(-7), 'last week is fetched with the first request');
    assert.equal(end, localDay(7));
    const labels = await dayLabels(page);
    assert.deepEqual(labels.slice(0, 2), ['Today', 'Tomorrow'], 'Today keeps its own block; a single empty day keeps its name');
    assert.match(labels[labels.length - 1], / – /, 'a run of empty days is one line');
    assert.equal(labels.length, 6);
    assert.equal(await page.$eval('#social-posts-earlier', el => el.textContent), '‹ Last week · 1 failed');
    assert.deepEqual(await rowStates(page), [['Upcoming <b>post</b>', '', false], ['A draft', 'Draft', false]],
        'one entry per post, not per channel; drafts say so; text renders as text');
    assert.deepEqual(await page.$eval('#social-posts .social-post > summary', row => [...row.querySelectorAll('.social-post-chip')].map(e => e.getAttribute('aria-label'))),
        ['Scott McCarty: Scheduled', 'Scott on X: Scheduled'], 'one chip per channel, labelled with its state');
});

test('revealing last week keeps Today in place and flags failed and unsent posts', POSTS_SIGNED_IN, async ({ page }) => {
    await postsReady(page);
    const top = () => page.$eval('.social-day-label.today', el => el.getBoundingClientRect().top);
    const before = await top();
    await page.click('#social-posts-earlier');
    assert.ok(Math.abs(await top() - before) < 2, 'Today does not move');
    assert.equal(await page.$eval('#social-posts-earlier', el => el.textContent), '‹ Earlier');
    assert.equal((await socialCalls(page, 'socialPosts')).length, 1, 'no new request to show last week');
    const states = await rowStates(page);
    assert.deepEqual(states.slice(0, 2), [['Last week, partly failed', '1 of 2 failed', true], ['Should have gone out', 'Not sent yet', false]]);
    await page.click('#social-posts-earlier');
    await page.waitForFunction(() => window.__storageCalls.filter(c => c[0] === 'socialPosts').length === 2
        && document.getElementById('social-posts').getAttribute('aria-busy') === 'false');
    assert.equal((await socialCalls(page, 'socialPosts'))[1][1], localDay(-14), 'Earlier fetches the week before');
    assert.ok((await rowStates(page)).some(r => r[0] === 'Ten days back'));
});

test('Next week appends seven days', POSTS_SIGNED_IN, async ({ page }) => {
    await postsReady(page);
    await page.click('#social-posts-later');
    await page.waitForFunction(() => window.__storageCalls.filter(c => c[0] === 'socialPosts').length === 2
        && document.getElementById('social-posts').getAttribute('aria-busy') === 'false');
    const calls = await socialCalls(page, 'socialPosts');
    assert.deepEqual(calls[1].slice(1), [localDay(7), localDay(14)]);
    assert.ok((await rowStates(page)).some(r => r[0] === 'Next week'));
});

test('an entry opens in place: the text once, then each channel; closing returns to #social/posts', POSTS_SIGNED_IN, async ({ page }) => {
    await postsReady(page);
    await page.click('#social-posts .social-post > summary');
    await page.waitForFunction(() => location.hash === '#social/post/up2', {}, 'the entry id is its first channel by name');
    assert.equal(await page.$$eval('.social-post[open] .social-post-full', els => els.length), 1, 'identical text shows once');
    assert.equal(await page.$$eval('.social-post[open] .social-post-version-cap', els => els.length), 0, 'no version captions when all agree');
    assert.deepEqual(await channelLines(page), [['Scott McCarty', 'Scheduled'], ['Scott on X', 'Scheduled']]);
    assert.equal(await page.$eval('.social-post[open] .social-postiz-link', el => el.href), 'https://postiz.example.com/');
    await page.click('.social-post[open] > summary');
    await page.waitForFunction(() => location.hash === '#social/posts');
    assert.equal(await page.$('.social-post[open]'), null);
});

test('posts made separately in Postiz with the same words at the same minute are one entry', {
    ...POSTS_SIGNED_IN,
    socialPosts: [
        { id: 'n1', group: 'g1', days: 1, hour: 12, state: 'QUEUE', text: 'Same words https://a.example/1', channel: CH.x },
        { id: 'n2', group: 'g2', days: 1, hour: 12, state: 'QUEUE', text: 'Same   words\nhttps://lnkd.in/x', channel: CH.li },
        { id: 'n3', group: 'g3', days: 1, hour: 12, state: 'QUEUE', text: 'Different words', channel: CH.m },
    ],
}, async ({ page }) => {
    await postsReady(page);
    const rows = await page.$$eval('#social-posts .social-post', els => els.map(e => [e.querySelector('.social-post-text').textContent, e.querySelectorAll('summary .social-post-chip').length, !!e.querySelector('.social-post-versions')]));
    assert.deepEqual(rows.map(r => r[1]).sort(), [1, 2], 'same words merge across groups; different words stay apart');
    assert.ok(rows.every(r => !r[2]), 'a link difference is not a separate version');
});

test('an entry whose X text differs shows two versions, captioned by channel', {
    ...POSTS_SIGNED_IN,
    socialPosts: [
        { id: 'v1', group: 'v', days: 1, hour: 12, state: 'QUEUE', text: 'Short take', channel: CH.x },
        { id: 'v2', group: 'v', days: 1, hour: 12, state: 'QUEUE', text: 'The longer take for LinkedIn and Mastodon', channel: CH.li },
        { id: 'v3', group: 'v', days: 1, hour: 12, state: 'QUEUE', text: 'The longer take for LinkedIn and Mastodon', channel: CH.m },
    ],
}, async ({ page }) => {
    await postsReady(page);
    assert.equal(await page.$eval('.social-post-versions', el => el.textContent), '· 2 versions');
    assert.equal(await page.$eval('.social-post-text', el => el.textContent), 'The longer take for LinkedIn and Mastodon', 'the version most channels carry leads');
    await page.click('#social-posts .social-post > summary');
    await page.waitForFunction(() => document.querySelector('.social-post[open]'));
    assert.deepEqual(await page.$$eval('.social-post[open] .social-post-version-cap', els => els.map(e => e.textContent)), ['On Mastodon, LinkedIn', 'On X']);
    assert.equal(await page.$$eval('.social-post[open] .social-post-full', els => els.length), 2);
});

test('a link to any channel of a post opens its entry', { ...POSTS_SIGNED_IN, path: '/#social/post/up1' }, async ({ page }) => {
    await page.waitForFunction(() => document.querySelector('.social-post[open]'));
    assert.equal(await page.$eval('.social-post[open] .social-post-full', el => el.textContent), 'Upcoming <b>post</b>');
    assert.equal(await page.evaluate(() => location.hash), '#social/post/up2', 'the link settles on the entry id');
});

test('a link to a post outside the first two weeks looks further and opens it', { ...POSTS_SIGNED_IN, path: '/#social/post/old' }, async ({ page }) => {
    await page.waitForFunction(() => document.querySelector('.social-post[open]'));
    assert.equal(await page.$eval('.social-post[open] .social-post-full', el => el.textContent), 'Ten days back');
    const ranges = (await socialCalls(page, 'socialPosts')).map(c => c.slice(1));
    assert.deepEqual(ranges.slice(-2), [[localDay(-63), localDay(-7)], [localDay(7), localDay(63)]]);
});

test('a link to a post that is gone says so', { ...POSTS_SIGNED_IN, path: '/#social/post/nope' }, async ({ page }) => {
    await page.waitForFunction(() => !document.getElementById('route-notice').hidden);
    assert.match(await page.$eval('#route-notice', el => el.textContent), /wasn’t found/);
    assert.equal(await page.$('.social-post[open]'), null);
});

test('Posts signed out asks to sign in', { path: '/#social/posts' }, async ({ page }) => {
    await page.waitForFunction(() => document.getElementById('social-posts-status').textContent.includes('Sign in'));
    assert.equal(await page.$eval('#social-posts-status button', el => el.textContent), 'Sign in with Google');
    assert.equal(await page.$eval('#social-posts-top', el => el.hidden), true, 'no week navigation');
});

test('Posts without Postiz offers to connect it', { ...POSTS_SIGNED_IN, socialPostsConfigured: false }, async ({ page }) => {
    await page.waitForFunction(() => document.getElementById('social-posts-status').textContent.includes('connected'));
    assert.equal(await postsStatus(page), 'Postiz isn’t connected yet.Connect Postiz');
    assert.equal(await page.$eval('#social-posts', el => el.innerHTML), '');
    assert.equal(await page.$eval('#social-posts-bottom', el => el.hidden), true);
});

test('Postiz unreachable with no copy: the list says so and retries', { ...POSTS_SIGNED_IN, socialPostsError: 'HTTP 502' }, async ({ page }) => {
    await page.waitForFunction(() => document.getElementById('social-posts').textContent.includes('Couldn’t reach Postiz'));
    assert.match(await page.$eval('#social-posts', el => el.textContent), /Couldn’t reach Postiz: HTTP 502\s*Retry/);
    await page.click('#social-posts .social-ghost');
    await page.waitForFunction(() => window.__storageCalls.filter(c => c[0] === 'socialPosts').length === 2);
});

test("Postiz unreachable with this account's copy: the copy shows, the status says why", {
    ...POSTS_SIGNED_IN,
    socialPostsError: 'HTTP 502',
    localStorage: {
        acquacotta_social_posts: JSON.stringify({ email: 'test@example.com', from: localDay(-7), postiz_url: '', posts: [
            { id: 'c1', group: 'c1', date: localDay(1), state: 'QUEUE', text: 'From the cache', release_url: '', channel: CH.x },
        ] }),
    },
}, async ({ page }) => {
    await page.waitForFunction(() => document.getElementById('social-posts-status').textContent.includes('last copy'));
    assert.equal(await postsStatus(page), 'Couldn’t reach Postiz · showing the last copyRetry');
    assert.equal(await page.$eval('#social-posts-status', el => el.classList.contains('error')), true);
    assert.deepEqual((await rowStates(page)).map(r => r[0]), ['From the cache']);
});

test("another account's cached posts never show", {
    ...POSTS_SIGNED_IN,
    socialPostsError: 'HTTP 502',
    localStorage: {
        acquacotta_social_posts: JSON.stringify({ email: 'someone@else.com', from: localDay(-7), postiz_url: '', posts: [
            { id: 'c1', group: 'c1', date: localDay(1), state: 'QUEUE', text: 'Not yours', release_url: '', channel: CH.x },
        ] }),
    },
}, async ({ page }) => {
    await page.waitForFunction(() => document.getElementById('social-posts').textContent.includes('Couldn’t reach Postiz'));
    assert.equal(await page.$eval('#social-posts', el => el.textContent.includes('Not yours')), false);
});

test('paging after Postiz is disconnected shows the connect prompt, not empty weeks', POSTS_SIGNED_IN, async ({ page }) => {
    await postsReady(page);
    await page.evaluate(() => { window.__TEST__.socialPostsConfigured = false; });
    await page.click('#social-posts-later');
    await page.waitForFunction(() => document.getElementById('social-posts-status').textContent.includes('connected'));
    assert.equal(await page.$eval('#social-posts-bottom', el => el.hidden), true);
});

run(tests);
