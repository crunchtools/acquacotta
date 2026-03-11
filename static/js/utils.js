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
        isToday: isToday
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
