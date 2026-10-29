/**
 * Acquacotta Utility Functions
 *
 * Pure functions extracted for testability.
 * These functions have no DOM dependencies and can be tested in isolation.
 */

// Make functions available globally for browser use
// and export for testing environments
(function(global) {
    'use strict';

    /**
     * Detect if the date has changed since the last known date.
     * Used to refresh views at midnight or when returning from background.
     *
     * @param {string|null} lastKnownDate - Previous date string (YYYY-MM-DD) or null
     * @param {Date} now - Current date/time
     * @param {string} timezone - IANA timezone string (e.g., 'America/New_York')
     * @returns {object} - { changed: boolean, newDate: string }
     */
    function detectDateChange(lastKnownDate, now, timezone) {
        const todayStr = now.toLocaleDateString('en-CA', { timeZone: timezone });
        const changed = lastKnownDate !== null && lastKnownDate !== todayStr;
        return { changed: changed, newDate: todayStr };
    }

    /**
     * Format a date according to the specified format.
     *
     * @param {Date|string} date - Date to format
     * @param {string} format - 'us' (MM/DD/YYYY), 'eu' (DD/MM/YYYY), or 'iso' (YYYY-MM-DD)
     * @returns {string} - Formatted date string
     */
    function formatDate(date, format) {
        const d = new Date(date);
        const day = d.getDate();
        const month = d.getMonth() + 1;
        const year = d.getFullYear();

        if (format === 'eu') {
            return day + '/' + month + '/' + year;
        } else if (format === 'iso') {
            return year + '-' + String(month).padStart(2, '0') + '-' + String(day).padStart(2, '0');
        } else {
            // US format (default)
            return month + '/' + day + '/' + year;
        }
    }

    /**
     * Format a date with day name.
     *
     * @param {Date|string} date - Date to format
     * @param {string} format - 'us', 'eu', or 'iso'
     * @returns {string} - Formatted date string with day name
     */
    function formatDateWithDay(date, format) {
        const d = new Date(date);
        const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
        const dayName = dayNames[d.getDay()];
        const day = d.getDate();
        const month = d.getMonth() + 1;
        const monthName = monthNames[d.getMonth()];
        const year = d.getFullYear();

        if (format === 'eu') {
            return dayName + ', ' + day + ' ' + monthName + ' ' + year;
        } else if (format === 'iso') {
            return dayName + ', ' + year + '-' + String(month).padStart(2, '0') + '-' + String(day).padStart(2, '0');
        } else {
            // US format (default)
            return dayName + ', ' + monthName + ' ' + day + ', ' + year;
        }
    }

    /**
     * Get date range for a period (day, week, or month).
     *
     * @param {string} period - 'day', 'week', or 'month'
     * @param {string} dateStr - Reference date in YYYY-MM-DD format
     * @returns {object} - { start: ISO string, end: ISO string }
     */
    function getDateRange(period, dateStr) {
        // Parse date string as local time (not UTC) by appending time component
        const refDate = new Date(dateStr + 'T00:00:00');
        var start, end;

        if (period === 'day') {
            start = new Date(refDate);
            start.setHours(0, 0, 0, 0);
            end = new Date(start);
            end.setDate(end.getDate() + 1);
        } else if (period === 'week') {
            start = new Date(refDate);
            start.setDate(refDate.getDate() - refDate.getDay());
            start.setHours(0, 0, 0, 0);
            end = new Date(start);
            end.setDate(start.getDate() + 7);
        } else {
            // month
            start = new Date(refDate.getFullYear(), refDate.getMonth(), 1);
            end = new Date(refDate.getFullYear(), refDate.getMonth() + 1, 1);
        }

        return {
            start: start.toISOString(),
            end: end.toISOString()
        };
    }

    /**
     * Derive date format from timezone region.
     *
     * @param {string} tz - IANA timezone string
     * @returns {string} - 'us', 'eu', or 'iso'
     */
    function getDateFormatForTimezone(tz) {
        if (!tz) return 'us';

        // America/* -> US format (MM/DD/YYYY, 12hr, Sunday first)
        if (tz.startsWith('America/') || tz.startsWith('US/')) {
            return 'us';
        }

        // Asia/* -> ISO format (YYYY-MM-DD, 24hr)
        if (tz.startsWith('Asia/')) {
            return 'iso';
        }

        // Europe/*, Africa/*, etc. -> EU format (DD/MM/YYYY, 24hr, Monday first)
        if (tz.startsWith('Europe/') || tz.startsWith('Africa/') ||
            tz.startsWith('Atlantic/') || tz.startsWith('Indian/')) {
            return 'eu';
        }

        // Default to US format
        return 'us';
    }

    /**
     * Snap minutes to nearest 30-minute interval.
     *
     * @param {number} minutes - Minutes value (0-59)
     * @returns {number} - Snapped minutes (0, 30, or 60)
     */
    function snapTo30Minutes(minutes) {
        return Math.round(minutes / 30) * 30;
    }

    /**
     * Format time as HH:MM with 30-minute snapping.
     *
     * @param {Date} date - Date object
     * @returns {string} - Time string in HH:MM format
     */
    function formatTimeSnapped(date) {
        const snappedMinutes = snapTo30Minutes(date.getMinutes());
        const hours = snappedMinutes >= 60 ? date.getHours() + 1 : date.getHours();
        return String(hours % 24).padStart(2, '0') + ':' + String(snappedMinutes % 60).padStart(2, '0');
    }

    /**
     * Calculate duration between two times in minutes.
     *
     * @param {Date|string} startTime - Start time
     * @param {Date|string} endTime - End time
     * @returns {number} - Duration in minutes
     */
    function calculateDuration(startTime, endTime) {
        const start = new Date(startTime);
        const end = new Date(endTime);
        return Math.round((end - start) / (1000 * 60));
    }

    /**
     * Format minutes as human-readable duration.
     *
     * @param {number} minutes - Duration in minutes
     * @returns {string} - Formatted string (e.g., "2h 30m" or "45m")
     */
    function formatMinutesAsDuration(minutes) {
        if (minutes < 60) {
            return minutes + 'm';
        }
        const hours = Math.floor(minutes / 60);
        const mins = minutes % 60;
        if (mins === 0) {
            return hours + 'h';
        }
        return hours + 'h ' + mins + 'm';
    }

    /**
     * Get today's date string in YYYY-MM-DD format for a timezone.
     *
     * @param {string} timezone - IANA timezone string
     * @returns {string} - Date string in YYYY-MM-DD format
     */
    function getTodayString(timezone) {
        return new Date().toLocaleDateString('en-CA', { timeZone: timezone });
    }

    /**
     * Check if a date string is today.
     *
     * @param {string} dateStr - Date string in YYYY-MM-DD format
     * @param {string} timezone - IANA timezone string
     * @returns {boolean} - True if date is today
     */
    function isToday(dateStr, timezone) {
        return dateStr === getTodayString(timezone);
    }

    /**
     * Delay before retrying a failed cloud sync: doubles per failure from 30s,
     * capped at 10 minutes, scaled by ±20% jitter so clients that failed
     * together don't retry together.
     *
     * @param {number} failures - Consecutive failures so far (1 for the first)
     * @param {number} [rand] - Value in [0, 1) for the jitter; Math.random() if omitted
     * @returns {number} - Delay in milliseconds
     */
    function syncRetryDelay(failures, rand) {
        const base = Math.min(30000 * Math.pow(2, Math.max(failures, 1) - 1), 600000);
        const r = rand === undefined ? Math.random() : rand;
        return Math.round(base * (0.8 + 0.4 * r));
    }

    /**
     * Where a horizontal swipe on the mobile week view should land. Swipes
     * shorter than 50px or not clearly horizontal are ignored; swiping past
     * either end of the week rolls into the adjacent week.
     *
     * @param {number} index - Currently selected day (0-6)
     * @param {number} dx - Horizontal travel in px (negative = swipe left)
     * @param {number} dy - Vertical travel in px
     * @returns {object|null} - { index, weekDelta } or null if not a swipe
     */
    function weekSwipeTarget(index, dx, dy) {
        if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.5) return null;
        const next = index + (dx < 0 ? 1 : -1);
        if (next > 6) return { index: 0, weekDelta: 1 };
        if (next < 0) return { index: 6, weekDelta: -1 };
        return { index: next, weekDelta: 0 };
    }

    /**
     * Resolve the user's saved tab order against the tabs that actually exist.
     * Unknown or repeated ids are dropped; a tab missing from the saved order
     * (e.g. a newly added plugin) is slotted in after its default predecessor.
     *
     * @param {Array|undefined} saved - The user's tab_order setting
     * @param {Array} available - Tab ids in default order
     * @returns {Array} - A complete ordering of the available tabs
     */
    function resolveTabOrder(saved, available) {
        if (!Array.isArray(saved)) return available.slice();
        const order = saved.filter((id, i) => available.indexOf(id) !== -1 && saved.indexOf(id) === i);
        available.forEach((id, i) => {
            if (order.indexOf(id) !== -1) return;
            const before = available.slice(0, i).reverse().find(prev => order.indexOf(prev) !== -1);
            order.splice(before === undefined ? 0 : order.indexOf(before) + 1, 0, id);
        });
        return order;
    }

    /**
     * Parse a deep-link hash: "#view", "#view/arg" or "#view/kind/id".
     * Segments are URI-decoded; a malformed escape makes the whole route invalid.
     *
     * @param {string} hash - location.hash, with or without the leading "#"
     * @returns {object|null} - { view, kind, id } (missing parts are ''), or null
     */
    function parseRoute(hash) {
        var raw = String(hash || '').replace(/^#?\/?/, '');
        if (!raw) return null;
        var parts = raw.split('/');
        if (parts.length > 3) parts = parts.slice(0, 2).concat([parts.slice(2).join('/')]);
        try {
            parts = parts.map(decodeURIComponent);
        } catch (e) {
            console.warn('Ignoring malformed deep link:', e.message);
            return null;
        }
        if (!/^[a-z][a-z0-9_-]*$/.test(parts[0])) return null;
        return { view: parts[0], kind: parts[1] || '', id: parts[2] || '' };
    }

    /**
     * Build a deep-link hash; the inverse of parseRoute. Empty trailing parts are dropped.
     *
     * @param {string} view - Tab id (e.g. 'todos')
     * @param {string} [kind] - Sub-route (e.g. 'item', 'list', 'week')
     * @param {string} [id] - Item id or name
     * @returns {string} - e.g. "#todos/item/0f3c…"
     */
    function formatRoute(view, kind, id) {
        var parts = [view, kind, id].map(function(p) { return p === undefined || p === null ? '' : String(p); });
        while (parts.length > 1 && !parts[parts.length - 1]) parts.pop();
        return '#' + parts.map(encodeURIComponent).join('/');
    }

    /**
     * Whether a cached Social posts window may be shown: it must belong to the
     * signed-in account and be the same window. No account, no cache.
     *
     * @param {object|null} cached - { email, from, posts } from localStorage
     * @param {string} email - The signed-in account's email
     * @param {string} from - The window start, ISO-8601
     * @returns {boolean}
     */
    function socialPostsCacheUsable(cached, email, from) {
        return !!cached && !!email && cached.email === email && cached.from === from;
    }

    /**
     * Build the RT settings save payload from the form, or explain what's missing.
     * A blank secret input keeps the saved one (secrets are never read back).
     * Choosing the token clears basic_user, because a saved username wins over it.
     *
     * @param {object} form - { method: 'basic'|'token', baseUrl, publicUrl, query, user, pass, token }
     * @param {object} saved - Last server config: { has_basic_pass, has_rest_token }
     * @returns {object} - { payload } or { error }
     */
    function buildRTConfigPayload(form, saved) {
        const known = saved || {};
        if (form.method === 'basic' && (!form.user || !(form.pass || known.has_basic_pass))) {
            return { error: 'Enter your RT username and password.' };
        }
        if (form.method === 'token' && !(form.token || known.has_rest_token)) {
            return { error: 'Paste an RT REST token.' };
        }
        const payload = {
            base_url: form.baseUrl,
            public_url: form.publicUrl,
            query: form.query,
            basic_user: form.method === 'basic' ? form.user : '',
        };
        if (form.method === 'basic' && form.pass) payload.basic_pass = form.pass;
        if (form.method === 'token' && form.token) payload.rest_token = form.token;
        return { payload: payload };
    }

    // Export functions
    var utils = {
        detectDateChange: detectDateChange,
        formatDate: formatDate,
        formatDateWithDay: formatDateWithDay,
        getDateRange: getDateRange,
        getDateFormatForTimezone: getDateFormatForTimezone,
        snapTo30Minutes: snapTo30Minutes,
        formatTimeSnapped: formatTimeSnapped,
        calculateDuration: calculateDuration,
        formatMinutesAsDuration: formatMinutesAsDuration,
        getTodayString: getTodayString,
        isToday: isToday,
        syncRetryDelay: syncRetryDelay,
        weekSwipeTarget: weekSwipeTarget,
        resolveTabOrder: resolveTabOrder,
        parseRoute: parseRoute,
        formatRoute: formatRoute,
        socialPostsCacheUsable: socialPostsCacheUsable,
        buildRTConfigPayload: buildRTConfigPayload
    };

    // Browser global
    if (typeof window !== 'undefined') {
        window.AcquacottaUtils = utils;
    }

    // CommonJS/Node.js
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = utils;
    }

    // AMD
    if (typeof define === 'function' && define.amd) {
        define(function() { return utils; });
    }

})(this);
