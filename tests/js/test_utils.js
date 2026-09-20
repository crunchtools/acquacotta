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
