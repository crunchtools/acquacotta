/**
 * Unit tests for Acquacotta utility functions.
 * Browser-based test runner - no npm/node required.
 */

// Simple test framework
var testResults = [];
var currentSuite = '';

function describe(suiteName, fn) {
    currentSuite = suiteName;
    fn();
}

function it(testName, fn) {
    var result = {
        suite: currentSuite,
        name: testName,
        pass: false,
        error: null
    };

    try {
        fn();
        result.pass = true;
    } catch (e) {
        result.error = e.message || String(e);
    }

    testResults.push(result);
}

function expect(actual) {
    return {
        toBe: function(expected) {
            if (actual !== expected) {
                throw new Error('Expected ' + JSON.stringify(expected) + ' but got ' + JSON.stringify(actual));
            }
        },
        toEqual: function(expected) {
            var actualStr = JSON.stringify(actual);
            var expectedStr = JSON.stringify(expected);
            if (actualStr !== expectedStr) {
                throw new Error('Expected ' + expectedStr + ' but got ' + actualStr);
            }
        },
        toBeTruthy: function() {
            if (!actual) {
                throw new Error('Expected truthy value but got ' + JSON.stringify(actual));
            }
        },
        toBeFalsy: function() {
            if (actual) {
                throw new Error('Expected falsy value but got ' + JSON.stringify(actual));
            }
        },
        toContain: function(expected) {
            if (actual.indexOf(expected) === -1) {
                throw new Error('Expected ' + JSON.stringify(actual) + ' to contain ' + JSON.stringify(expected));
            }
        },
        toBeGreaterThan: function(expected) {
            if (actual <= expected) {
                throw new Error('Expected ' + actual + ' to be greater than ' + expected);
            }
        },
        toBeLessThan: function(expected) {
            if (actual >= expected) {
                throw new Error('Expected ' + actual + ' to be less than ' + expected);
            }
        }
    };
}

// Get utility functions
var utils = window.AcquacottaUtils;

// Test suites (describe/it blocks) below exercise each utility function.

describe('detectDateChange', function() {
    it('should return changed=false for initial state (null lastKnownDate)', function() {
        var now = new Date('2024-01-15T10:00:00Z');
        var result = utils.detectDateChange(null, now, 'UTC');

        expect(result.changed).toBe(false);
        expect(result.newDate).toBe('2024-01-15');
    });

    it('should return changed=false when date is the same', function() {
        var now = new Date('2024-01-15T23:59:59Z');
        var result = utils.detectDateChange('2024-01-15', now, 'UTC');

        expect(result.changed).toBe(false);
        expect(result.newDate).toBe('2024-01-15');
    });

    it('should return changed=true when date has changed (midnight crossing)', function() {
        var now = new Date('2024-01-16T00:01:00Z');
        var result = utils.detectDateChange('2024-01-15', now, 'UTC');

        expect(result.changed).toBe(true);
        expect(result.newDate).toBe('2024-01-16');
    });

    it('should respect timezone when detecting date change', function() {
        // At midnight UTC, it's still 7pm EST the previous day
        var now = new Date('2024-01-16T00:00:00Z');

        // In UTC, date has changed
        var utcResult = utils.detectDateChange('2024-01-15', now, 'UTC');
        expect(utcResult.changed).toBe(true);

        // In America/New_York (EST = UTC-5), still Jan 15
        var estResult = utils.detectDateChange('2024-01-15', now, 'America/New_York');
        expect(estResult.changed).toBe(false);
        expect(estResult.newDate).toBe('2024-01-15');
    });

    it('should detect date change when returning from background after midnight', function() {
        // Simulating user leaving app at 11pm, returning at 2am next day
        var lastKnownDate = '2024-01-15';
        var returnTime = new Date('2024-01-16T02:00:00Z');

        var result = utils.detectDateChange(lastKnownDate, returnTime, 'UTC');

        expect(result.changed).toBe(true);
        expect(result.newDate).toBe('2024-01-16');
    });
});

