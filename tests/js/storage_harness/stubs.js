/**
 * Browser-side stubs for tests/js/test_storage_sync.js, loaded before utils.js and
 * storage.js. storage.js keeps its auth state in closure variables, so the harness
 * logs in the way production does: it leaves a pending login in sessionStorage for
 * consumePendingAuth() to write into IndexedDB during Storage.init().
 *
 * window.__net    fetch stub: records every call, answers from per-route handlers,
 *                 and can hold a route until the test releases it.
 * window.__timers setTimeout/clearTimeout stub: timers never fire on their own; the
 *                 test fires them, so retry and debounce delays are inspectable.
 */
(function() {
    'use strict';

    sessionStorage.setItem('acquacotta_pending_auth', JSON.stringify({
        credentials: { token: 'test-token', user_email: 'test@example.com' },
        settings: { spreadsheet_id: 'test-sheet' },
    }));

    const json = (status, body) => new Response(JSON.stringify(body), {
        status, headers: { 'Content-Type': 'application/json' },
    });

    const routes = {
        'GET /api/plugins': () => json(200, {
            plugins: [{ id: 'sheets', active: true, plugin_type: 'storage', frontend_fields: ['spreadsheet_id'] }],
        }),
        'GET /api/sheets/pomodoros': () => json(200, []),
        'GET /api/sheets/settings': () => json(200, {}),
        'GET /api/todos/sync': () => json(200, { todos: [], lists: [] }),
        'POST /api/todos/sync': () => json(200, { status: 'ok' }),
    };
    const held = {};

    window.__net = {
        calls: [],
        respond(route, status, body) { routes[route] = () => json(status, body); },
        hold(route) { held[route] = []; },
        // Answer every held request on a route, then stop holding it.
        release(route) {
            const waiting = held[route] || [];
            delete held[route];
            waiting.forEach(resolve => resolve(routes[route]()));
        },
        heldCount(route) { return (held[route] || []).length; },
        count(route) { return this.calls.filter(c => c.route === route).length; },
    };

    window.fetch = function(url, options = {}) {
        const route = `${(options.method || 'GET').toUpperCase()} ${new URL(url, location.href).pathname}`;
        window.__net.calls.push({ route, body: options.body ? JSON.parse(options.body) : null });
        if (held[route]) return new Promise(resolve => held[route].push(resolve));
        return Promise.resolve(routes[route] ? routes[route]() : json(404, { error: 'not stubbed' }));
    };

    let nextId = 1;
    const pending = new Map();
    window.__timers = {
        list() { return [...pending.entries()].map(([id, t]) => ({ id, delay: t.delay })); },
        // Run one queued timer and return whatever its callback returns.
        fire(id) {
            const t = pending.get(id);
            pending.delete(id);
            return t.fn();
        },
    };
    window.setTimeout = (fn, delay) => { const id = nextId++; pending.set(id, { fn, delay }); return id; };
    window.clearTimeout = id => { pending.delete(id); };
})();
