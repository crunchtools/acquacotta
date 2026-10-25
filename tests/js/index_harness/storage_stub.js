/**
 * Stand-in for static/js/storage.js when tests/js/test_index.js loads index.html.
 *
 * Driven by window.__TEST__ (set before the page's scripts run):
 *   settings     the object getSettings() returns
 *   plugins      the /api/plugins body pluginFetch() returns
 *   auth         what getAuthStatus() returns (default: logged out)
 *   rtConfig     what getRTConfig() returns
 *   socialIntegrations  what getSocialIntegrations() returns
 *   socialIntegrationsDelayMs  hold that answer this long (to see the cached render)
 *   socialDraft  what socialDraft() returns (the call is recorded)
 *   socialScheduleError  when set, socialSchedule() rejects with this message
 *   socialPreview / socialPreviewError  what socialPreview() returns, or its rejection
 *   socialSlotsError / socialSlotsDelayMs / socialSlotsTaken  see socialSlots() below
 *   holdPlugins  when true, /api/plugins waits for window.__releasePlugins()
 *
 * Every saveSettings() call is recorded in window.__storageCalls. Methods the
 * tests don't care about resolve to an empty array.
 */
(function () {
    'use strict';

    const cfg = window.__TEST__ || {};
    const clone = v => JSON.parse(JSON.stringify(v));
    const settings = clone(cfg.settings || {});
    const calls = window.__storageCalls = [];
    const json = body => new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
    });

    let release = () => {};
    const pluginGate = cfg.holdPlugins ? new Promise(r => { release = r; }) : Promise.resolve();
    window.__releasePlugins = () => release();

    const impl = {
        getSettings: async () => clone(settings),
        saveSettings: async s => {
            calls.push(['saveSettings', clone(s)]);
            Object.assign(settings, clone(s));
        },
        saveSetting: async (key, value) => {
            calls.push(['saveSetting', key, clone(value)]);
            settings[key] = clone(value);
        },
        getAuthStatus: () => cfg.auth || { logged_in: false },
        getActivePlugin: () => null,
        isLocalMode: () => !(cfg.auth && cfg.auth.logged_in),
        getStoredSpreadsheetId: () => null,
        getStoredLocationId: () => null,
        pluginFetch: async url => {
            if (url === '/api/plugins') {
                await pluginGate;
                return json(cfg.plugins || { plugins: [] });
            }
            return json({});
        },
        authenticatedFetch: async () => json({}),
        getRTConfig: async () => clone(cfg.rtConfig || {}),
        getSocialIntegrations: async () => {
            calls.push(['getSocialIntegrations']);
            if (cfg.socialIntegrationsDelayMs) await new Promise(r => setTimeout(r, cfg.socialIntegrationsDelayMs));
            return clone(cfg.socialIntegrations || { configured: false, integrations: [] });
        },
        socialPreview: async url => {
            calls.push(['socialPreview', url]);
            if (cfg.socialPreviewError) throw new Error(cfg.socialPreviewError);
            return clone(cfg.socialPreview || { url, title: '', site: 'example.com', image: '' });
        },
        // Three windows a day (10:20, 15:10, 20:00 local) for `days` days from
        // `startIso`, minus any listed in cfg.socialSlotsTaken; cfg.socialSlotsError
        // rejects, cfg.socialSlotsDelayMs holds the answer.
        socialSlots: async (channelId, startIso, days) => {
            calls.push(['socialSlots', channelId, startIso, days]);
            if (cfg.socialSlotsDelayMs) await new Promise(r => setTimeout(r, cfg.socialSlotsDelayMs));
            if (cfg.socialSlotsError) throw new Error(cfg.socialSlotsError);
            const slots = [];
            const taken = new Set(cfg.socialSlotsTaken || []);
            for (let i = 0; i < days; i++) {
                for (const [h, m] of [[10, 20], [15, 10], [20, 0]]) {
                    const d = new Date(startIso);
                    d.setDate(d.getDate() + i);
                    d.setHours(h, m, 0, 0);
                    if (d.getTime() > Date.now() && !taken.has(d.toISOString())) slots.push(d.toISOString());
                }
            }
            return { slots };
        },
        socialDraft: async (url, channels) => {
            calls.push(['socialDraft', url, clone(channels)]);
            return clone(cfg.socialDraft || { page: {}, drafts: [] });
        },
        socialSchedule: async request => {
            calls.push(['socialSchedule', clone(request)]);
            if (cfg.socialScheduleError) throw new Error(cfg.socialScheduleError);
            return { date: '2026-10-25T14:00:00Z', posts: [], warnings: [], postiz_url: 'https://postiz.example.com' };
        },
        // loadTodos() creates a list and reloads until one exists.
        getTodoLists: async () => [{ id: 'general', name: 'General', sort_order: 0 }],
        getSyncStatus: async () => ({}),
        getLocalPomodoroCount: async () => 0,
        // An empty report, shaped like the real one: the Reports tab renders it.
        getReport: async () => ({ total_minutes: 0, total_pomodoros: 0, by_type: {}, daily_totals: [], labels: [] }),
        getPomodorosPage: async () => ({ pomodoros: [], has_more: false }),
    };

    window.Storage = new Proxy(impl, {
        get: (target, key) => (key in target ? target[key] : async () => []),
    });
})();