describe('formatDate', function() {
    it('should format date in US format (MM/DD/YYYY)', function() {
        var date = new Date('2024-01-15T12:00:00Z');
        var result = utils.formatDate(date, 'us');
        expect(result).toBe('1/15/2024');
    });

    it('should format date in EU format (DD/MM/YYYY)', function() {
        var date = new Date('2024-01-15T12:00:00Z');
        var result = utils.formatDate(date, 'eu');
        expect(result).toBe('15/1/2024');
    });

    it('should format date in ISO format (YYYY-MM-DD)', function() {
        var date = new Date('2024-01-15T12:00:00Z');
        var result = utils.formatDate(date, 'iso');
        expect(result).toBe('2024-01-15');
    });

    it('should default to US format when no format specified', function() {
        var date = new Date('2024-03-25T12:00:00Z');
        // Note: This will use local timezone, so we test format pattern
        var result = utils.formatDate(date);
        // US format pattern: M/D/YYYY (may vary by local timezone)
        expect(result).toContain('/');
    });

    it('should handle string date input', function() {
        // Use midday UTC to avoid timezone issues (midnight UTC becomes previous day in western timezones)
        var result = utils.formatDate('2024-07-04T12:00:00Z', 'iso');
        expect(result).toBe('2024-07-04');
    });
});

describe('formatDateWithDay', function() {
    it('should include day name in US format', function() {
        var date = new Date('2024-01-15T12:00:00Z');
        var result = utils.formatDateWithDay(date, 'us');
        expect(result).toContain('Mon');
        expect(result).toContain('Jan');
        expect(result).toContain('15');
    });

    it('should include day name in EU format', function() {
        var date = new Date('2024-01-15T12:00:00Z');
        var result = utils.formatDateWithDay(date, 'eu');
        expect(result).toContain('Mon');
        expect(result).toContain('15 Jan');
    });

    it('should include day name in ISO format', function() {
        var date = new Date('2024-01-15T12:00:00Z');
        var result = utils.formatDateWithDay(date, 'iso');
        expect(result).toContain('Mon');
        expect(result).toContain('2024-01-15');
    });
});

describe('getDateRange', function() {
    it('should return day range correctly', function() {
        var result = utils.getDateRange('day', '2024-01-15');

        var start = new Date(result.start);
        var end = new Date(result.end);

        expect(start.getDate()).toBe(15);
        expect(end.getDate()).toBe(16);
    });

    it('should return week range correctly', function() {
        var result = utils.getDateRange('week', '2024-01-15'); // Monday

        var start = new Date(result.start);
        var end = new Date(result.end);

        // Week should span 7 days
        var diffDays = (end - start) / (1000 * 60 * 60 * 24);
        expect(diffDays).toBe(7);
    });

    it('should return month range correctly', function() {
        var result = utils.getDateRange('month', '2024-01-15');

        var start = new Date(result.start);
        var end = new Date(result.end);

        expect(start.getDate()).toBe(1);
        expect(start.getMonth()).toBe(0); // January
        expect(end.getMonth()).toBe(1); // February
    });

    it('should handle month boundary correctly', function() {
        // December should go to January next year
        var result = utils.getDateRange('month', '2024-12-15');

        var start = new Date(result.start);
        var end = new Date(result.end);

        expect(start.getMonth()).toBe(11); // December
        expect(end.getMonth()).toBe(0); // January
        expect(end.getFullYear()).toBe(2025);
    });
});

describe('getDateFormatForTimezone', function() {
    it('should return us format for America timezones', function() {
        expect(utils.getDateFormatForTimezone('America/New_York')).toBe('us');
        expect(utils.getDateFormatForTimezone('America/Los_Angeles')).toBe('us');
        expect(utils.getDateFormatForTimezone('US/Eastern')).toBe('us');
    });

    it('should return eu format for Europe timezones', function() {
        expect(utils.getDateFormatForTimezone('Europe/London')).toBe('eu');
        expect(utils.getDateFormatForTimezone('Europe/Paris')).toBe('eu');
    });

    it('should return iso format for Asia timezones', function() {
        expect(utils.getDateFormatForTimezone('Asia/Tokyo')).toBe('iso');
        expect(utils.getDateFormatForTimezone('Asia/Shanghai')).toBe('iso');
    });

    it('should return us format for null/undefined', function() {
        expect(utils.getDateFormatForTimezone(null)).toBe('us');
        expect(utils.getDateFormatForTimezone(undefined)).toBe('us');
    });
});

