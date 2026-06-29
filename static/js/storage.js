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
    const DB_VERSION = 3;  // Bumped for todos stores

    // Object store names
    const STORES = {
        POMODOROS: 'pomodoros',
        SETTINGS: 'settings',
        SYNC_QUEUE: 'sync_queue',
        SYNC_STATUS: 'sync_status',
        AUTH: 'auth',
        TODOS: 'todos',
        TODO_LISTS: 'todo_lists'
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

    // Storage location field names — each plugin declares its own in PLUGIN_METADATA.frontend_fields
    const LOCATION_FIELDS = ['spreadsheet_id', 'folder_id'];

    // Storage state
    let db = null;
    let authStatus = null;
    let storedCredentials = null;  // OAuth credentials from IndexedDB (ephemeral)
    let cachedSpreadsheetId = null;  // Legacy alias — kept for backwards compat
    let cachedLocationFields = {};   // All plugin location fields from SETTINGS
    let isOnline = navigator.onLine;
    let syncInProgress = false;
    let cachedActivePlugin = null; // Active storage plugin metadata from /api/plugins
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
        if (db) return Promise.resolve(db);
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

                // Todos store
                if (!database.objectStoreNames.contains(STORES.TODOS)) {
                    const todosStore = database.createObjectStore(STORES.TODOS, { keyPath: 'id' });
                    todosStore.createIndex('list_id', 'list_id', { unique: false });
                    todosStore.createIndex('status', 'status', { unique: false });
                }

                // Todo lists store
                if (!database.objectStoreNames.contains(STORES.TODO_LISTS)) {
                    database.createObjectStore(STORES.TODO_LISTS, { keyPath: 'id' });
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
                const request = callback(store);
                if (request && request.onsuccess !== undefined) {
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                } else {
                    transaction.oncomplete = () => resolve(request);
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
     * Get records from a store index within a key range
     */
    function getRangeFromIndex(storeName, indexName, lower, upper) {
        return dbTransaction(storeName, 'readonly', (store) => {
            const index = store.index(indexName);
            let range = null;
            if (lower && upper) range = IDBKeyRange.bound(lower, upper);
            else if (lower) range = IDBKeyRange.lowerBound(lower);
            else if (upper) range = IDBKeyRange.upperBound(upper);
            return index.getAll(range);
        });
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
    function _buildCredentialsPayload() {
        const payload = {
            token: storedCredentials.token,
            refresh_token: storedCredentials.refresh_token,
            token_uri: storedCredentials.token_uri,
            client_id: storedCredentials.client_id,
            client_secret: storedCredentials.client_secret,
            scopes: storedCredentials.scopes,
            user_email: storedCredentials.user_email,
        };
        // Include all cached location fields (spreadsheet_id, folder_id, etc.)
        Object.assign(payload, cachedLocationFields);
        return payload;
    }

    async function authenticatedFetch(url, options = {}) {
        if (!storedCredentials) {
            throw new Error('Not logged in');
        }
        const hasLocation = Object.values(cachedLocationFields).some(v => v);
        if (!hasLocation) {
            throw new Error('No storage location configured');
        }

        const method = (options.method || 'GET').toUpperCase();

        if (method === 'GET' || method === 'DELETE') {
            options.headers = options.headers || {};
            options.headers['X-Credentials'] = btoa(JSON.stringify(_buildCredentialsPayload()));
        } else {
            options.headers = options.headers || {};
            options.headers['Content-Type'] = 'application/json';
            const body = options.body ? JSON.parse(options.body) : {};
            body._credentials = _buildCredentialsPayload();
            options.body = JSON.stringify(body);
        }

        return fetch(url, options);
    }

    function authenticatedFetchRaw(url, options = {}) {
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

        // Daily totals — group by local date, not UTC date prefix
        const dailyTotals = dates.map(d => {
            const dayStr = d.toLocaleDateString('en-CA');
            const dayPomodoros = pomodoros.filter(p => {
                const localDate = new Date(p.start_time).toLocaleDateString('en-CA');
                return localDate === dayStr;
            });
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

            // Preserve storage location fields (they're not in the backend data)
            for (const [field, value] of Object.entries(cachedLocationFields)) {
                if (value) {
                    await putInStore(STORES.SETTINGS, { key: field, value, synced: true });
                }
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
         * Open IndexedDB without running auth/network initialization.
         * Call this early so IndexedDB reads (settings, pomodoros) work
         * before the full init() completes.
         */
        openDatabase: openDatabase,

        /**
         * Initialize storage based on auth status
         * @param {object} status - Auth status from /api/auth/status
         */
        init: async function(status) {
            // Open IndexedDB first (idempotent if already opened)
            await openDatabase();

            // Load credentials from AUTH store (ephemeral - OAuth tokens only)
            const creds = await loadCredentials();

            // Load all storage location fields from SETTINGS store (persistent)
            cachedLocationFields = {};
            for (const field of LOCATION_FIELDS) {
                const setting = await getFromStore(STORES.SETTINGS, field);
                if (setting && setting.value) {
                    cachedLocationFields[field] = setting.value;
                }
            }
            // Legacy alias for backwards compat
            cachedSpreadsheetId = cachedLocationFields.spreadsheet_id || null;

            // Load storage_existed from SETTINGS store
            const storageExistedSetting = await getFromStore(STORES.SETTINGS, 'storage_existed');
            const storageExisted = storageExistedSetting ? storageExistedSetting.value : false;

            // Fetch active plugin info to know which location fields are required
            try {
                const pluginRes = await fetch('/api/plugins');
                if (pluginRes.ok) {
                    const pluginData = await pluginRes.json();
                    cachedActivePlugin = pluginData.plugins.find(p => p.active && p.plugin_type === 'storage') || null;
                }
            } catch (e) { /* offline — fall back to checking any location field */ }
            const activePlugin = cachedActivePlugin;

            const requiredFields = activePlugin ? (activePlugin.frontend_fields || []) : [];
            const hasRequiredLocation = requiredFields.length === 0 ||
                requiredFields.some(f => cachedLocationFields[f]);
            const hasAnyCreds = creds && creds.token;

            if (hasAnyCreds && hasRequiredLocation) {
                authStatus = {
                    logged_in: true,
                    email: creds.user_email,
                    name: creds.user_name,
                    picture: creds.user_picture,
                    spreadsheet_id: cachedSpreadsheetId,
                    folder_id: cachedLocationFields.folder_id || null,
                    needs_initial_sync: !storageExisted,
                    needs_relogin: false
                };
            } else if (hasAnyCreds && !hasRequiredLocation) {
                // Plugin changed — auto-provision the new backend with existing credentials.
                // Clear stale sync queue (it was for the old plugin).
                await clearStore(STORES.SYNC_QUEUE);

                let provisioned = false;
                try {
                    const provRes = await authenticatedFetchRaw('/api/storage/provision', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            _credentials: {
                                token: creds.token,
                                refresh_token: creds.refresh_token,
                                token_uri: creds.token_uri,
                                client_id: creds.client_id,
                                client_secret: creds.client_secret,
                                scopes: creds.scopes,
                                user_email: creds.user_email,
                            }
                        })
                    });
                    if (provRes.ok) {
                        const provData = await provRes.json();
                        for (const field of requiredFields) {
                            if (provData[field]) {
                                cachedLocationFields[field] = provData[field];
                                await putInStore(STORES.SETTINGS, { key: field, value: provData[field], synced: true });
                            }
                        }
                        cachedSpreadsheetId = cachedLocationFields.spreadsheet_id || null;
                        await putInStore(STORES.SETTINGS, { key: 'storage_existed', value: provData.existed, synced: true });
                        provisioned = true;
                    }
                } catch (e) {
                    console.error('Auto-provision failed:', e);
                }

                if (provisioned) {
                    authStatus = {
                        logged_in: true,
                        email: creds.user_email,
                        name: creds.user_name,
                        picture: creds.user_picture,
                        spreadsheet_id: cachedSpreadsheetId,
                        folder_id: cachedLocationFields.folder_id || null,
                        needs_initial_sync: true,
                        needs_relogin: false
                    };
                } else {
                    authStatus = {
                        logged_in: false,
                        needs_relogin: true,
                        google_configured: true,
                        relogin_reason: activePlugin
                            ? `Could not set up ${activePlugin.name}. Please sign in again.`
                            : 'Please sign in again'
                    };
                }
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

            // Bidirectional sync on every page load when logged in
            if (authStatus.logged_in && storedCredentials) {
                try {
                    // Clear any stale sync queue — the batch push below handles everything
                    await clearStore(STORES.SYNC_QUEUE);

                    // 1. Fetch pomodoros from backend
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

                        // 4. Push local pomodoros that don't exist on the backend
                        const toPush = [];
                        for (const pomo of localPomodoros) {
                            if (!sheetsIds.has(pomo.id)) {
                                toPush.push(pomo);
                            } else {
                                pomo.synced = true;
                                await putInStore(STORES.POMODOROS, pomo);
                            }
                        }
                        if (toPush.length > 0) {
                            const batchRes = await authenticatedFetch('/api/sheets/pomodoros/batch', {
                                method: 'POST',
                                body: JSON.stringify({ pomodoros: toPush })
                            });
                            if (batchRes.ok) {
                                for (const pomo of toPush) {
                                    pomo.synced = true;
                                    await putInStore(STORES.POMODOROS, pomo);
                                }
                            }
                        }

                        // Store the authoritative count after merge (avoids stale Drive reads)
                        const allLocal = await getAllFromStore(STORES.POMODOROS);
                        authStatus.synced_count = allLocal.length;
                    }

                    // Pull settings from Sheets on first load only (Sheet is authoritative)
                    const settingsSyncDone = await getFromStore(STORES.SYNC_STATUS, 'initial_sync_done');
                    if (!settingsSyncDone) {
                        const settingsRes = await authenticatedFetch('/api/sheets/settings');
                        if (settingsRes.ok) {
                            const sheetsSettings = await settingsRes.json();
                            if (Object.keys(sheetsSettings).length > 0) {
                                await clearStore(STORES.SETTINGS);
                                for (const [key, value] of Object.entries(sheetsSettings)) {
                                    await putInStore(STORES.SETTINGS, { key, value, synced: true });
                                }
                                // Re-save location fields after clearing
                                for (const [field, value] of Object.entries(cachedLocationFields)) {
                                    if (value) {
                                        await putInStore(STORES.SETTINGS, { key: field, value, synced: true });
                                    }
                                }
                            }
                        }
                        await putInStore(STORES.SYNC_STATUS, { key: 'initial_sync_done', value: true });
                    }

                    // Mark storage as existing
                    await putInStore(STORES.SETTINGS, { key: 'storage_existed', value: true, synced: true });
                } catch (e) {
                    console.error('Bidirectional sync during init failed:', e);
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

        getActivePlugin: function() {
            return cachedActivePlugin;
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
         * Update a storage location field in IndexedDB (SETTINGS store only)
         * @param {string} field - Field name (e.g., 'spreadsheet_id', 'folder_id')
         * @param {string} newId - New location ID
         * @returns {Promise}
         */
        updateLocationField: async function(field, newId) {
            await putInStore(STORES.SETTINGS, { key: field, value: newId, synced: false });
            cachedLocationFields[field] = newId;
            if (field === 'spreadsheet_id') cachedSpreadsheetId = newId;
        },

        /**
         * Update spreadsheet ID in IndexedDB (legacy compat wrapper)
         * @param {string} newId - New spreadsheet ID
         * @returns {Promise}
         */
        updateSpreadsheetId: async function(newId) {
            await this.updateLocationField('spreadsheet_id', newId);
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
            let pomodoros;
            if (startDate || endDate) {
                pomodoros = await getRangeFromIndex(STORES.POMODOROS, 'start_time', startDate || null, endDate || null);
            } else {
                pomodoros = await getAllFromStore(STORES.POMODOROS);
            }

            // Sort by start_time descending (most recent first)
            pomodoros.sort((a, b) => new Date(b.start_time) - new Date(a.start_time));
            return pomodoros;
        },

        /**
         * Fetch a page of pomodoros using cursor-based pagination on the start_time index.
         * Returns newest first. Use beforeTimestamp to fetch the next page.
         * @param {number} limit - Number of records to fetch
         * @param {string} [beforeTimestamp] - ISO timestamp to start before (exclusive)
         * @returns {Promise<{pomodoros: Array, hasMore: boolean}>}
         */
        getPomodorosPage: function(limit, beforeTimestamp) {
            return new Promise((resolve, reject) => {
                if (!db) { reject(new Error('Database not initialized')); return; }
                const tx = db.transaction(STORES.POMODOROS, 'readonly');
                const store = tx.objectStore(STORES.POMODOROS);
                const index = store.index('start_time');

                const range = beforeTimestamp
                    ? IDBKeyRange.upperBound(beforeTimestamp, true)
                    : null;
                const request = index.openCursor(range, 'prev');
                const results = [];

                request.onsuccess = (event) => {
                    const cursor = event.target.result;
                    if (cursor && results.length < limit) {
                        results.push(cursor.value);
                        cursor.continue();
                    } else {
                        resolve({ pomodoros: results, hasMore: !!cursor });
                    }
                };
                request.onerror = () => reject(request.error);
            });
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
                linked_todo_id: data.linked_todo_id || null,
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
                linked_todo_id: data.linked_todo_id || null,
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

        saveSetting: async function(key, value) {
            await putInStore(STORES.SETTINGS, { key, value, synced: false });
            if (authStatus && authStatus.logged_in) {
                await addToSyncQueue('update', 'settings', 'all', { [key]: value });
                this.syncToSheets();
            }
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
                const range = calculatePeriodDateRange(period, dateStr || new Date().toLocaleDateString('en-CA'));
                if (!range) {
                    return { error: 'Invalid period' };
                }
                dates = range.dates;
                startIso = range.start.toISOString();
                endIso = range.end.toISOString();
            }

            const pomodoros = await getRangeFromIndex(STORES.POMODOROS, 'start_time', startIso, endIso);
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
         * Full bidirectional sync — pull from Sheets, push to Sheets
         * @returns {Promise<object>} - { uploaded: number, downloaded: number }
         */
        fullSync: async function() {
            if (!authStatus || !authStatus.logged_in) {
                return { uploaded: 0, downloaded: 0 };
            }
            let uploaded = 0, downloaded = 0;

            // 1. Fetch pomodoros from Sheets
            const pomosRes = await authenticatedFetch('/api/sheets/pomodoros');
            if (pomosRes.ok) {
                const sheetsPomodoros = await pomosRes.json();
                const sheetsIds = new Set(sheetsPomodoros.map(p => p.id));

                const localPomodoros = await getAllFromStore(STORES.POMODOROS);
                const localIds = new Set(localPomodoros.map(p => p.id));

                // Pull from Sheets
                for (const pomo of sheetsPomodoros) {
                    if (!localIds.has(pomo.id)) {
                        pomo.synced = true;
                        await putInStore(STORES.POMODOROS, pomo);
                        downloaded++;
                    }
                }

                // Push to Sheets
                for (const pomo of localPomodoros) {
                    if (!sheetsIds.has(pomo.id)) {
                        await addToSyncQueue('create', 'pomodoros', pomo.id, pomo);
                        uploaded++;
                    } else if (!pomo.synced) {
                        pomo.synced = true;
                        await putInStore(STORES.POMODOROS, pomo);
                    }
                }
            }

            // 2. Process sync queue
            await processSyncQueue();

            return { uploaded, downloaded };
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
                    const batchResponse = await res.json();
                    // Mark all as synced
                    for (const pomo of pomodoros) {
                        pomo.synced = true;
                        await putInStore(STORES.POMODOROS, pomo);
                    }
                    return { migrated: batchResponse.count || 0, skipped: pomodoros.length - (batchResponse.count || 0) };
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
        },

        // ── Todos CRUD ──────────────────────────────────────────────

        getTodos: async function() {
            const todos = await getAllFromStore(STORES.TODOS);
            return todos.sort((a, b) => {
                if (a.status !== b.status) return a.status === 'pending' ? -1 : 1;
                return (a.sort_order ?? 999999) - (b.sort_order ?? 999999);
            });
        },

        createTodo: async function(data) {
            const existing = await getAllFromStore(STORES.TODOS);
            const maxOrder = existing.reduce((m, t) => Math.max(m, t.sort_order ?? 0), 0);
            const todo = {
                id: generateUUID(),
                title: data.title || '',
                notes: data.notes || '',
                status: 'pending',
                priority: data.priority || 'none',
                due_date: data.due_date || null,
                list_id: data.list_id || null,
                sort_order: maxOrder + 1,
                created_at: new Date().toISOString(),
                completed_at: null
            };
            await putInStore(STORES.TODOS, todo);
            this._debounceTodoSync();
            return todo;
        },

        updateTodo: async function(id, data) {
            const existing = await getFromStore(STORES.TODOS, id);
            if (!existing) return null;
            const updated = { ...existing, ...data };
            await putInStore(STORES.TODOS, updated);
            this._debounceTodoSync();
            return updated;
        },

        completeTodo: async function(id) {
            const existing = await getFromStore(STORES.TODOS, id);
            if (!existing) return null;
            existing.status = 'completed';
            existing.completed_at = new Date().toISOString();
            await putInStore(STORES.TODOS, existing);
            this._debounceTodoSync();
            return existing;
        },

        uncompleteTodo: async function(id) {
            const existing = await getFromStore(STORES.TODOS, id);
            if (!existing) return null;
            existing.status = 'pending';
            existing.completed_at = null;
            await putInStore(STORES.TODOS, existing);
            this._debounceTodoSync();
            return existing;
        },

        deleteTodo: async function(id) {
            await deleteFromStore(STORES.TODOS, id);
            this._debounceTodoSync();
            return { status: 'ok' };
        },

        // ── Todo Lists CRUD ─────────────────────────────────────────

        getTodoLists: async function() {
            const lists = await getAllFromStore(STORES.TODO_LISTS);
            return lists.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
        },

        createTodoList: async function(data) {
            const lists = await getAllFromStore(STORES.TODO_LISTS);
            const list = {
                id: generateUUID(),
                name: data.name || 'New List',
                order: lists.length
            };
            await putInStore(STORES.TODO_LISTS, list);
            this._debounceTodoSync();
            return list;
        },

        updateTodoList: async function(id, data) {
            const existing = await getFromStore(STORES.TODO_LISTS, id);
            if (!existing) return null;
            const updated = { ...existing, ...data };
            await putInStore(STORES.TODO_LISTS, updated);
            this._debounceTodoSync();
            return updated;
        },

        deleteTodoList: async function(id) {
            await deleteFromStore(STORES.TODO_LISTS, id);
            // Orphan todos in this list → set list_id to null
            const todos = await getAllFromStore(STORES.TODOS);
            for (const todo of todos) {
                if (todo.list_id === id) {
                    todo.list_id = null;
                    await putInStore(STORES.TODOS, todo);
                }
            }
            this._debounceTodoSync();
            return { status: 'ok' };
        },

        // ── Todos Sync ──────────────────────────────────────────────

        _todoSyncTimer: null,

        _debounceTodoSync: function() {
            if (this._todoSyncTimer) clearTimeout(this._todoSyncTimer);
            if (!authStatus || !authStatus.logged_in || !isOnline) return;
            this._todoSyncTimer = setTimeout(() => this.syncTodosToCloud(), 2000);
        },

        syncTodosToCloud: async function() {
            if (!authStatus || !authStatus.logged_in || !isOnline) return;
            try {
                const todos = await getAllFromStore(STORES.TODOS);
                const lists = await getAllFromStore(STORES.TODO_LISTS);
                await authenticatedFetch('/api/todos/sync', {
                    method: 'POST',
                    body: JSON.stringify({ todos, lists })
                });
            } catch (e) {
                console.error('Todo sync to cloud failed:', e);
            }
        },

        loadTodosFromCloud: async function() {
            if (!authStatus || !authStatus.logged_in || !isOnline) return false;
            try {
                const res = await authenticatedFetch('/api/todos/sync');
                if (!res.ok) return false;
                const data = await res.json();
                if (data.todos) {
                    for (const todo of data.todos) {
                        await putInStore(STORES.TODOS, todo);
                    }
                }
                if (data.lists) {
                    for (const list of data.lists) {
                        await putInStore(STORES.TODO_LISTS, list);
                    }
                }
                return true;
            } catch (e) {
                console.error('Todo load from cloud failed:', e);
                return false;
            }
        },

        getLinkedTodoTime: async function(todoId) {
            const pomodoros = await getAllFromStore(STORES.POMODOROS);
            return pomodoros
                .filter(p => p.linked_todo_id === todoId)
                .reduce((sum, p) => sum + (p.duration_minutes || 0), 0);
        },

        buildTodoTimeMap: async function() {
            const pomodoros = await getAllFromStore(STORES.POMODOROS);
            const map = {};
            for (const p of pomodoros) {
                if (p.linked_todo_id) {
                    map[p.linked_todo_id] = (map[p.linked_todo_id] || 0) + (p.duration_minutes || 0);
                }
            }
            return map;
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
