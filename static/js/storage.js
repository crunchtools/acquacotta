/**
 * Acquacotta Storage Layer - IndexedDB Implementation
 *
 * Provides a unified interface for data storage using IndexedDB:
 * - Demo mode: Browser IndexedDB only
 * - Logged in: Browser IndexedDB + sync to/from Google Sheets
 *
 * The server is stateless - it only proxies API calls to Google Sheets.
 * All user data lives in the browser's IndexedDB and optionally in their Google Sheets.
 *
 * Credit: kirkjerk (original idea for browser-side storage)
 */

(function(global) {
    'use strict';

    // IndexedDB configuration
    const DB_NAME = 'acquacotta';
    const DB_VERSION = 2;  // Bumped for auth store

    // Object store names
    const STORES = {
        POMODOROS: 'pomodoros',
        SETTINGS: 'settings',
        SYNC_QUEUE: 'sync_queue',
        SYNC_STATUS: 'sync_status',
        AUTH: 'auth'
    };

    // Default settings (mirrors backend defaults)
    const DEFAULT_SETTINGS = {
        timer_preset_1: 5,
        timer_preset_2: 10,
        timer_preset_3: 15,
        timer_preset_4: 25,
        short_break_minutes: 5,
        long_break_minutes: 15,
        pomodoros_until_long_break: 4,
        always_use_short_break: false,
        sound_enabled: true,
        notifications_enabled: true,
        pomodoro_types: [
            'Content',
            'Customer/Partner/Community',
            'Learn/Train',
            'Product',
            'PTO',
            'Queued',
            'Social Media',
            'Team',
            'Travel',
            'Unqueued'
        ],
        auto_start_after_break: false,
        tick_sound_during_breaks: false,
        bell_at_pomodoro_end: true,
        bell_at_break_end: true,
        show_notes_field: false,
        working_hours_start: '08:00',
        working_hours_end: '17:00',
        clock_format: 'auto',
        period_labels: 'auto',
        daily_minutes_goal: 300
    };

    // Sync configuration
    const SYNC_RETRY_DELAYS = [1000, 2000, 5000, 10000, 30000]; // Exponential backoff
    const MAX_SYNC_RETRIES = 5;

    // Storage state
    let db = null;
    let authStatus = null;
    let storedCredentials = null;  // OAuth credentials from IndexedDB (ephemeral)
    let cachedSpreadsheetId = null;  // Spreadsheet ID from SETTINGS (persistent)
    let isOnline = navigator.onLine;
    let syncInProgress = false;
    let syncLockPromise = null;  // Promise-based lock to prevent race conditions
    let pendingSyncCount = 0;
    let lastSyncError = null;

    /**
     * Generate a UUID v4
     */
    function generateUUID() {
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
            const r = Math.random() * 16 | 0;
            const v = c === 'x' ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    }

    /**
     * Open IndexedDB database
     */
    function openDatabase() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);

            request.onerror = () => {
                console.error('IndexedDB error:', request.error);
                reject(request.error);
            };

            request.onsuccess = () => {
                db = request.result;
                resolve(db);
            };

            request.onupgradeneeded = (event) => {
                const database = event.target.result;

                // Pomodoros store
                if (!database.objectStoreNames.contains(STORES.POMODOROS)) {
                    const pomodorosStore = database.createObjectStore(STORES.POMODOROS, { keyPath: 'id' });
                    pomodorosStore.createIndex('start_time', 'start_time', { unique: false });
                    pomodorosStore.createIndex('type', 'type', { unique: false });
                    pomodorosStore.createIndex('synced', 'synced', { unique: false });
                }

                // Settings store
                if (!database.objectStoreNames.contains(STORES.SETTINGS)) {
                    database.createObjectStore(STORES.SETTINGS, { keyPath: 'key' });
                }

                // Sync queue store
                if (!database.objectStoreNames.contains(STORES.SYNC_QUEUE)) {
                    const syncStore = database.createObjectStore(STORES.SYNC_QUEUE, { keyPath: 'id', autoIncrement: true });
                    syncStore.createIndex('created_at', 'created_at', { unique: false });
                }

                // Sync status store
                if (!database.objectStoreNames.contains(STORES.SYNC_STATUS)) {
                    database.createObjectStore(STORES.SYNC_STATUS, { keyPath: 'key' });
                }

                // Auth store (for OAuth credentials - keeps server stateless)
                if (!database.objectStoreNames.contains(STORES.AUTH)) {
                    database.createObjectStore(STORES.AUTH, { keyPath: 'key' });
                }
            };
        });
    }

    /**
     * Generic IndexedDB transaction helper
     */
    function dbTransaction(storeName, mode, callback) {
        return new Promise((resolve, reject) => {
            if (!db) {
                reject(new Error('Database not initialized'));
                return;
            }
            const transaction = db.transaction(storeName, mode);
            const store = transaction.objectStore(storeName);

            try {
                const result = callback(store);
                if (result && result.onsuccess !== undefined) {
                    result.onsuccess = () => resolve(result.result);
                    result.onerror = () => reject(result.error);
                } else {
                    transaction.oncomplete = () => resolve(result);
                    transaction.onerror = () => reject(transaction.error);
                }
            } catch (e) {
                reject(e);
            }
        });
    }

    /**
     * Get all records from a store
     */
    function getAllFromStore(storeName) {
        return dbTransaction(storeName, 'readonly', (store) => store.getAll());
    }

    /**
     * Get a single record by key
     */
    function getFromStore(storeName, key) {
        return dbTransaction(storeName, 'readonly', (store) => store.get(key));
    }

    /**
     * Put a record into a store
     */
    function putInStore(storeName, record) {
        return dbTransaction(storeName, 'readwrite', (store) => store.put(record));
    }

    /**
     * Delete a record from a store
     */
    function deleteFromStore(storeName, key) {
        return dbTransaction(storeName, 'readwrite', (store) => store.delete(key));
    }

    /**
     * Clear all records from a store
     */
    function clearStore(storeName) {
        return dbTransaction(storeName, 'readwrite', (store) => store.clear());
    }

    /**
     * Load OAuth credentials from IndexedDB
     */
    async function loadCredentials() {
        try {
            const creds = await getFromStore(STORES.AUTH, 'credentials');
            if (creds) {
                storedCredentials = creds;
                return creds;
            }
        } catch (e) {
            console.error('Error loading credentials:', e);
        }
        return null;
    }

    /**
     * Clear OAuth credentials (logout)
     */
    async function clearCredentials() {
        storedCredentials = null;
        try {
            await deleteFromStore(STORES.AUTH, 'credentials');
        } catch (e) {
            console.error('Error clearing credentials:', e);
        }
    }

    /**
     * Make authenticated API call with stored credentials
     * Spreadsheet ID comes from SETTINGS (persistent), credentials from AUTH (ephemeral)
     */
    async function authenticatedFetch(url, options = {}) {
        if (!storedCredentials) {
            throw new Error('Not logged in');
        }
        if (!cachedSpreadsheetId) {
            throw new Error('No spreadsheet configured');
        }

        // Add credentials to request body for POST/PUT, or as header for GET/DELETE
        const method = (options.method || 'GET').toUpperCase();

        if (method === 'GET' || method === 'DELETE') {
            // For GET/DELETE, send credentials as Authorization header (base64 encoded JSON)
            options.headers = options.headers || {};
            options.headers['X-Credentials'] = btoa(JSON.stringify({
                token: storedCredentials.token,
                refresh_token: storedCredentials.refresh_token,
                token_uri: storedCredentials.token_uri,
                client_id: storedCredentials.client_id,
                client_secret: storedCredentials.client_secret,
                scopes: storedCredentials.scopes,
                spreadsheet_id: cachedSpreadsheetId
            }));
        } else {
            // For POST/PUT, merge credentials into body
            options.headers = options.headers || {};
            options.headers['Content-Type'] = 'application/json';
            const body = options.body ? JSON.parse(options.body) : {};
            body._credentials = {
                token: storedCredentials.token,
                refresh_token: storedCredentials.refresh_token,
                token_uri: storedCredentials.token_uri,
                client_id: storedCredentials.client_id,
                client_secret: storedCredentials.client_secret,
                scopes: storedCredentials.scopes,
                spreadsheet_id: cachedSpreadsheetId
            };
            options.body = JSON.stringify(body);
        }

        return fetch(url, options);
    }

    /**
     * Add to sync queue (with duplicate prevention)
     */
    async function addToSyncQueue(operation, store, recordId, data = null) {
        // First, remove any existing queue items for this record to prevent duplicates
        const existingQueue = await getAllFromStore(STORES.SYNC_QUEUE);
        for (const item of existingQueue) {
            if (item.store === store && item.record_id === recordId) {
                await deleteFromStore(STORES.SYNC_QUEUE, item.id);
            }
        }

        const queueItem = {
            operation: operation,  // 'create', 'update', 'delete'
            store: store,
            record_id: recordId,
            data: data,
            created_at: new Date().toISOString(),
            retries: 0
        };
        await putInStore(STORES.SYNC_QUEUE, queueItem);
        await updatePendingCount();
    }

    /**
     * Update pending sync count
     */
    async function updatePendingCount() {
        const queue = await getAllFromStore(STORES.SYNC_QUEUE);
        pendingSyncCount = queue.length;
        dispatchSyncStatusEvent();
    }

    /**
     * Dispatch sync status event for UI updates
     */
    function dispatchSyncStatusEvent() {
        window.dispatchEvent(new CustomEvent('acquacotta-sync-status', {
            detail: {
                syncing: syncInProgress,
                pending: pendingSyncCount,
                online: isOnline,
                error: lastSyncError,
                loggedIn: authStatus && authStatus.logged_in
            }
        }));
    }

    /**
     * Filter pomodoros by date range
     */
    function filterByDateRange(pomodoros, startDate, endDate) {
        return pomodoros.filter(p => {
            if (startDate && p.start_time < startDate) return false;
            if (endDate && p.start_time > endDate) return false;
            return true;
        });
    }

    /**
     * Calculate report statistics
     */
    function calculateReportStats(pomodoros, dates) {
        const totalMinutes = pomodoros.reduce((sum, p) => sum + p.duration_minutes, 0);
        const totalCount = pomodoros.length;

        // Group by type
        const byType = {};
        pomodoros.forEach(p => {
            byType[p.type] = (byType[p.type] || 0) + p.duration_minutes;
        });

        // Daily totals
        const dailyTotals = dates.map(d => {
            const dayStr = d.toISOString().split('T')[0];
            const dayPomodoros = pomodoros.filter(p => p.start_time.startsWith(dayStr));
            return {
                date: dayStr,
                minutes: dayPomodoros.reduce((sum, p) => sum + p.duration_minutes, 0),
                count: dayPomodoros.length
            };
        });

        return {
            total_minutes: totalMinutes,
            total_pomodoros: totalCount,
            by_type: byType,
            daily_totals: dailyTotals
        };
    }

    /**
     * Parse ISO date range and build dates list
     */
    function parseDateRange(startIso, endIso) {
        const startDt = new Date(startIso);
        const endDt = new Date(endIso);

        const dates = [];
        const d = new Date(startDt);
        d.setHours(0, 0, 0, 0);
        const endNaive = new Date(endDt);
        endNaive.setHours(0, 0, 0, 0);

        while (d < endNaive) {
            dates.push(new Date(d));
            d.setDate(d.getDate() + 1);
        }

        if (dates.length === 0) {
            dates.push(new Date(startDt));
        }

        return dates;
    }

    /**
     * Calculate period date range
     */
    function calculatePeriodDateRange(period, dateStr) {
        const refDate = new Date(dateStr + 'T00:00:00');
        let start, end, dates;

        if (period === 'day') {
            start = new Date(refDate);
            start.setHours(0, 0, 0, 0);
            end = new Date(start);
            end.setDate(end.getDate() + 1);
            dates = [new Date(start)];
        } else if (period === 'week') {
            start = new Date(refDate);
            start.setDate(refDate.getDate() - refDate.getDay());
            start.setHours(0, 0, 0, 0);
            end = new Date(start);
            end.setDate(start.getDate() + 7);
            dates = [];
            for (let i = 0; i < 7; i++) {
                const d = new Date(start);
                d.setDate(start.getDate() + i);
                dates.push(d);
            }
        } else if (period === 'month') {
            start = new Date(refDate.getFullYear(), refDate.getMonth(), 1);
            if (refDate.getMonth() === 11) {
                end = new Date(refDate.getFullYear() + 1, 0, 1);
            } else {
                end = new Date(refDate.getFullYear(), refDate.getMonth() + 1, 1);
            }
            dates = [];
            const d = new Date(start);
            while (d < end) {
                dates.push(new Date(d));
                d.setDate(d.getDate() + 1);
            }
        } else {
            return null;
        }

        return { dates, start, end };
    }

    /**
     * Sync a single operation to Google Sheets
     */
    async function syncOperationToSheets(queueItem) {
        const { operation, store, record_id, data } = queueItem;

        if (store !== 'pomodoros' && store !== 'settings') {
            return true; // Unknown store, skip
        }

        try {
            if (store === 'pomodoros') {
                if (operation === 'create') {
                    const res = await authenticatedFetch('/api/sheets/pomodoros', {
                        method: 'POST',
                        body: JSON.stringify(data)
                    });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                } else if (operation === 'update') {
                    const res = await authenticatedFetch(`/api/sheets/pomodoros/${record_id}`, {
                        method: 'PUT',
                        body: JSON.stringify(data)
                    });
                    if (!res.ok) throw new Error(`HTTP ${res.status}`);
                } else if (operation === 'delete') {
                    const res = await authenticatedFetch(`/api/sheets/pomodoros/${record_id}`, {
                        method: 'DELETE'
                    });
                    // 404 on delete is OK - record already doesn't exist
                    if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`);
                }
            } else if (store === 'settings') {
                const res = await authenticatedFetch('/api/sheets/settings', {
                    method: 'POST',
                    body: JSON.stringify(data)
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
            }
            return true;
        } catch (e) {
            console.error('Sync operation failed:', e);
            throw e;
        }
    }

    /**
     * Process the sync queue - push local changes to Sheets
     * Uses promise-based locking to prevent race conditions
     */
    async function processSyncQueue() {
        if (!authStatus || !authStatus.logged_in || !isOnline) {
            return;
        }

        // Promise-based lock to prevent concurrent sync operations
        if (syncLockPromise) {
            // Another sync is in progress, wait for it to complete then return
            // (don't start another sync, let the current one handle all items)
            await syncLockPromise;
            return;
        }

        let resolveLock;
        syncLockPromise = new Promise(resolve => { resolveLock = resolve; });

        syncInProgress = true;
        lastSyncError = null;
        dispatchSyncStatusEvent();

        try {
            const queue = await getAllFromStore(STORES.SYNC_QUEUE);

            // Sort by created_at to process in order
            queue.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

            for (const item of queue) {
                try {
                    await syncOperationToSheets(item);

                    // Mark the pomodoro as synced
                    if (item.store === 'pomodoros' && item.operation !== 'delete') {
                        const pomo = await getFromStore(STORES.POMODOROS, item.record_id);
                        if (pomo) {
                            pomo.synced = true;
                            await putInStore(STORES.POMODOROS, pomo);
                        }
                    }

                    // Remove from queue
                    await deleteFromStore(STORES.SYNC_QUEUE, item.id);
                } catch (e) {
                    // Update retry count
                    item.retries = (item.retries || 0) + 1;
                    if (item.retries >= MAX_SYNC_RETRIES) {
                        console.error('Max retries reached for sync item:', item);
                        lastSyncError = `Failed to sync after ${MAX_SYNC_RETRIES} retries`;
                        // Remove failed item after max retries
                        await deleteFromStore(STORES.SYNC_QUEUE, item.id);
                    } else {
                        await putInStore(STORES.SYNC_QUEUE, item);
                    }
                }
            }

            // Update last sync time
            await putInStore(STORES.SYNC_STATUS, {
                key: 'last_push_sync',
                value: new Date().toISOString()
            });

        } catch (e) {
            console.error('Sync queue processing error:', e);
            lastSyncError = e.message;
        } finally {
            syncInProgress = false;
            syncLockPromise = null;
            resolveLock();  // Release the lock
            await updatePendingCount();
        }
    }

    /**
     * Pull data from Google Sheets to IndexedDB
     */
    async function syncFromSheets() {
        if (!authStatus || !authStatus.logged_in || !isOnline) {
            return { success: false, error: 'Not logged in or offline' };
        }

        syncInProgress = true;
        lastSyncError = null;
        dispatchSyncStatusEvent();

        try {
            // Fetch pomodoros from Sheets
            const pomosRes = await authenticatedFetch('/api/sheets/pomodoros');
            if (!pomosRes.ok) throw new Error(`HTTP ${pomosRes.status}`);
            const sheetsPomodoros = await pomosRes.json();

            // Fetch settings from Sheets
            const settingsRes = await authenticatedFetch('/api/sheets/settings');
            if (!settingsRes.ok) throw new Error(`HTTP ${settingsRes.status}`);
            const sheetsSettings = await settingsRes.json();

            // Get local pomodoros to merge
            const localPomodoros = await getAllFromStore(STORES.POMODOROS);
            const localIds = new Set(localPomodoros.map(p => p.id));

            // Add/update pomodoros from Sheets
            let imported = 0;
            for (const pomo of sheetsPomodoros) {
                if (!localIds.has(pomo.id)) {
                    pomo.synced = true;
                    await putInStore(STORES.POMODOROS, pomo);
                    imported++;
                }
            }

            // Update settings from Sheets
            for (const [key, value] of Object.entries(sheetsSettings)) {
                await putInStore(STORES.SETTINGS, { key, value, synced: true });
            }

            // Preserve spreadsheet_id in SETTINGS (it's not in Sheet, it's the ID of the Sheet itself)
            if (cachedSpreadsheetId) {
                await putInStore(STORES.SETTINGS, {
                    key: 'spreadsheet_id',
                    value: cachedSpreadsheetId,
                    synced: true
                });
            }

            // Update last sync time
            await putInStore(STORES.SYNC_STATUS, {
                key: 'last_pull_sync',
                value: new Date().toISOString()
            });

            return { success: true, imported };
        } catch (e) {
            console.error('Sync from Sheets error:', e);
            lastSyncError = e.message;
            return { success: false, error: e.message };
        } finally {
            syncInProgress = false;
            dispatchSyncStatusEvent();
        }
    }

    /**
     * Storage API
     */
    const Storage = {
        /**
         * Initialize storage based on auth status
         * @param {object} status - Auth status from /api/auth/status
         */
        init: async function(status) {
            // Open IndexedDB first
            await openDatabase();

            // Load credentials from AUTH store (ephemeral - OAuth tokens only)
            const creds = await loadCredentials();

            // Load spreadsheet_id from SETTINGS store (persistent)
            const spreadsheetIdSetting = await getFromStore(STORES.SETTINGS, 'spreadsheet_id');
            cachedSpreadsheetId = spreadsheetIdSetting ? spreadsheetIdSetting.value : null;

            // Load spreadsheet_existed from SETTINGS store
            const spreadsheetExistedSetting = await getFromStore(STORES.SETTINGS, 'spreadsheet_existed');
            const spreadsheetExisted = spreadsheetExistedSetting ? spreadsheetExistedSetting.value : false;

            // Build auth status from credentials (AUTH) + spreadsheet_id (SETTINGS)
            if (creds && creds.token && cachedSpreadsheetId) {
                authStatus = {
                    logged_in: true,
                    email: creds.user_email,
                    name: creds.user_name,
                    picture: creds.user_picture,
                    spreadsheet_id: cachedSpreadsheetId,
                    needs_initial_sync: !spreadsheetExisted
                };
            } else {
                authStatus = {
                    logged_in: false,
                    google_configured: status ? status.google_configured : true
                };
            }

            // Set up online/offline listeners
            window.addEventListener('online', () => {
                isOnline = true;
                dispatchSyncStatusEvent();
                // Trigger sync when coming back online
                if (authStatus && authStatus.logged_in) {
                    this.syncToSheets();
                }
            });

            window.addEventListener('offline', () => {
                isOnline = false;
                dispatchSyncStatusEvent();
            });

            // Update pending count
            await updatePendingCount();

            // Handle initial sync based on whether sheet existed
            if (authStatus.logged_in && storedCredentials) {
                if (spreadsheetExisted) {
                    // Existing sheet: bidirectional pomodoro sync + pull settings from Sheet
                    // Only on first load after login (check if we've done this already)
                    const syncStatus = await getFromStore(STORES.SYNC_STATUS, 'initial_sync_done');
                    if (!syncStatus) {
                        // 0. First, deduplicate any existing duplicates in the Sheet
                        try {
                            const dedupeRes = await authenticatedFetch('/api/sheets/deduplicate', {
                                method: 'POST',
                                body: JSON.stringify({})
                            });
                            if (dedupeRes.ok) {
                                const dedupeResult = await dedupeRes.json();
                                if (dedupeResult.removed > 0) {
                                    console.log(`Removed ${dedupeResult.removed} duplicate pomodoros from Sheet`);
                                }
                            }
                        } catch (e) {
                            console.error('Deduplication during init failed:', e);
                        }

                        // 1. Fetch pomodoros from Sheets
                        const pomosRes = await authenticatedFetch('/api/sheets/pomodoros');
                        if (pomosRes.ok) {
                            const sheetsPomodoros = await pomosRes.json();
                            const sheetsIds = new Set(sheetsPomodoros.map(p => p.id));

                            // 2. Get local pomodoros
                            const localPomodoros = await getAllFromStore(STORES.POMODOROS);
                            const localIds = new Set(localPomodoros.map(p => p.id));

                            // 3. Pull pomodoros from Sheets that don't exist locally
                            for (const pomo of sheetsPomodoros) {
                                if (!localIds.has(pomo.id)) {
                                    pomo.synced = true;
                                    await putInStore(STORES.POMODOROS, pomo);
                                }
                            }

                            // 4. Push local pomodoros to Sheets that don't exist there
                            for (const pomo of localPomodoros) {
                                if (!sheetsIds.has(pomo.id)) {
                                    await addToSyncQueue('create', 'pomodoros', pomo.id, pomo);
                                } else {
                                    // Mark as synced since it exists in Sheets
                                    pomo.synced = true;
                                    await putInStore(STORES.POMODOROS, pomo);
                                }
                            }
                        }

                        // 5. Pull settings from Sheets (Sheet is authoritative for settings)
                        const settingsRes = await authenticatedFetch('/api/sheets/settings');
                        if (settingsRes.ok) {
                            const sheetsSettings = await settingsRes.json();
                            // Clear local settings and replace with Sheet settings
                            await clearStore(STORES.SETTINGS);
                            for (const [key, value] of Object.entries(sheetsSettings)) {
                                await putInStore(STORES.SETTINGS, { key, value, synced: true });
                            }
                            // Re-save spreadsheet_id after clearing (it's not in Sheet settings)
                            await putInStore(STORES.SETTINGS, {
                                key: 'spreadsheet_id',
                                value: cachedSpreadsheetId,
                                synced: false  // Mark as unsynced so it gets pushed to Sheet
                            });
                            // Queue the spreadsheet_id to be saved to the Sheet
                            await addToSyncQueue('update', 'settings', 'spreadsheet_id', {
                                spreadsheet_id: cachedSpreadsheetId
                            });
                        }

                        // 6. Process any queued pushes (including spreadsheet_id)
                        await processSyncQueue();

                        await putInStore(STORES.SYNC_STATUS, { key: 'initial_sync_done', value: true });
                    }
                } else {
                    // New sheet: push local data TO Sheets
                    // Check if we've done this already
                    const syncStatus = await getFromStore(STORES.SYNC_STATUS, 'initial_push_done');
                    if (!syncStatus) {
                        // Push any existing local pomodoros and settings to the new sheet
                        const localPomodoros = await getAllFromStore(STORES.POMODOROS);
                        if (localPomodoros.length > 0) {
                            // Queue all local pomodoros for sync
                            for (const pomo of localPomodoros) {
                                if (!pomo.synced) {
                                    await addToSyncQueue('create', 'pomodoros', pomo.id, pomo);
                                }
                            }
                        }
                        // Push local settings
                        const localSettings = await getAllFromStore(STORES.SETTINGS);
                        if (localSettings.length > 0) {
                            const settingsObj = {};
                            for (const s of localSettings) {
                                settingsObj[s.key] = s.value;
                            }
                            await addToSyncQueue('update', 'settings', 'all', settingsObj);
                        }
                        // Process the queue
                        await processSyncQueue();
                        // Mark initial push done and update spreadsheet_existed in SETTINGS
                        await putInStore(STORES.SYNC_STATUS, { key: 'initial_push_done', value: true });
                        await putInStore(STORES.SETTINGS, { key: 'spreadsheet_existed', value: true, synced: true });
                    }
                }
            }
        },

        /**
         * Check if using local-only mode (not logged in)
         * @returns {boolean}
         */
        isLocalMode: function() {
            return !authStatus || !authStatus.logged_in;
        },

        /**
         * Get auth status
         * @returns {object|null}
         */
        getAuthStatus: function() {
            return authStatus;
        },

        /**
         * Check if online
         * @returns {boolean}
         */
        isOnline: function() {
            return isOnline;
        },

        /**
         * Get sync status
         * @returns {object}
         */
        getSyncStatus: function() {
            return {
                syncing: syncInProgress,
                pending: pendingSyncCount,
                online: isOnline,
                error: lastSyncError,
                loggedIn: authStatus && authStatus.logged_in
            };
        },

        /**
         * Get stored spreadsheet ID from settings (for auto-fill on login)
         * @returns {Promise<string|null>}
         */
        getStoredSpreadsheetId: async function() {
            try {
                // Ensure database is open
                if (!db) {
                    await openDatabase();
                }
                const setting = await getFromStore(STORES.SETTINGS, 'spreadsheet_id');
                return setting ? setting.value : null;
            } catch (e) {
                console.error('getStoredSpreadsheetId error:', e);
                return null;
            }
        },

        /**
         * Logout - clear credentials and sync status from IndexedDB
         * Spreadsheet_id in SETTINGS is preserved for re-login convenience
         * @returns {Promise}
         */
        logout: async function() {
            await clearCredentials();
            cachedSpreadsheetId = null;  // Clear cached value (will reload from SETTINGS on next init)
            // Clear sync status so next login will re-sync from Sheet
            await clearStore(STORES.SYNC_STATUS);
            authStatus = { logged_in: false, google_configured: true };
            dispatchSyncStatusEvent();
        },

        /**
         * Update spreadsheet ID in IndexedDB (SETTINGS store only)
         * @param {string} newId - New spreadsheet ID
         * @returns {Promise}
         */
        updateSpreadsheetId: async function(newId) {
            // Update SETTINGS store (persistent)
            await putInStore(STORES.SETTINGS, {
                key: 'spreadsheet_id',
                value: newId,
                synced: false
            });

            // Update cached value for current session
            cachedSpreadsheetId = newId;

            // Queue sync to save spreadsheet_id to Google Sheets Settings
            await addToSyncQueue('update', 'settings', 'spreadsheet_id', {
                spreadsheet_id: newId
            });

            // Process the queue
            await processSyncQueue();
        },

        /**
         * Make authenticated fetch request (includes credentials)
         * @param {string} url - URL to fetch
         * @param {object} options - Fetch options
         * @returns {Promise<Response>}
         */
        authenticatedFetch: authenticatedFetch,

        /**
         * Get count of local pomodoros
         * @returns {Promise<number>}
         */
        getLocalPomodoroCount: async function() {
            const pomodoros = await getAllFromStore(STORES.POMODOROS);
            return pomodoros.length;
        },

        /**
         * Check if there's local data
         * @returns {Promise<boolean>}
         */
        hasLocalData: async function() {
            const pomodoros = await getAllFromStore(STORES.POMODOROS);
            return pomodoros.length > 0;
        },

        /**
         * Fetch pomodoros with optional date filtering
         * @param {string} startDate - Optional start date (ISO string)
         * @param {string} endDate - Optional end date (ISO string)
         * @returns {Promise<Array>}
         */
        getPomodoros: async function(startDate, endDate) {
            let pomodoros = await getAllFromStore(STORES.POMODOROS);

            if (startDate || endDate) {
                pomodoros = filterByDateRange(pomodoros, startDate, endDate);
            }

            // Sort by start_time descending (most recent first)
            pomodoros.sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
            return pomodoros;
        },

        /**
         * Create a new pomodoro (timer completion)
         * @param {object} data - Pomodoro data (name, type, duration_minutes, notes)
         * @returns {Promise<object>}
         */
        createPomodoro: async function(data) {
            const endTime = new Date();
            const startTime = new Date(endTime.getTime() - (data.duration_minutes || 25) * 60 * 1000);

            const pomodoro = {
                id: generateUUID(),
                name: data.name || '',
                type: data.type,
                start_time: startTime.toISOString(),
                end_time: endTime.toISOString(),
                duration_minutes: data.duration_minutes || 25,
                notes: data.notes || null,
                synced: false
            };

            await putInStore(STORES.POMODOROS, pomodoro);

            // Queue for sync if logged in
            if (authStatus && authStatus.logged_in) {
                await addToSyncQueue('create', 'pomodoros', pomodoro.id, pomodoro);
                this.syncToSheets(); // Trigger immediate sync attempt
            }

            return pomodoro;
        },

        /**
         * Create a manual pomodoro with custom times
         * @param {object} data - Pomodoro data with start_time, end_time, duration_minutes
         * @returns {Promise<object>}
         */
        createManualPomodoro: async function(data) {
            const pomodoro = {
                id: data.id || generateUUID(),  // Use provided ID or generate new
                name: data.name || '',
                type: data.type,
                start_time: data.start_time,
                end_time: data.end_time,
                duration_minutes: data.duration_minutes,
                notes: data.notes || null,
                synced: false
            };

            await putInStore(STORES.POMODOROS, pomodoro);

            // Queue for sync if logged in
            if (authStatus && authStatus.logged_in) {
                await addToSyncQueue('create', 'pomodoros', pomodoro.id, pomodoro);
                this.syncToSheets();
            }

            return pomodoro;
        },

        /**
         * Update an existing pomodoro
         * @param {string} id - Pomodoro ID
         * @param {object} data - Updated pomodoro data
         * @returns {Promise<object>}
         */
        updatePomodoro: async function(id, data) {
            const existing = await getFromStore(STORES.POMODOROS, id);
            if (!existing) {
                return { status: 'error', message: 'Pomodoro not found' };
            }

            const updated = {
                ...existing,
                name: data.name,
                type: data.type,
                start_time: data.start_time,
                end_time: data.end_time,
                duration_minutes: data.duration_minutes,
                notes: data.notes || null,
                synced: false
            };

            await putInStore(STORES.POMODOROS, updated);

            // Queue for sync if logged in
            if (authStatus && authStatus.logged_in) {
                await addToSyncQueue('update', 'pomodoros', id, updated);
                this.syncToSheets();
            }

            return { status: 'ok' };
        },

        /**
         * Delete a pomodoro
         * @param {string} id - Pomodoro ID
         * @returns {Promise<object>}
         */
        deletePomodoro: async function(id) {
            await deleteFromStore(STORES.POMODOROS, id);

            // Queue for sync if logged in
            if (authStatus && authStatus.logged_in) {
                await addToSyncQueue('delete', 'pomodoros', id);
                this.syncToSheets();
            }

            return { status: 'ok' };
        },

        /**
         * Get settings
         * @returns {Promise<object>}
         */
        getSettings: async function() {
            const settingsRecords = await getAllFromStore(STORES.SETTINGS);
            const settings = { ...DEFAULT_SETTINGS };

            for (const record of settingsRecords) {
                settings[record.key] = record.value;
            }

            return settings;
        },

        /**
         * Save settings
         * @param {object} settings - Settings to save
         * @returns {Promise<object>}
         */
        saveSettings: async function(settings) {
            const allSettings = {};

            for (const [key, value] of Object.entries(settings)) {
                await putInStore(STORES.SETTINGS, { key, value, synced: false });
                allSettings[key] = value;
            }

            // Queue for sync if logged in
            if (authStatus && authStatus.logged_in) {
                await addToSyncQueue('update', 'settings', 'all', allSettings);
                this.syncToSheets();
            }

            return { status: 'ok' };
        },

        /**
         * Get report for a period
         * @param {string} period - 'day', 'week', or 'month'
         * @param {string} startDate - Start date (ISO string)
         * @param {string} endDate - End date (ISO string)
         * @param {string} dateStr - Reference date string (YYYY-MM-DD)
         * @returns {Promise<object>}
         */
        getReport: async function(period, startDate, endDate, dateStr) {
            let dates, startIso, endIso;

            if (startDate && endDate) {
                dates = parseDateRange(startDate, endDate);
                startIso = startDate;
                endIso = endDate;
            } else {
                const range = calculatePeriodDateRange(period, dateStr || new Date().toISOString().split('T')[0]);
                if (!range) {
                    return { error: 'Invalid period' };
                }
                dates = range.dates;
                startIso = range.start.toISOString();
                endIso = range.end.toISOString();
            }

            const allPomodoros = await getAllFromStore(STORES.POMODOROS);
            const pomodoros = filterByDateRange(allPomodoros, startIso, endIso);
            const stats = calculateReportStats(pomodoros, dates);

            return {
                period: period,
                ...stats
            };
        },

        /**
         * Sync local changes to Google Sheets
         * @returns {Promise}
         */
        syncToSheets: async function() {
            return processSyncQueue();
        },

        /**
         * Sync from Google Sheets to local IndexedDB
         * @returns {Promise<object>}
         */
        syncFromSheets: async function() {
            return syncFromSheets();
        },

        /**
         * Full bidirectional sync
         * @returns {Promise<object>}
         */
        fullSync: async function() {
            // First push local changes
            await processSyncQueue();

            // Then pull from Sheets
            return syncFromSheets();
        },

        /**
         * Remove duplicate pomodoros from Google Sheets
         * @returns {Promise<object>}
         */
        deduplicateSheets: async function() {
            if (!authStatus || !authStatus.logged_in) {
                return { error: 'Not logged in' };
            }
            try {
                const res = await authenticatedFetch('/api/sheets/deduplicate', {
                    method: 'POST',
                    body: JSON.stringify({})
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                return await res.json();
            } catch (e) {
                console.error('Deduplication error:', e);
                return { error: e.message };
            }
        },

        /**
         * Export data as CSV
         * @returns {Promise<string>} - CSV content
         */
        exportCSV: async function() {
            const pomodoros = await getAllFromStore(STORES.POMODOROS);
            // Sort by start_time descending
            pomodoros.sort((a, b) => new Date(b.start_time) - new Date(a.start_time));

            const lines = ['id,name,type,start_time,end_time,duration_minutes,notes'];
            pomodoros.forEach(p => {
                const name = (p.name || '').replace(/"/g, '""');
                const notes = (p.notes || '').replace(/"/g, '""');
                lines.push(
                    `"${p.id}","${name}","${p.type}","${p.start_time}","${p.end_time}",${p.duration_minutes},"${notes}"`
                );
            });
            return lines.join('\n');
        },

        /**
         * Download data as CSV file
         */
        downloadCSV: async function() {
            const csv = await this.exportCSV();
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'acquacotta_pomodoros.csv';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        },

        /**
         * Clear all local data
         * @returns {Promise<boolean>}
         */
        clearAllData: async function() {
            try {
                await clearStore(STORES.POMODOROS);
                await clearStore(STORES.SETTINGS);
                await clearStore(STORES.SYNC_QUEUE);
                await clearStore(STORES.SYNC_STATUS);
                await updatePendingCount();
                return true;
            } catch (e) {
                console.error('Error clearing data:', e);
                return false;
            }
        },

        /**
         * Get local pomodoros for migration (backwards compatibility)
         * @returns {Promise<Array>}
         */
        getLocalPomodorosForMigration: async function() {
            return getAllFromStore(STORES.POMODOROS);
        },

        // Legacy method aliases for backwards compatibility
        exportLocalCSV: function() {
            return this.exportCSV();
        },

        downloadLocalCSV: function() {
            return this.downloadCSV();
        },

        clearLocalData: function() {
            return this.clearAllData();
        },

        /**
         * Migrate data from old localStorage format to IndexedDB
         * This handles backwards compatibility with pre-IndexedDB versions
         * @returns {Promise<object>}
         */
        migrateFromLocalStorage: async function() {
            try {
                // Check for old localStorage data
                const oldPomodoros = localStorage.getItem('acquacotta_pomodoros');
                const oldSettings = localStorage.getItem('acquacotta_settings');

                if (!oldPomodoros && !oldSettings) {
                    return { migrated: 0 };
                }

                let migrated = 0;

                // Migrate pomodoros
                if (oldPomodoros) {
                    const pomodoros = JSON.parse(oldPomodoros);
                    for (const pomo of pomodoros) {
                        // Check if already exists in IndexedDB
                        const existing = await getFromStore(STORES.POMODOROS, pomo.id);
                        if (!existing) {
                            pomo.synced = false;
                            await putInStore(STORES.POMODOROS, pomo);
                            migrated++;
                        }
                    }
                    // Clear old localStorage after successful migration
                    localStorage.removeItem('acquacotta_pomodoros');
                }

                // Migrate settings
                if (oldSettings) {
                    const settings = JSON.parse(oldSettings);
                    for (const [key, value] of Object.entries(settings)) {
                        await putInStore(STORES.SETTINGS, { key, value, synced: false });
                    }
                    localStorage.removeItem('acquacotta_settings');
                }

                return { migrated };
            } catch (e) {
                console.error('Error migrating from localStorage:', e);
                return { migrated: 0, error: e.message };
            }
        },

        /**
         * Migrate local IndexedDB data to Google Sheets (on login)
         * Uses batch upload for efficiency
         * @returns {Promise<object>}
         */
        migrateLocalToBackend: async function() {
            if (!authStatus || !authStatus.logged_in) {
                return { migrated: 0, skipped: 0, error: 'Not logged in' };
            }

            const pomodoros = await getAllFromStore(STORES.POMODOROS);
            if (pomodoros.length === 0) {
                return { migrated: 0, skipped: 0 };
            }

            try {
                // Use batch endpoint - server handles duplicate checking
                const res = await authenticatedFetch('/api/sheets/pomodoros/batch', {
                    method: 'POST',
                    body: JSON.stringify({ pomodoros: pomodoros })
                });

                if (res.ok) {
                    const result = await res.json();
                    // Mark all as synced
                    for (const pomo of pomodoros) {
                        pomo.synced = true;
                        await putInStore(STORES.POMODOROS, pomo);
                    }
                    return { migrated: result.count || 0, skipped: pomodoros.length - (result.count || 0) };
                } else {
                    return { migrated: 0, skipped: 0, error: `HTTP ${res.status}` };
                }
            } catch (e) {
                console.error('Error migrating pomodoros:', e);
                return { migrated: 0, skipped: 0, error: e.message };
            }
        },

        /**
         * Migrate local settings to backend
         * @param {boolean} replaceAll - If true, replace all settings in Sheet (used by Overwrite Google)
         * @returns {Promise<object>}
         */
        migrateLocalSettingsToBackend: async function(replaceAll = false) {
            if (!authStatus || !authStatus.logged_in) {
                return { migrated: false, error: 'Not logged in' };
            }

            const settingsRecords = await getAllFromStore(STORES.SETTINGS);
            if (settingsRecords.length === 0) {
                return { migrated: false };
            }

            const settings = {};
            for (const record of settingsRecords) {
                settings[record.key] = record.value;
            }

            // Add replace_all flag if requested
            if (replaceAll) {
                settings._replace_all = true;
            }

            try {
                const res = await authenticatedFetch('/api/sheets/settings', {
                    method: 'POST',
                    body: JSON.stringify(settings)
                });

                if (res.ok) {
                    // Mark all settings as synced
                    for (const record of settingsRecords) {
                        record.synced = true;
                        await putInStore(STORES.SETTINGS, record);
                    }
                    return { migrated: true };
                } else {
                    return { migrated: false, error: `HTTP ${res.status}` };
                }
            } catch (e) {
                console.error('Error migrating settings:', e);
                return { migrated: false, error: e.message };
            }
        }
    };

    // Export
    if (typeof window !== 'undefined') {
        window.Storage = Storage;
    }

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = Storage;
    }

})(this);