describe('snapTo30Minutes', function() {
    it('should snap 0-14 to 0', function() {
        expect(utils.snapTo30Minutes(0)).toBe(0);
        expect(utils.snapTo30Minutes(14)).toBe(0);
    });

    it('should snap 15-44 to 30', function() {
        expect(utils.snapTo30Minutes(15)).toBe(30);
        expect(utils.snapTo30Minutes(30)).toBe(30);
        expect(utils.snapTo30Minutes(44)).toBe(30);
    });

    it('should snap 45-59 to 60', function() {
        expect(utils.snapTo30Minutes(45)).toBe(60);
        expect(utils.snapTo30Minutes(59)).toBe(60);
    });
});

describe('formatTimeSnapped', function() {
    it('should format time with snapped minutes', function() {
        var date = new Date('2024-01-15T10:14:00');
        expect(utils.formatTimeSnapped(date)).toBe('10:00');
    });

    it('should handle hour rollover when snapping to 60', function() {
        var date = new Date('2024-01-15T10:45:00');
        expect(utils.formatTimeSnapped(date)).toBe('11:00');
    });

    it('should handle midnight rollover', function() {
        var date = new Date('2024-01-15T23:45:00');
        expect(utils.formatTimeSnapped(date)).toBe('00:00');
    });
});

describe('calculateDuration', function() {
    it('should calculate duration in minutes', function() {
        var start = '2024-01-15T10:00:00Z';
        var end = '2024-01-15T10:25:00Z';
        expect(utils.calculateDuration(start, end)).toBe(25);
    });

    it('should handle date objects', function() {
        var start = new Date('2024-01-15T10:00:00Z');
        var end = new Date('2024-01-15T11:30:00Z');
        expect(utils.calculateDuration(start, end)).toBe(90);
    });
});

describe('formatMinutesAsDuration', function() {
    it('should format minutes only when under an hour', function() {
        expect(utils.formatMinutesAsDuration(25)).toBe('25m');
        expect(utils.formatMinutesAsDuration(45)).toBe('45m');
    });

    it('should format hours only when even hours', function() {
        expect(utils.formatMinutesAsDuration(60)).toBe('1h');
        expect(utils.formatMinutesAsDuration(120)).toBe('2h');
    });

    it('should format hours and minutes', function() {
        expect(utils.formatMinutesAsDuration(90)).toBe('1h 30m');
        expect(utils.formatMinutesAsDuration(150)).toBe('2h 30m');
    });
});

describe('isToday', function() {
    it('should return true for today', function() {
        var today = utils.getTodayString('UTC');
        expect(utils.isToday(today, 'UTC')).toBe(true);
    });

    it('should return false for yesterday', function() {
        var yesterday = new Date();
        yesterday.setDate(yesterday.getDate() - 1);
        var yesterdayStr = yesterday.toISOString().split('T')[0];
        expect(utils.isToday(yesterdayStr, 'UTC')).toBe(false);
    });
});

describe('syncRetryDelay', function() {
    it('should start at 30 seconds with no jitter at the midpoint', function() {
        expect(utils.syncRetryDelay(1, 0.5)).toBe(30000);
    });

    it('should double per consecutive failure', function() {
        expect(utils.syncRetryDelay(2, 0.5)).toBe(60000);
        expect(utils.syncRetryDelay(3, 0.5)).toBe(120000);
    });

    it('should cap at 10 minutes', function() {
        expect(utils.syncRetryDelay(6, 0.5)).toBe(600000);
        expect(utils.syncRetryDelay(50, 0.5)).toBe(600000);
    });

    it('should apply jitter of plus or minus 20 percent', function() {
        expect(utils.syncRetryDelay(1, 0)).toBe(24000);
        expect(utils.syncRetryDelay(1, 0.999)).toBe(35988);
    });

    it('should treat a zero or negative count as the first failure', function() {
        expect(utils.syncRetryDelay(0, 0.5)).toBe(30000);
    });
});

