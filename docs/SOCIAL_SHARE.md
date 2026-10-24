# Social Share

A one-box composer for quick posts from your phone: type a post (or share a
link into it), tap the channels, then Post now or Schedule. Acquacotta sends the
same text to every selected channel through your own
[Postiz](https://postiz.com) instance. Long-form, per-channel posts stay a
desktop job.

## Why it matters

Sharing a good article everywhere means writing the same post four times with
four different length limits, usually on a phone. Postiz handles the publishing
but not the writing, and its own UI is a desktop tool. This puts the whole loop
in the Android share sheet: share, type a line, tap Post now.

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
   signed OAuth state; you land back on the Social tab with the link in the
   text box.
4. **Write, or draft (optional).** With a Gemini key and a link in the text,
   "Draft from link" rewrites the text as one post sized for the tightest
   selected channel. The server fetches the page (public addresses only, every
   redirect and the connected address re-checked, 1 MB and 10 s caps), extracts title, description,
   `og:image` and a short excerpt, and makes one Gemini call in JSON mode that
   returns one post within that limit. The
   voice rules are fixed: practical, plain-spoken, no hype, at most two hashtags,
   at most one emoji, the URL exactly once.
5. **Post.** A shared link shows as a card under the text (thumbnail, title,
   site) and its URL is appended to the post on send; ✕ drops it. The preview
   is display-only: platforms build their own cards from the URL (Bluesky and
   LinkedIn show it as a plain link). Channels are platform chips that remember
   your last selection; the counter shows what's left on the tightest channel
   (X and Mastodon count a link as 23) and names any channel you're over. One
   button posts; "Schedule for later" turns it into a scheduling button with a
   time picker (next weekday 9 AM). Either way it takes a second tap to confirm,
   and tapping anywhere else cancels.

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
