/**
 * Offline stand-ins for the CDN libraries index.html loads (Chart.js and its
 * plugins, flatpickr), so tests/js/test_index.js never touches the network.
 */
(function () {
    'use strict';

    // Any method call on these returns another inert object, so chained calls work.
    const inert = () => new Proxy(function () {}, {
        get: (target, key) => (key === 'then' ? undefined : inert()),
        apply: () => inert(),
        construct: () => inert(),
    });

    if (!window.Chart) {
        window.Chart = class {
            constructor() { this.data = { datasets: [] }; this.options = {}; }
            destroy() {}
            update() {}
            resize() {}
            static register() {}
        };
        window.Chart.defaults = inert();
    }
    if (!window.ChartDataLabels) window.ChartDataLabels = {};
    if (!window.flatpickr) {
        window.flatpickr = () => ({
            setDate() {}, clear() {}, destroy() {}, set() {}, open() {}, close() {},
            selectedDates: [], config: {},
        });
        window.flatpickr.l10ns = { default: {} };
        window.flatpickr.localize = () => {};
    }
})();
