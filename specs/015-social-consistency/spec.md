# 015: Social tab, one look across Compose, Upcoming and Past

Status: Implemented (v2.30.0) · Author: Scott McCarty · UX: Fable · Date: 2026-10-29

## Why
On v2.29.0 at phone width, Posts used three chip sizes (28px vs Compose's 44px), three colours (green, accent, dashed outline) and three placements for chips and text. Scott: "The look and feel needs to be consistent between Compose, Posts/Upcoming, and Posts/Past… I like the Compose layout. Use it as the model. Where it says Post now and Schedule, use that area for Past and Upcoming. Then show a scrolling list of 10 slots, with a show more results if necessary."

## Principles
- One component per job, each defined once: `.social-segment` (44px switch), `.social-chip` (44px channel circle), `.social-ghost` (44px outline button), `.social-status` (one status line) and `.social-post` (one row).
- Three colours: `--accent` means on, chosen, or the primary action. A `--bg-tertiary` outline means off or not sent. A `--warn` ring means needs attention. There is no green in Posts.
- The segment tells you where you are (Past or Upcoming), and the chip tells you whether the post went. A word on the meta line names the exception.

## Pane skeleton (390px)
| | Compose | Upcoming / Past |
|---|---|---|
| A | Compose \| Posts segment (shared element, same box) | same |
| B | text, link card, count, chips | **Past \| Upcoming** segment, the same CSS as Post now \| Schedule |
| C | Post now \| Schedule, when, Post button | status line, ≤10 rows, **Show more** (full-width ghost button) |

The segment margin is `.75rem` everywhere, and the chip row margin is `.5rem 0` everywhere.

## Channel glyph
Compose's `.social-chip` is used in Compose, in post rows and in the expanded channel lines: 44×44px, round, bold glyph.

| Context | State | Look |
|---|---|---|
| Compose | selected / not / over limit | on / off / on + ring |
| Posts | PUBLISHED, or QUEUE in the future | on |
| Posts | QUEUE in the past ("Not sent yet"), ERROR | off + ring |
| Posts | DRAFT | off |

In Posts the chip is a `span`. Summary chips are `aria-hidden`, and the summary carries its own `aria-label`. Expanded chips are `role=img` with "Name: State".

## Row (identical in both lists)
- **Meta line:** `Today · 10:20 AM` (Tomorrow and Yesterday too, otherwise `Mon, Nov 2 · 9:20 AM`, with the year when it isn't this year), then `· N versions`, then an exception word (`Failed`, `2 of 6 failed`, `Not sent yet`, `Draft`), then the caret.
- **Chip row.**
- **Text:** two lines, clamped.

Upcoming is soonest first, Past newest first. An entry is Past when its date is before now.

An open entry hides the summary chips and text. It shows each version's text once, then one 44px line per channel (chip · name · state · View post ›), then Copy link and Open in Postiz.

## Loading and paging
- "10" means 10 consolidated entries. Show more reveals 10 more. When the loaded range runs short, it first fetches 56-day windows further out until it has enough, or reaches the 364-day horizon. Then "No older posts in the last year" or "Nothing more scheduled in the next year" replaces the button.
- The first load fetches `[today−56, today)` and `[today, today+56)` in parallel. Both lists come from that one range, so switching between them is instant. The windows are 56 days because the backend caps a request at 62 days, and a 62-day local-midnight span across a DST change goes over.
- **Empty:** "Nothing scheduled through Dec 23" with a Compose a post button, or "No posts since Sep 3".
- **Loading:** three skeleton rows.
- **Errors:** the status line shows Retry. A failed Show more keeps the rows already shown.
- **Cache:** the first range is cached per account, as before.

## Routes
- `#social/posts` is Upcoming (the default).
- `#social/posts/past`.
- `#social/post/<id>` widens both ways to the horizon, picks the post's list, opens the entry and centres it.

## Accessibility
- Segments are radiogroups and arrow keys move between their options.
- The list is `role=list`, rows are `role=listitem`, and Show more has `aria-controls`.
- The status line announces "N more shown".
- Every tap target is at least 44px.

## Decisions on the spec
Fable put Upcoming on the left as the default. I put **Past | Upcoming** in timeline order, matching Scott's wording, and kept Upcoming as the default. Fable proposed per-list caches and fetch windows; I used one merged range with derived lists. It is simpler and has the same behaviour.
