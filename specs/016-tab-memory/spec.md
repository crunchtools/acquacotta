# 016: Tab memory, every tab reopens where it was left

Status: Implemented · Author: Scott McCarty · Date: 2026-11-08 · Issue: #237

## Why
Scott: "If the user brings up the Professional tab in Todo, then clicks to Tickets, then clicks back to Todo, the Professional tab should be highlighted. This should be remembered between sessions, even if the page refreshes (saved in IndexDB). This should be part of the plugin framework."

Within a page load the selection already survived a tab switch. A reload dropped it.

## Behaviour
- Each tab with sub-tabs reopens on the last one used, after a tab switch or a reload: the To-do list, the Tickets queue, the Discussions person, Social's Compose or Posts (and Past or Upcoming), and the Reports period.
- Only sub-tabs are remembered. Opening an item (a to-do, a ticket, a post) never replaces the memory, and no item reopens on load.
- The top-level tab is not remembered. A load still starts on Timer, or on the tab a deep link names.
- A deep link wins. `#todos/list/<id>` opens that list and becomes the memory.
- A remembered list, queue or person that no longer exists falls back to All.

## Storage
- The IndexedDB store `ui_state` holds one record per tab, `subtab:<view>` → `[kind, id]`. These are the route parts that tab's deep link already uses (spec 013).
- It is device-local and never synced. It is where this browser left the UI, not user data, so it stays out of Sheets, JSON storage and the MCP settings schema (Principle 2 covers data, and this is not data).
- It is marked `cache: true`, so sign-out clears it along with the cached ids it points at.

## Framework
The memory sits in the deep-link registry, so every tab gets it the same way. A view opts in with two entries next to its existing routes:

```js
ROUTES.todos = {
    current: () => …,                 // already there: [kind, id] for the URL
    tabs: ['', 'list'],               // which kinds are sub-tabs ('' = default)
    restore: (kind, id) => { … },     // set that state, no render
    …
};
```

`setRoute` records the sub-tab whenever it mirrors the URL. `restoreSubTabs()` runs after settings load and before any tab renders. A plugin added later gets the memory by declaring `tabs` and `restore`.
