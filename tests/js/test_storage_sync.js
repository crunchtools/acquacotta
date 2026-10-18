/**
 * Browser-level tests for the task-list sync state machine in static/js/storage.js:
 * the pending flag, the retry timer, and the refreshTodosFromCloudIfChanged poll.
 * The real storage.js runs logged in against a real IndexedDB; fetch and timers are
 * stubbed by storage_harness/stubs.js. Each test gets a fresh browser context.
 *
 * Run: node tests/js/test_storage_sync.js
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const puppeteer = require('puppeteer');

const ROOT = path.resolve(__dirname, '..', '..');
const PAGE = `<!DOCTYPE html><html><body>
<script src="/stubs.js"></script>
<script src="/static/js/utils.js"></script>
<script src="/static/js/storage.js"></script>
</body></html>`;

const SYNC = 'POST /api/todos/sync';
const POLL = 'GET /api/todos/sync';

const tests = [];
const test = (name, fn) => tests.push({ name, fn });

const state = page => page.evaluate(() => ({
    pending: !!Storage._todoSyncPending,
    failures: Storage._todoSyncFailures,
    timers: __timers.list(),
}));

// Fire the only queued timer and wait for the sync it runs.
async function fireOnly(page) {
    const { timers } = await state(page);
    assert.equal(timers.length, 1, `expected one queued timer, got ${JSON.stringify(timers)}`);
    await page.evaluate(id => __timers.fire(id), timers[0].id);
}

// Fire the only queued timer with the push held in flight, so a test can edit
// during the push before letting it answer.
async function startHeldPush(page) {
    await page.evaluate(route => __net.hold(route), SYNC);
    const { timers } = await state(page);
    assert.equal(timers.length, 1);
    await page.evaluate(id => { window.__push = __timers.fire(id); }, timers[0].id);
    await page.waitForFunction(route => __net.heldCount(route) === 1, {}, SYNC);
}

async function finishHeldPush(page, status) {
    await page.evaluate((route, s) => {
        __net.respond(route, s, s < 300 ? { status: 'ok' } : { error: 'boom' });
        __net.release(route);
        return window.__push;
    }, SYNC, status);
}

const createTodo = (page, title) => page.evaluate(t => Storage.createTodo({ title: t }), title);
const todoTitles = page => page.evaluate(async () => (await Storage.getTodos()).map(t => t.title));

test('a local edit marks the sync pending and debounces a push', async ({ page }) => {
    await createTodo(page, 'write tests');
    const s = await state(page);
    assert.equal(s.pending, true);
    assert.deepEqual(s.timers.map(t => t.delay), [2000]);
    assert.equal(await page.evaluate(r => __net.count(r), SYNC), 0, 'nothing pushed before the debounce fires');
});

test('a successful push sends local todos and clears pending', async ({ page }) => {
    await createTodo(page, 'write tests');
    await fireOnly(page);
    const s = await state(page);
    assert.equal(s.pending, false);
    assert.equal(s.failures, 0);
    assert.deepEqual(s.timers, []);
    const body = await page.evaluate(r => __net.calls.find(c => c.route === r).body, SYNC);
    assert.deepEqual(body.todos.map(t => t.title), ['write tests']);
});

test('a non-2xx push keeps the sync pending and schedules a backoff retry', async ({ page }) => {
    await createTodo(page, 'write tests');
    await page.evaluate(r => __net.respond(r, 500, { error: 'boom' }), SYNC);
    await fireOnly(page);
    let s = await state(page);
    assert.equal(s.pending, true);
    assert.equal(s.failures, 1);
    assert.equal(s.timers.length, 1);
    // syncRetryDelay(1): 30s with ±20% jitter.
    assert.ok(s.timers[0].delay >= 24000 && s.timers[0].delay <= 36000, `retry delay ${s.timers[0].delay}`);

    // The retry succeeds: pending clears and the failure count resets.
    await page.evaluate(r => __net.respond(r, 200, { status: 'ok' }), SYNC);
    await fireOnly(page);
    s = await state(page);
    assert.equal(s.pending, false);
    assert.equal(s.failures, 0);
    assert.deepEqual(s.timers, []);
});

test('a successful push does not clear pending when a newer edit is queued', async ({ page }) => {
    await createTodo(page, 'first');
    await startHeldPush(page);
    await createTodo(page, 'second');
    await finishHeldPush(page, 200);

    let s = await state(page);
    assert.equal(s.pending, true, 'the edit made during the push is still unsynced');
    assert.deepEqual(s.timers.map(t => t.delay), [2000], 'only the newer edit\'s debounce is queued');

    await fireOnly(page);
    s = await state(page);
    assert.equal(s.pending, false);
    const last = await page.evaluate(r => __net.calls.filter(c => c.route === r).pop().body, SYNC);
    assert.deepEqual(last.todos.map(t => t.title).sort(), ['first', 'second']);
});

test('a failure with a timer already queued does not add a second timer', async ({ page }) => {
    await createTodo(page, 'first');
    await startHeldPush(page);
    await createTodo(page, 'second');
    await finishHeldPush(page, 503);

    const s = await state(page);
    assert.equal(s.pending, true);
    assert.equal(s.failures, 1);
    assert.deepEqual(s.timers.map(t => t.delay), [2000], 'the queued debounce stands in for the retry');
});

test('a poll during pending does not touch the cloud or delete local todos', async ({ page }) => {
    await createTodo(page, 'unsynced');
    // The remote copy predates the edit and has no todos at all.
    const changed = await page.evaluate(() => Storage.refreshTodosFromCloudIfChanged());
    assert.equal(changed, false);
    assert.equal(await page.evaluate(r => __net.count(r), POLL), 0);
    assert.deepEqual(await todoTitles(page), ['unsynced']);
});

test('a poll after a failed push does not delete the unsynced todos', async ({ page }) => {
    // The #164 data-loss path: a failed push used to clear pending, so the next
    // poll reconciled local state to the stale remote copy.
    await createTodo(page, 'unsynced');
    await page.evaluate(r => __net.respond(r, 500, { error: 'boom' }), SYNC);
    await fireOnly(page);
    assert.equal(await page.evaluate(() => Storage.refreshTodosFromCloudIfChanged()), false);
    assert.deepEqual(await todoTitles(page), ['unsynced']);
});

test('a poll with nothing pending reconciles local todos to the cloud copy', async ({ page }) => {
    // Control for the two tests above: the same empty remote does delete once synced.
    await createTodo(page, 'deleted elsewhere');
    await fireOnly(page);
    assert.equal(await page.evaluate(() => Storage.refreshTodosFromCloudIfChanged()), true);
    assert.equal(await page.evaluate(r => __net.count(r), POLL), 1);
    assert.deepEqual(await todoTitles(page), []);
});

(async () => {
    const send = (res, type, body) => { res.writeHead(200, { 'Content-Type': type }); res.end(body); };
    const server = http.createServer((req, res) => {
        const url = new URL(req.url, 'http://localhost');
        if (url.pathname === '/') return send(res, 'text/html', PAGE);
        if (url.pathname === '/stubs.js') {
            return send(res, 'text/javascript', fs.readFileSync(path.join(__dirname, 'storage_harness', 'stubs.js')));
        }
        if (['/static/js/utils.js', '/static/js/storage.js'].includes(url.pathname)) {
            return send(res, 'text/javascript', fs.readFileSync(path.join(ROOT, url.pathname)));
        }
        res.writeHead(404);
        res.end();
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const baseUrl = `http://127.0.0.1:${server.address().port}`;
    const browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
    let failed = 0;
    for (const t of tests) {
        const context = await browser.createBrowserContext();
        try {
            const page = await context.newPage();
            page.setDefaultTimeout(10000);
            const errors = [];
            page.on('pageerror', err => errors.push(err.message));
            await page.goto(baseUrl + '/', { waitUntil: 'load' });
            await page.evaluate(async () => {
                await Storage.init({ google_configured: true });
                await Storage.whenInitialSyncDone();
            });
            assert.equal(await page.evaluate(() => Storage.getAuthStatus().logged_in), true, 'harness login did not take');
            await t.fn({ page });
            assert.deepEqual(errors, [], 'page threw');
            console.log(`  ✓ ${t.name}`);
        } catch (e) {
            failed++;
            console.log(`  ✗ ${t.name}\n      ${e.message.split('\n').join('\n      ')}`);
        } finally {
            await context.close();
        }
    }
    await browser.close();
    server.close();
    console.log(`\nstorage.js sync tests: ${tests.length - failed} passed, ${failed} failed`);
    process.exit(failed ? 1 : 0);
})();