describe('weekSwipeTarget', function() {
    it('should move to the next day on a left swipe', function() {
        expect(JSON.stringify(utils.weekSwipeTarget(2, -80, 5))).toBe('{"index":3,"weekDelta":0}');
    });

    it('should move to the previous day on a right swipe', function() {
        expect(JSON.stringify(utils.weekSwipeTarget(2, 80, 5))).toBe('{"index":1,"weekDelta":0}');
    });

    it('should roll forward into next week from the last day', function() {
        expect(JSON.stringify(utils.weekSwipeTarget(6, -80, 0))).toBe('{"index":0,"weekDelta":1}');
    });

    it('should roll back into last week from the first day', function() {
        expect(JSON.stringify(utils.weekSwipeTarget(0, 80, 0))).toBe('{"index":6,"weekDelta":-1}');
    });

    it('should ignore short swipes', function() {
        expect(utils.weekSwipeTarget(3, -40, 0)).toBe(null);
    });

    it('should ignore mostly vertical swipes so scrolling still works', function() {
        expect(utils.weekSwipeTarget(3, -80, 70)).toBe(null);
    });
});

describe('resolveTabOrder', function() {
    var tabs = ['timer', 'reports', 'history', 'todos', 'rt', 'settings'];

    it('should use the default order when nothing is saved', function() {
        expect(utils.resolveTabOrder(undefined, tabs).join()).toBe(tabs.join());
    });

    it('should honor a complete saved order', function() {
        var saved = ['rt', 'todos', 'timer', 'reports', 'history', 'settings'];
        expect(utils.resolveTabOrder(saved, tabs).join()).toBe(saved.join());
    });

    it('should drop unknown and repeated ids', function() {
        var saved = ['rt', 'gone', 'rt', 'timer', 'reports', 'history', 'todos', 'settings'];
        expect(utils.resolveTabOrder(saved, tabs).join()).toBe('rt,timer,reports,history,todos,settings');
    });

    it('should slot a new tab in after its default predecessor', function() {
        var saved = ['settings', 'todos', 'timer', 'reports', 'history'];
        expect(utils.resolveTabOrder(saved, tabs).join()).toBe('settings,todos,rt,timer,reports,history');
    });

    it('should put a new first tab at the front', function() {
        expect(utils.resolveTabOrder(['reports', 'history'], ['timer', 'reports', 'history']).join()).toBe('timer,reports,history');
    });
});

describe('parseRoute / formatRoute', function() {
    it('should parse a bare tab', function() {
        expect(utils.parseRoute('#todos')).toEqual({ view: 'todos', kind: '', id: '' });
    });

    it('should parse a tab with a sub-route', function() {
        expect(utils.parseRoute('#reports/month')).toEqual({ view: 'reports', kind: 'month', id: '' });
    });

    it('should parse an item and decode it', function() {
        expect(utils.parseRoute('#discussions/person/Jane%20Doe')).toEqual({ view: 'discussions', kind: 'person', id: 'Jane Doe' });
    });

    it('should keep extra slashes in the id', function() {
        expect(utils.parseRoute('#rt/queue/a/b').id).toBe('a/b');
    });

    it('should accept a leading slash and no hash', function() {
        expect(utils.parseRoute('/rt/ticket/1529')).toEqual({ view: 'rt', kind: 'ticket', id: '1529' });
    });

    it('should reject empty, malformed and odd views', function() {
        expect(utils.parseRoute('')).toBe(null);
        expect(utils.parseRoute('#')).toBe(null);
        expect(utils.parseRoute('#todos/item/%E0%A4%A')).toBe(null);
        expect(utils.parseRoute('#<script>')).toBe(null);
    });

    it('should format and round-trip', function() {
        expect(utils.formatRoute('todos')).toBe('#todos');
        expect(utils.formatRoute('todos', 'list', '')).toBe('#todos/list');
        var hash = utils.formatRoute('discussions', 'person', 'Jane Doe/Ops');
        expect(hash).toBe('#discussions/person/Jane%20Doe%2FOps');
        expect(utils.parseRoute(hash).id).toBe('Jane Doe/Ops');
    });
});

