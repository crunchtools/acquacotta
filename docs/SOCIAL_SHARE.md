# Social Share

Share a link from your phone to Acquacotta and it drafts one post per social
channel, sized to each channel's limit. You edit the drafts, pick the channels
and a time, and Acquacotta schedules them through your own
[Postiz](https://postiz.com) instance.

## Why it matters

Sharing a good article everywhere means writing the same post four times with
four different length limits, usually on a phone. Postiz handles the publishing
but not the writing, and its own UI is a desktop tool. This puts the whole loop
in the Android share sheet: share, glance at the drafts, tap Schedule.

## How it works

1. **Install.** Acquacotta ships a web app manifest with a `share_target`, so
   once it is installed (Chrome, menu, "Add to Home screen" / "Install app") it
   appears in Android's share sheet. A pass-through service worker exists only
   because Chrome requires one to install; it caches nothing.
2. **Share.** Android opens `/share?title=…&text=…&url=…`. Most apps put the link
   in `text`, so the server takes the first http(s) URL from `url`, then `text`,
   and redirects to the Social tab with it.
3. **Sign in if needed.** Credentials live in the browser, so the server cannot
   tell on that redirect whether you are signed in. If you are not, the page
   keeps the link and the sign-in button carries it through Google inside the
   signed OAuth state; you land back on the Social tab with the link.
4. **Draft.** The server fetches the page (public addresses only, every
   redirect and the connected address re-checked, 1 MB and 10 s caps), extracts title, description,
   `og:image` and a short excerpt, and makes one Gemini call in JSON mode that
   returns a post for each selected channel within its character limit. The
   voice rules are fixed: practical, plain-spoken, no hype, at most two hashtags,
   at most one emoji, the URL exactly once.
5. **Edit and schedule.** Each channel gets a card with an include toggle, an
   editable text box and a live count against its limit. Choose the next free
   Postiz slot (default), a specific time, or "save as draft". Scheduling is
   refused while an included post is over its limit, except for drafts.

Channel limits come from Postiz (`/integration-settings/:id`), with a built-in
table as fallback. The page image (PNG, JPEG, GIF or WebP, up to 5 MB) is
downloaded by Acquacotta through the same SSRF guard as the page and uploaded
to Postiz media; Postiz is never handed a URL to fetch. If that fails, the posts
go out without it and the result says why.

### Custody

The same as RT Tickets: the config lives in your Drive at
`plugins/social/config.json`, the Postiz and Gemini keys are Fernet-encrypted
with the server seal key, and the server reads it per request and stores
nothing. Keys are write-only in the UI; the server returns only `has_*` flags.

### Postiz API

Verified against Postiz v2.25.3 (`apps/backend/src/public-api`):

| Item | Value |
|------|-------|
| Base URL | backend + `/public/v1`; the stock image serves the backend at `/api`, so `https://postiz.example.com/api/public/v1` |
| Auth | `Authorization: <api key>`: the raw key, no `Bearer` |
| Key location | Postiz, Settings, **Agents / Dev** |
| Calls used | `GET /is-connected`, `GET /integrations`, `GET /integration-settings/:id`, `GET /find-slot/:id`, `POST /upload` (multipart), `POST /posts` |

Post content is sent as HTML, one `<p>` per line, which is how the Postiz editor
stores it. X needs a reply policy on anything but a draft, so X posts carry
`settings: {"who_can_reply_post": "everyone"}`.

## Example

Settings, Plugins, Social Share (no default channels ticked means all):

```
Postiz API URL   https://postiz.example.com/api        (normalized to …/api/public/v1)
Postiz API key   <from Postiz Settings, Agents / Dev>
Gemini API key   <from aistudio.google.com/apikey>
Gemini model     gemini-3.8-flash
Default channels [x] X  [x] LinkedIn  [ ] Mastodon
```

The `POST /posts` body Acquacotta sends for "next free slot":

```json
{
  "type": "schedule",
  "shortLink": false,
  "date": "2026-10-25T14:00:00Z",
  "tags": [],
  "posts": [
    {
      "integration": {"id": "cm1x..."},
      "value": [{"content": "<p>Line one</p><p>https://example.com/post</p>", "image": []}],
      "settings": {"who_can_reply_post": "everyone"}
    }
  ]
}
```

A Postiz on a private address (same host or LAN) needs the operator to allow it:
`SOCIAL_ALLOWED_HOSTS=postiz.internal`. Only an allowlisted host may use plain
http, since the API key travels in a header. Shared pages are always public-only.

## Related

- [Data architecture](DATA_ARCHITECTURE.md): where per-user plugin config lives
- Spec: [specs/012-social-share](../specs/012-social-share/spec.md)
- RT Tickets (spec 011): the plugin pattern this one follows