describe('buildRTConfigPayload', function() {
    var base = { baseUrl: 'https://rt', publicUrl: 'https://rt', query: 'q' };
    function form(extra) {
        var f = {};
        for (var k in base) f[k] = base[k];
        for (var j in extra) f[j] = extra[j];
        return f;
    }

    it('should send user and a newly typed password', function() {
        var r = utils.buildRTConfigPayload(form({ method: 'basic', user: 'scott', pass: 'pw', token: '' }), {});
        expect(r.payload.basic_user).toBe('scott');
        expect(r.payload.basic_pass).toBe('pw');
        expect(r.payload.rest_token).toBe(undefined);
    });

    it('should keep a saved password when the input is blank', function() {
        var r = utils.buildRTConfigPayload(form({ method: 'basic', user: 'scott', pass: '', token: '' }), { has_basic_pass: true });
        expect(r.error).toBe(undefined);
        expect('basic_pass' in r.payload).toBe(false);
    });

    it('should refuse basic auth with no password typed or saved', function() {
        expect(utils.buildRTConfigPayload(form({ method: 'basic', user: 'scott', pass: '' }), {}).error).toBe('Enter your RT username and password.');
    });

    it('should refuse basic auth with no username', function() {
        expect(utils.buildRTConfigPayload(form({ method: 'basic', user: '', pass: 'pw' }), {}).error).toBe('Enter your RT username and password.');
    });

    it('should clear the username and send a typed token for token auth', function() {
        var r = utils.buildRTConfigPayload(form({ method: 'token', user: 'scott', pass: 'pw', token: 'tok' }), { has_basic_pass: true });
        expect(r.payload.basic_user).toBe('');
        expect(r.payload.rest_token).toBe('tok');
        expect('basic_pass' in r.payload).toBe(false);
    });

    it('should keep a saved token when the input is blank', function() {
        var r = utils.buildRTConfigPayload(form({ method: 'token', user: '', token: '' }), { has_rest_token: true });
        expect(r.payload.basic_user).toBe('');
        expect('rest_token' in r.payload).toBe(false);
    });

    it('should refuse token auth with no token typed or saved', function() {
        expect(utils.buildRTConfigPayload(form({ method: 'token', token: '' }), {}).error).toBe('Paste an RT REST token.');
    });
});

// Test runner: executes every registered suite and renders pass/fail output.

function runAllTests() {
    // Tests were already run during script load (describe/it calls execute immediately)
    // Just display the results that were collected
    displayResults();
}

function displayResults() {
    var container = document.getElementById('test-results');
    var loading = document.getElementById('loading');
    var summaryDiv = document.getElementById('summary');

    loading.style.display = 'none';
    container.style.display = 'block';
    summaryDiv.style.display = 'block';

    // Group by suite
    var suites = {};
    testResults.forEach(function(result) {
        if (!suites[result.suite]) {
            suites[result.suite] = [];
        }
        suites[result.suite].push(result);
    });

    // Render suites
    var html = '';
    Object.keys(suites).forEach(function(suiteName) {
        html += '<div class="test-suite">';
        html += '<h2>' + escapeHtml(suiteName) + '</h2>';

        suites[suiteName].forEach(function(test) {
            var statusClass = test.pass ? 'pass' : 'fail';
            var statusText = test.pass ? 'PASS' : 'FAIL';

            html += '<div class="test ' + statusClass + '">';
            html += '<span class="test-name">' + escapeHtml(test.name) + '</span>';
            html += '<span class="test-status ' + statusClass + '">' + statusText + '</span>';
            html += '</div>';

            if (test.error) {
                html += '<div class="error-message">' + escapeHtml(test.error) + '</div>';
            }
        });

        html += '</div>';
    });

    container.innerHTML = html;

    // Summary
    var passed = testResults.filter(function(t) { return t.pass; }).length;
    var failed = testResults.filter(function(t) { return !t.pass; }).length;
    var total = testResults.length;

    summaryDiv.className = 'summary ' + (failed === 0 ? 'all-pass' : 'has-failures');
    summaryDiv.innerHTML =
        '<span class="summary-count pass">' + passed + ' passed</span> / ' +
        '<span class="summary-count fail">' + failed + ' failed</span> / ' +
        total + ' total';

    // Set exit code for CI (via data attribute)
    document.body.setAttribute('data-test-exit-code', failed === 0 ? '0' : '1');
    document.body.setAttribute('data-test-passed', passed);
    document.body.setAttribute('data-test-failed', failed);

    // Console output for CI
    console.log('Test Results: ' + passed + ' passed, ' + failed + ' failed');
    if (failed > 0) {
        testResults.filter(function(t) { return !t.pass; }).forEach(function(t) {
            console.error('FAIL: ' + t.suite + ' - ' + t.name + ': ' + t.error);
        });
    }
}

function escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
