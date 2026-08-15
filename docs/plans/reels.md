# Reels — plan

## Summary

A new **Reels** section: staff register a set of language-teaching Instagram
accounts in Django admin, a scheduled job pulls their new reels once a day and
stores the metadata, and each user gets a feed of the reels **they haven't seen
yet**. Staff can also **upload our own reels** through the same admin — same
model, same feed, no scraping cost, and no copyright question (see
[Our own reels](#our-own-reels)).

Four hard design rules, all of them cost- or risk-driven:

1. **We host the video ourselves, on Cloudflare R2.** Embedding was the first
   instinct and it is wrong for *this* audience: the app is Persian-first and
   **Instagram has been blocked in Iran since 2022**, so an Instagram embed is a
   blank box for most of our users. R2 also turns out to cost ~$0.50/month
   because it charges **zero egress**. See [Video hosting & CDN](#video-hosting--cdn-cost).
2. **Scraping cost is a function of how many accounts we watch — not how many
   users we have.** One fetch serves every user. See [Financial analysis](#financial-analysis).
3. **Reels expire.** A 90-day media TTL keeps storage flat at ~$0.01/month
   forever instead of growing, plus a "purge before date" action in the admin.
   Crucially it's the **media** that expires, not the row — see
   [Retention](#retention--lifecycle) for why deleting rows costs money.
4. **Nothing spends money automatically until Phase 3.** Phase 1 ships with a
   manual "Fetch now" button, a hard budget ceiling, and a
   [Costs page](#the-costs-page) in Django admin showing every expense this
   feature generates — with a month-end projection and Telegram budget alerts.
   The cron comes only after we've measured real cost. See
   [Cost controls](#cost-controls-built-into-the-feature).

This document is the source of truth for the feature.

---

## Financial analysis

### 1. What the vendor actually charges

Apify is the right tool. The relevant actors are **pay-per-event (PPE)** — you
pay per *item returned*, not per compute-minute, which makes cost fully
predictable from our own config.

| Actor | Model | Free plan | Starter plan | Scale/Business |
|---|---|---|---|---|
| [`apify/instagram-reel-scraper`](https://apify.com/apify/instagram-reel-scraper) | per reel | **$2.60 / 1,000** | **$2.30 / 1,000** | down to ~$1.00 / 1,000 |
| [`apify/instagram-scraper`](https://apify.com/apify/instagram-scraper) (general) | per item | $2.70 / 1,000 | $2.30 / 1,000 | $1.50–1.90 / 1,000 |

**Use `apify/instagram-reel-scraper`.** It is purpose-built, slightly cheaper on
the free tier, and returns exactly the fields we need.

Apify subscription tiers ([pricing](https://apify.com/pricing)):

| Plan | Monthly | Platform credit included |
|---|---|---|
| Free | $0 | **$5 / month, renews monthly** |
| Starter | $29 | $29 |
| Scale | $199 | $199 |

The credit is *consumed by* the per-result charges — so on the Free plan,
anything up to $5/month of scraping is **genuinely $0 out of pocket**. On
Starter you pay $29 and the first $29 of usage is free; beyond that it is
pay-as-you-go at the same rate.

Extras we deliberately **do not** buy:

- **Transcripts** — billed per minute of audio. Off in Phase 1–3.
- **Video download** — billed per MB. Never; see [Storage](#storage--hosting-cost).
- **Residential proxy** ($8/GB) — not needed, PPE actors include platform usage
  and proxy in the per-result price.

### 2. The cost formula

Cost is entirely determined by three knobs we control in admin:

```
reels_billed_per_month = accounts × results_limit × (30 / poll_interval_days)
monthly_cost_usd       = reels_billed_per_month / 1000 × rate
```

`results_limit` is "how many of the newest reels we ask for per account per
poll". **We are billed for every reel returned, including ones we already have.**
That is the single most important cost fact in this document — dedupe happens on
our side, after we've paid. So `results_limit` should be set to just above the
posting rate of the account, not "high, to be safe".

### 3. Cost scenarios

Rate columns: Free-plan rate $2.60/1k, Starter rate $2.30/1k. "Out of pocket" =
what actually leaves the bank account after the included credit.

| # | Accounts | `results_limit` | Poll | Reels billed/mo | @ $2.60/1k | @ $2.30/1k | Best plan | **Out of pocket / mo** |
|---|---|---|---|---|---|---|---|---|
| 1 | 10 | 3 | daily | 900 | $2.34 | $2.07 | Free | **$0** |
| 2 | 20 | 3 | every 2 days | 900 | $2.34 | $2.07 | Free | **$0** |
| 3 | **20** | **3** | **daily** | **1,800** | **$4.68** | $4.14 | **Free** | **$0** ← recommended MVP |
| 4 | 20 | 5 | daily | 3,000 | $7.80 | $6.90 | Starter | $29 |
| 5 | 30 | 3 | daily | 2,700 | $7.02 | $6.21 | Starter | $29 |
| 6 | 50 | 3 | daily | 4,500 | $11.70 | $10.35 | Starter | $29 |
| 7 | 50 | 5 | daily | 7,500 | $19.50 | $17.25 | Starter | $29 |
| 8 | 100 | 3 | daily | 9,000 | $23.40 | $20.70 | Starter | $29 |
| 9 | 100 | 5 | daily | 15,000 | $39.00 | $34.50 | Starter + overage | ~$34.50 |
| 10 | 200 | 3 | daily | 18,000 | $46.80 | $41.40 | Starter + overage | ~$41.40 |

**Row 3 is the launch configuration: 20 curated accounts, 3 newest reels each,
polled once a day = $4.68/month, which fits inside the Free plan's $5 monthly
credit.** We can run the entire feature at zero marginal cost until it proves
itself.

Note the shape of the curve: going from 20 to 100 accounts costs ~$29/month, not
5× anything painful. Content supply is cheap; this feature does not have a cost
cliff.

### 4. Cost per *useful* reel, and per user

Billed reels ≠ new reels. A typical language-teaching account posts ~1 reel/day.
Fetching the 3 newest daily means we pay for 3 and keep ~1:

| Metric | Value at MVP config |
|---|---|
| Reels billed / month | 1,800 |
| Genuinely new reels kept / month | ~600 (20 accounts × ~1/day) |
| **Cost per new reel** | **~$0.0078** |
| Cost per new reel if `results_limit` were 5 | ~$0.013 (67% waste) |
| Cost per new reel at `results_limit` 2 | ~$0.005 (but risks missing posts) |

Tuning `results_limit` down is the highest-leverage cost action, and the
`ReelFetchRun` table (below) records `items_returned` vs `items_new` per account
so this is visible rather than guessed.

**Cost per user — the important number:**

| Monthly active users | Scraping cost/mo | **Cost per user / mo** |
|---|---|---|
| 100 | $4.68 | $0.047 |
| 1,000 | $4.68 | **$0.005** |
| 10,000 | $4.68 | $0.0005 |

Because we scrape once and serve everyone, **the cost does not grow with users
at all.** Against the Basic plan at $1.00/month
([subscription.md](subscription.md)), reels consume ~0.5% of revenue at 1,000
users. Unlike the Gemini-backed features, this one needs no per-user quota.

### 5. Video hosting & CDN cost

#### Why embedding is not an option here

The obvious cheap answer is "don't host video, embed Instagram's player". For a
general-audience product that would be right. For *this* product it fails on
three counts, in descending order of severity:

1. **Instagram is blocked in Iran** (since September 2022, and still blocked
   through the 2026 restrictions). Our UI is Persian-first. An `iframe` pointing
   at `instagram.com` renders nothing for a user in Iran, and neither does the
   thumbnail — `scontent.cdninstagram.com` is blocked too. The feature would
   simply not work for a large share of the target users.
2. **Meta now requires a Facebook App access token** for the oEmbed route, and
   has added Reels-specific permission scopes. The token-free `/embed/` iframe
   still works but is undocumented and can be withdrawn without notice.
3. Embeds break whenever a creator edits, archives, or privates a post.

Point 1 alone settles it. **We host the video.**

#### Where to host it

Self-hosting sounds expensive because on most providers **egress** is the bill,
not storage. Cloudflare R2 charges **$0 for egress** — that single fact makes
this cheap. Comparison, sized at a 12-month-old library and 1,000 monthly active
users watching 20 reels each:

| Option | Storage/mo | Egress (120 GB/mo) | **Total/mo** | At 10k MAU (1.2 TB/mo) |
|---|---|---|---|---|
| **Cloudflare R2** | $0.50 | **$0** | **~$0.50** | **~$0.50** |
| Bunny.net CDN | ~$0.45 | ~$7.20 (ME $0.06/GB) | ~$8 | ~$72 |
| AWS S3 + CloudFront | ~$1 | ~$10 | ~$11 | ~$102 |
| Cloudflare Stream | $18 | $10 | ~$28 | ~$100 |
| Render disk + bandwidth | ~$0.75 | ~$6 overage | ~$7 | **~$330** |

**Use Cloudflare R2.** Note that R2 is ~50× cheaper than Cloudflare's own
*Stream* product: Stream bills $5/1,000 minutes stored + $1/1,000 minutes
delivered, which we'd be paying for adaptive-bitrate transcoding and a player we
don't need — reels are 30-second H.264 MP4s that play fine in a bare
`<video>` tag. Also note the last row: hosting media off Render's own bandwidth
is the one genuinely bad option at scale.

#### R2 in detail

R2 rates ([pricing](https://developers.cloudflare.com/r2/pricing/)):
storage **$0.015/GB-month**, Class A (writes) **$4.50/M**, Class B (reads)
**$0.36/M**, egress **free**. Free tier: **10 GB storage, 1M Class A, 10M Class
B per month**.

Sizing assumption: Instagram *serves* reels re-encoded far below creator-upload
specs — expect **~3–6 MB for a 30-second reel**, not the 30–50 MB an exported
1080p/15Mbps master would be. The table below uses the conservative **6 MB**.
(Phase 0 measures the real number; the conclusion doesn't change either way —
see the sensitivity note.)

At 600 new reels/month = **3.6 GB/month** of library growth:

| Age | Library | Stored | Billable (−10 GB free) | **Storage $/mo** |
|---|---|---|---|---|
| 3 months | 1,800 | 6.5 GB | 0 | **$0** |
| 6 months | 3,600 | 13 GB | 3 GB | $0.05 |
| 12 months | 7,200 | 43 GB | 33 GB | **$0.50** |
| 24 months | 14,400 | 86 GB | 76 GB | $1.15 |
| 36 months | 21,600 | 130 GB | 120 GB | $1.80 |

That column grows forever, which is the argument for
[retention](#retention--lifecycle). With a media TTL, storage stops being a
growth line and becomes a **constant**:

| Media TTL | Steady-state stored | Billable | **Storage $/mo, forever** |
|---|---|---|---|
| 30 days | 3.6 GB | 0 | **$0** |
| **90 days** | **10.8 GB** | 0.8 GB | **~$0.01** |
| 180 days | 21.6 GB | 11.6 GB | ~$0.17 |
| none | unbounded | — | $0.50 → $1.80 → … |

**90 days keeps us essentially inside R2's free tier permanently.** That is the
recommended default.

Operations, both comfortably inside the free tier:

| | Volume/month | Free tier | Used |
|---|---|---|---|
| Class A (ingest: video + thumbnail) | 1,200 | 1M | 0.1% |
| Class B (views: 1k MAU × 20 × 2 objects) | 40,000 | 10M | 0.4% |
| Class B at 10k MAU | 400,000 | 10M | 4% |

**Sensitivity:** even if reels average 10 MB, year-1 storage is $0.93/month. Even
at 10,000 MAU, egress stays $0 and ops stay inside the free tier. There is no
input to this model that makes hosting expensive — which is exactly why we
should not spend engineering time on transcoding to save space.

#### Two caveats worth knowing up front

- **DNS moves to Cloudflare.** An R2 custom domain (`cdn.nemoapps.xyz`) requires
  the zone to be on Cloudflare — the `r2.dev` URL is rate-limited and explicitly
  not for production. So `nemoapps.xyz` DNS moves to Cloudflare (free); existing
  Render and Vercel records carry over as **DNS-only (grey cloud)** entries and
  keep working unchanged. Caching on the custom domain needs a *Cache Everything*
  rule to cover MP4s.
- **Reachability from Iran is an assumption to verify, not a fact.** Our own
  domain isn't on a blocklist the way `instagram.com` is by name, which is the
  whole point — but Cloudflare ranges have been throttled in Iran at times.
  Phase 0 must test `cdn.nemoapps.xyz` from a real Iranian connection. Fallback
  if it's poor: Bunny.net at ~$8/month for the same traffic (different IP
  footprint), or ArvanCloud for a domestic-CDN option. Both are cheap enough that
  this is a reachability decision, not a budget one.

#### User-side data usage

At 6 MB/reel, a session of 20 reels costs the *user* ~120 MB of mobile data.
That is the real cost of this feature, and it's paid by someone on an Iranian
mobile plan. Mitigations, in order of value-per-effort: **tap-to-play with no
autoplay preload** (Phase 2, free), a "data saver" toggle, and — only if it
proves to matter — a 720p re-encode at ingest (Phase 4; halves user data, saves
us nothing).

### 6. Bottom line

| Item | Phase 1–2 | Phase 3 (auto-poll, 20 accounts, 1k users) | At 100 accounts, 10k users |
|---|---|---|---|
| Apify scraping | $0 (manual runs, a few cents) | **$0** (inside free credit) | $29/mo |
| R2 storage, 90-day TTL | $0 (free tier) | **~$0.01/mo, flat** | ~$0.60/mo |
| R2 egress + ops | $0 | **$0** | **$0** |
| **Total** | **~$0** | **~$0/mo** | **~$30/mo** |

The feature launches free, stays effectively free at 20 accounts, and lands
around $30/month at 5× the accounts and 10× the users — where the bill is
essentially *just Apify*, because retention pins storage flat and R2 charges
nothing for egress. The risk to manage is not the cost level — it's
*uncontrolled* cost, which the next section addresses.

---

### 7. Measured, not modelled — Phase 0 results

The first real run happened on **2026-08-15**: one account (`@easytodeutsch`),
`results_limit=3`, through `apify/instagram-reel-scraper`. Everything above was an
estimate; these are the actual numbers, and both moved in our favour.

| | Modelled | **Measured** | Effect |
|---|---|---|---|
| Apify rate | $2.60 / 1,000 | **$2.07 / 1,000** ($0.0062 for 3 reels) | ~20% cheaper |
| Reel size | 6 MB @ 30s (conservative) | **~0.10 MB per second** → 1.67 MB @ 20s, 2.89 MB @ 30s, 4.54 MB @ 40s | ~half |

Instagram re-encodes reels well below creator-upload specs, exactly as assumed —
the conservative 6 MB was double reality. Re-running the two headline numbers:

| | With modelled figures | **With measured figures** |
|---|---|---|
| MVP config (20 accounts × 3 daily) | $4.68/mo | **$3.73/mo** — still inside the $5 free credit |
| Library growth | 3.6 GB/mo | **1.8 GB/mo** |
| Steady-state storage @ 90-day TTL | 10.8 GB → ~$0.01/mo | **5.4 GB → $0/mo**, under R2's 10 GB free tier |
| Storage after 12 months, no TTL | 43 GB → $0.50/mo | 21.6 GB → $0.17/mo |

**At the launch configuration both vendors stay inside their free tiers
indefinitely.** The retention TTL is no longer needed to control cost at this
scale — it's now purely a content-freshness decision. It stays on anyway: it's
the difference between a bounded system and one that merely happens to be small.

Also confirmed in that run: the actor accepts a list of usernames, the output
field names match `apify.normalise_item`, and the stored MP4s serve as
`video/mp4` with valid `ftyp isom` headers — playable in a bare `<video>` tag.

---

## Cost controls built into the feature

These are functional requirements, not nice-to-haves. In order of importance:

1. **`maxTotalChargeUsd` on every single Apify run.** The Apify API accepts this
   per-run parameter for PPE actors; the actor terminates gracefully at the cap
   and we are never charged past it. We set it to
   `expected_items × rate × 1.2`. This makes a runaway run structurally
   impossible, not just unlikely.
2. **A monthly budget ceiling** — a `ReelsBudget` singleton in admin holding
   `monthly_budget_usd` (default **$5.00**, matching the free credit) and a
   running `spent_this_month_usd`. Before any run: if
   `spent + estimated_cost > monthly_budget`, the run is **skipped and logged**,
   not trimmed silently.
3. **Global kill switch** — `REELS_SCRAPING_ENABLED` env var. Off by default in
   Phase 1.
4. **Per-source knobs** — `is_active`, `poll_interval_hours`, `results_limit`
   are all editable per account in admin. An account that posts weekly gets
   `poll_interval_hours=168`, not 24.
5. **Full spend audit, in Django admin** — every run writes a `ReelFetchRun` row
   with `items_returned`, `items_new`, and the **actual** `cost_usd` read back
   from the Apify run's usage field (not our estimate). A dedicated
   [Costs page](#the-costs-page) shows current spend vs budget, a month-end
   projection, 12-month history, per-source cost-per-new-reel, and a
   reconciliation against what Apify and Cloudflare actually report — so the
   feature's cost is answerable without logging into any vendor console.
   Budget thresholds (50/80/100%) fire Telegram staff alerts.
6. **Manual before automatic** — Phase 1 has no scheduler at all. The only way to
   spend money is a staff member clicking "Fetch now".
7. **Zero-cost fallback path** — staff can upload a reel straight into admin
   without any Apify call. If we ever want to pause scraping entirely, the
   feature still works, just hand-curated.
8. **Retention** — a media TTL (default **90 days**) that turns storage from a
   growing line into a flat ~$0.01/month, plus a manual "purge before date"
   action in the admin. Full design in [Retention & lifecycle](#retention--lifecycle).

---

## Language matching

Every teaching account has **two** languages, not one: the language it *teaches*
and the language it *explains in*. `@easytodeutsch` teaches German to English
speakers; a Persian-language German channel teaches the same German to a
completely different audience. Filtering on "German" alone would put both in the
same feed and hand half the users narration they can't follow.

So content carries a pair, and so does the user:

| Content (`ReelSource` and `Reel`) | User |
|---|---|
| `target_language` — what it teaches | `learning_languages[]` — what they want to learn |
| `base_language` — what it's explained in | `known_languages[]` — what they already understand |

A reel matches when **both** halves line up:

```python
target_language ∈ user.learning_languages
AND (base_language ∈ user.known_languages OR base_language == "")
```

`base_language = ""` means **immersive** — German taught in German, no
translation. There's no second language to require, so it reaches every learner
of the target. Without this case, monolingual content would be invisible to
everyone.

Worked example, the one from the brief: a user learning **German + English** who
reads **English + Persian** gets German-in-English, German-in-Persian,
English-in-Persian, and every immersive German or English reel — but *not*
German-in-Turkish.

Both are ordered lists (first = primary) and multi-select, because people learn
more than one language and most already read more than one.

### Three different language questions

The app now asks three things that are easy to conflate, and must not be:

| Field | Question | Values |
|---|---|---|
| `User.ui_language` | What is the *interface* written in? | `en` / `fa` only — what we've translated |
| `User.learning_languages` | What do you want to learn? | any catalogue code |
| `User.known_languages` | What do you already understand? | any catalogue code |

Someone can read the app in Persian, be learning German, and understand both
Persian and English. `ui_language` is **not** a proxy for either of the others —
it's only a good *default* for `known_languages`, which is how onboarding
pre-ticks it.

The catalogue lives in `apps/accounts/languages.py`, mirrored to
`frontend/src/lib/languages.ts`. Unknown codes from a client are **dropped, not
rejected** — a stale code should cost that one entry, not the whole save.

### Where we ask

- **Onboarding** — a step after the name, before decks (`Welcome.tsx`), using the
  shared `LanguagePicker` component. `known_languages` is pre-ticked with the UI
  language they just chose; a default to confirm, never a substitute for asking.
- **The reels feed** — if `learning_languages` is empty, the feed shows the same
  picker instead of content. Accounts created before this existed have no
  preferences, and guessing from `ui_language` would quietly build the wrong
  feed. One extra question beats a feed of videos they can't follow.

Empty `learning_languages` is the "not asked yet" signal — checked by
`matching.has_language_prefs()` / `hasLanguagePrefs()`.

---

## Data model

New app: `apps.reels` (added to `INSTALLED_APPS` and `core/urls.py` alongside
the existing apps).

### `ReelSource` — a content channel

An Instagram account we scrape, **or** one of our own channels — see
[Our own reels](#our-own-reels).

| Field | Notes |
|---|---|
| `kind` | `instagram` (scraped) or `own` (uploaded by us) |
| `username` | unique, without `@`; a channel slug for `own` sources |
| `display_name` | shown in the feed |
| `profile_pic` | `ImageField`, cached like thumbnails |
| `target_language` / `base_language` | what it teaches, and what it explains in — see [Language matching](#language-matching) |
| `level` | optional `a1`…`c2`, for filtering later |
| `topics` | free tags, e.g. `grammar,slang` |
| `is_active` | bool, default `True` |
| `permission_granted` | bool + `permission_note` — did the creator agree? See [Copyright](#copyright--tos--the-one-that-got-worse) |
| `poll_interval_hours` | default `24` |
| `results_limit` | default `3` — the per-poll cost knob |
| `retention_days` | null = use the global default; see [Retention](#retention--lifecycle) |
| `last_polled_at`, `last_status`, `last_error` | operational state |
| `created_at` | |

### `Reel` — one scraped reel

| Field | Notes |
|---|---|
| `source` | FK → `ReelSource` |
| `key` | **unique** — the dedupe key. For scraped reels it's the Instagram shortcode (the `ABC123` in `instagram.com/reel/ABC123/`); for [our own reels](#our-own-reels) it's a generated slug. |
| `url` | canonical reel URL — always kept, always linked back to |
| `caption`, `hashtags` (JSON) | |
| `video_key` | R2 object key, e.g. `reels/<key>.mp4` |
| `video_bytes` | for the storage-cost report in admin |
| `thumb_key` | R2 object key for the poster image |
| `media_status` | `pending` / `stored` / `failed` / `purged` — only `stored` is servable |
| `media_purged_at` | when the R2 objects were deleted |
| `is_evergreen` | exempt from the retention purge; defaults **true** for own reels |
| `pin_until` | while set and in the future, sorts to the top of the feed |
| `title` | used by own reels; blank for scraped ones |
| `duration_seconds`, `view_count`, `like_count`, `comment_count` | as of fetch time; not refreshed |
| `posted_at` | Instagram's timestamp — the feed sort key |
| `target_language`, `base_language`, `level` | copied from source, overridable per reel |
| `is_published` | staff moderation gate |
| `fetched_at` | |

`is_published` defaults to **`True`** so the feed fills without manual work, but
staff can unpublish anything off-topic. (A default of `False` would make the
feature depend on daily human review — not worth it for curated sources.)

### `ReelView` — the "already seen" record

`user` FK, `reel` FK, `seen_at`, `saved` bool, unique on `(user, reel)`.
This one table powers both the unseen feed and a future "Saved" tab.

### `ReelFetchRun` — the spend ledger

`source` FK (nullable — a batch run covers several), `apify_run_id`,
`started_at`, `finished_at`, `status`, `items_returned`, `items_new`,
`cost_usd`, `error`. Read-only in admin.

### `ReelsBudget` — singleton settings row

`monthly_budget_usd` (default `5.00`), `month` (YYYY-MM),
`spent_this_month_usd`, `default_results_limit`, `default_retention_days`.
Resets on month rollover.

### `ReelPurgeLog` — the deletion ledger

`ran_at`, `cutoff_date`, `reels_purged`, `bytes_freed`, `triggered_by`
(`cron` or a staff user), `hard_delete` bool. Read-only. A destructive job should
never be invisible.

### `ReelsStorageSnapshot` / `ReelsCostMonth` — cost history

Daily storage readings and monthly cost roll-ups, feeding the
[Costs page](#the-costs-page). Kept separate from `ReelFetchRun` so the spend
record outlives the reels it paid for.

---

## Fetch pipeline

`apps/reels/apify.py` + `apps/reels/tasks.py`.

**Batching matters.** The reel scraper accepts a list of usernames per run, so
we issue **one Apify run per group of due sources sharing a `results_limit`**,
not one run per account. Fewer runs, same per-result cost, less overhead.

```
poll_reel_sources()                    # celery-beat, hourly
  ├ if not REELS_SCRAPING_ENABLED: return
  ├ due = active sources where last_polled_at + poll_interval <= now
  ├ estimate = Σ(results_limit) × rate
  ├ if budget.spent + estimate > budget.monthly_budget_usd:
  │     log a skipped ReelFetchRun and return          ← hard stop
  ├ for each results_limit group:
  │     run actor with { username: [...], resultsLimit: N }
  │                  + maxTotalChargeUsd = estimate × 1.2
  │     for each item:
  │         get_or_create Reel by key                 ← dedupe, after billing
  │         if created: queue ingest_reel_media.delay(reel_id)
  │     write ReelFetchRun with real cost_usd from the run's usage
  └ budget.spent_this_month_usd += actual cost

ingest_reel_media(reel_id)                             # one task per new reel
  ├ stream videoUrl → R2 via boto3 (R2 is S3-compatible)
  ├ stream displayUrl → R2 as the poster image
  ├ record video_bytes, set media_status = "stored"
  └ on failure: media_status = "failed", retry twice, then leave unpublished
```

**Ingest is time-critical.** Instagram's `videoUrl` and `displayUrl` are signed
CDN links that expire within days, so the download must happen in the same run,
not on a nightly sweep. A reel whose media never lands stays `media_status
= "failed"` and is filtered out of the feed — it is never shown as a broken card.

Bandwidth: 3.6 GB/month leaves Render on upload to R2, well inside the included
allowance. If Instagram's CDN ever throttles Render's datacenter IPs, the
fallbacks are (a) Apify's own per-MB *video download* add-on event, or (b) doing
the copy in a Cloudflare Worker that streams IG → R2 without touching Render at
all. Phase 0 checks whether either is needed.

An **hourly** beat tick (not per-minute like reminders) driving per-source
`poll_interval_hours` gives per-account scheduling without a per-account cron.

### Scheduling in production: GitHub Actions, not celery-beat

**There is no Celery worker in production.** The deployment is a single free-tier
Render web service running with `CELERY_TASK_ALWAYS_EAGER`, so `celery beat`
never runs there — the beat entries below only fire in local docker-compose.
Adding a worker service would mean paying for a server this feature does not
justify.

The project already solves this: `.github/workflows/keepalive.yml` uses GitHub
Actions as the cron daemon. Reels does the same, in
**`.github/workflows/reels-poll.yml`** — a daily `python manage.py poll_reels`.

The one real decision here is *where the work runs*:

| | Actions calls an HTTP endpoint on Render | **Actions runs the job itself** (chosen) |
|---|---|---|
| Time budget | gunicorn's 30s request timeout | 30 min on the runner |
| ~60 downloads + R2 uploads | needs a chunked start/collect protocol and repeated calls | one straightforward pass |
| New public attack surface | a cron endpoint with a shared secret | none |
| Credentials | stay on Render | duplicated into GitHub secrets |
| Load on the free web instance | heavy, on an instance that sleeps every 15 min | none |

Fetching a day's reels takes minutes, so the endpoint route would need the poll
split into `start` and `collect` phases with the workflow looping over them —
real complexity, to run heavy I/O on the weakest machine available. Running it on
the runner instead costs one thing: `DATABASE_URL` and the R2 keys become GitHub
secrets. That's ordinary CI practice, and the runner has the bandwidth for the
video copying anyway.

`poll_reels` also runs the purge and the storage snapshot, so one workflow covers
all three scheduled jobs. `--dry-run` (exposed as a `workflow_dispatch` input)
reports what's due and what it would cost without spending anything.

**Three independent off switches**, any one of which stops all spending:
disable the workflow in the GitHub UI; unset the `REELS_SCRAPING_ENABLED`
variable; or let the monthly budget guard trip. The workflow also sets
`concurrency: reels-poll` — two overlapping polls would each pay for the same
reels.

For local development, add to `CELERY_BEAT_SCHEDULE` in `core/settings.py`:

```python
"poll-reel-sources": {
    "task": "apps.reels.tasks.poll_reel_sources",
    "schedule": crontab(minute=7),               # hourly, off the reminder minute
},
"purge-expired-reel-media": {
    "task": "apps.reels.tasks.purge_expired_reel_media",
    "schedule": crontab(hour=3, minute=20),      # daily
},
```

Note the deployment already runs `CELERY_TASK_ALWAYS_EAGER` in the single-server
mode — the manual "Fetch now" admin action must therefore be safe to run inline
(it is: one HTTP call to Apify, bounded by `maxTotalChargeUsd`).

---

## Our own reels

We also publish **our own** reels — recorded by us, uploaded through admin, no
Instagram involved. This is not a side feature; it's the part of Reels we fully
control, and it changes the risk profile of the whole plan.

### It reuses the existing model, not a parallel one

`ReelSource` gains a **`kind`** field — `instagram` or `own` — and everything
downstream works unchanged:

| | `kind="instagram"` | `kind="own"` |
|---|---|---|
| `username` | the IG handle | a channel name, e.g. `nemo` |
| Where media comes from | scraped, then copied to R2 | uploaded straight to R2 |
| `Reel.key` | the IG shortcode | a generated slug, e.g. `nemo-dativ-01` |
| Polling / Apify cost | yes | **never polled, $0** |
| Retention TTL | 90 days | **exempt — see below** |
| Feed, seen-tracking, saving | identical | identical |

One model means the feed query, `ReelView`, pagination, the admin grid, and the
frontend player all need **zero** special-casing. The only branches are in the
poller (skip `own` sources) and the purge job (skip `own` reels).

There can be more than one `own` source — a Nemo channel, a guest teacher, a
partner school — so they're attributable in the feed rather than all lumped
together.

### Upload flow

In the admin dashboard, an **Upload a reel** form next to *Add source*:

`video (mp4)` · `poster (jpg/png)` · `title` · `caption` · `language` · `level` ·
`topics` · `source` (which own-channel) · `pin_until` (optional)

On save: validate → upload both to R2 → create the `Reel` with
`media_status="stored"`. Same objects, same CDN path, same player as a scraped
reel.

**Constraints, enforced at upload:**

- **MP4 / H.264 video + AAC audio.** Not negotiable — it's the only combination
  that plays reliably in iOS Safari, and this is a PWA with an installed-iOS
  audience (see the existing iOS TTS fix). Reject anything else at the form with
  a clear message rather than discovering it on someone's iPhone.
- **Max 50 MB**, 9:16 recommended, ≤ 3 minutes.
- **Poster image is required in Phase 1.** Auto-extracting a frame needs `ffmpeg`,
  which is *not* in the backend Docker image today — adding it is a
  Phase 4 convenience, not a launch blocker.

### Two fields own reels need

- **`pin_until`** — a datetime. While set and in the future, the reel sorts to
  the top of the feed regardless of `posted_at`. Our own content is often
  time-relevant (a new lesson, an announcement) and shouldn't have to wait its
  turn behind scraped reels.
- **`is_evergreen`** — defaults to **`True`** for own reels. We made this
  content; there is no re-scrape path if it's purged. See below.

### Retention: own reels are never auto-purged

A scraped reel that gets purged is recoverable — worst case we scrape it again.
**An own reel that gets purged is simply gone** unless someone still has the
source file. So the purge job excludes `source.kind == "own"` outright, in
addition to the `is_evergreen` default. Deleting an own reel is a deliberate,
manual, single-record action.

Cost impact is negligible and worth stating: even 200 own reels at 6 MB is
1.2 GB — inside R2's free tier, permanently, with no Apify charge at all.

### Why this matters beyond "nice to have"

1. **It's the only content with no copyright question.** Own reels are 100% ours
   — no ToS exposure, no takedown risk, no permission to ask for.
2. **It de-risks the entire feature.** If Instagram scraping becomes untenable —
   the actor breaks, Meta clamps down, the legal posture sours — Reels does not
   die. It becomes a first-party content channel and keeps running.
3. **It's the natural home for product tie-ins.** An own reel can carry an
   optional FK to a deck or `BookLesson`, turning "watch" into "add these 8 words
   to my deck" with one tap. That is a far more natural fit for content we
   scripted than for a scraped clip, and it's the strongest version of the
   Phase 4 *make cards from this reel* idea.

Because of (2), it's worth shipping own-reel upload **in Phase 1 alongside the
scraper**, not deferring it — it costs little and means the feature has a working
content path before a single Apify call is made.

---

## Retention & lifecycle

Reels are dated content — a "5 German phrases" clip from eight months ago has
little pull, and keeping it costs storage forever. So reels expire. But **naive
deletion has a trap that costs real money**, so the design is two-stage.

### The trap: deleting a reel makes us pay for it again

`key` is our dedupe key. If we hard-delete a `Reel` row while that reel is
still among the account's newest posts, the very next poll re-scrapes it — **we
pay for it a second time, and every user sees it again as "new".** For a source
polled daily this could repeat indefinitely.

So the row is not what expires. **The media is.**

### Two stages

| Stage | What happens | When | Effect |
|---|---|---|---|
| **1 — purge media** | Delete the R2 video + poster objects. Keep the DB row; set `media_status = "purged"`, stamp `media_purged_at`. Reel drops out of the feed. | `posted_at` older than the TTL (default **90 days**) | Recovers ~100% of the storage cost |
| **2 — hard delete** | Delete the row and its `ReelView` rows. | Manual only, never automatic | Frees a few KB of Postgres; **re-exposes us to re-ingest cost** |

Stage 1 recovers essentially all the money — a metadata row is a few hundred
bytes, so 21,600 rows after three years is well under 10 MB of Postgres. **There
is no financial reason to ever run stage 2 automatically.** It exists for real
cleanup: a source we dropped entirely, a takedown, spam.

### Exemptions

The purge job skips a reel if any of these hold:

- **It's one of [our own reels](#our-own-reels)** (`source.kind == "own"`). There
  is no re-upload path if we delete it — this exclusion is absolute, not a
  default someone can toggle off in bulk.
- `is_evergreen` — a staff flag for the genuinely timeless ones. This is how a
  small hand-picked "best of" library survives the TTL.
- It has been **saved** by at least one user. Purging media out from under
  someone's saved list is a bad experience for a rounding error of storage.
- `posted_at` is null (hand-added reels without a reliable date).

Per-source override: `retention_days` on `ReelSource` (null = use the global
default), so a slow-posting, high-quality account can keep a longer window.

### The job

```
purge_expired_reel_media()                    # celery-beat, daily at 03:20 UTC
  ├ if REELS_RETENTION_DAYS is unset: return          ← opt-in, off by default
  ├ cutoff = now - (source.retention_days or REELS_RETENTION_DAYS)
  ├ qs = Reel.objects.filter(media_status="stored", posted_at__lt=cutoff)
  │        .exclude(source__kind="own")           ← never purge our own content
  │        .exclude(is_evergreen=True).exclude(views__saved=True)
  ├ delete R2 objects in batches of 100
  └ update media_status="purged", media_purged_at=now, log freed bytes
```

Every purge writes a `ReelPurgeLog` row (`ran_at`, `cutoff`, `reels_purged`,
`bytes_freed`, `triggered_by` — cron or a staff user) so a destructive job is
never invisible. Deleting from R2 costs nothing (Class B ops, free tier).

### Feed impact

A purged reel is excluded from the feed. Users don't see gaps — they see fewer
old reels, which is the intent. The already-covered "user has seen everything"
fallback still applies, and with a 90-day window at 600 reels/month there are
~1,800 reels in rotation at any time, far more than anyone exhausts.

---

## Environment

```
APIFY_TOKEN=                      # unset = the whole scraping side is inert
APIFY_REEL_ACTOR=apify/instagram-reel-scraper
REELS_RATE_PER_1000=2.60          # what Apify charges; drives estimates + the guard
REELS_SCRAPING_ENABLED=           # "True" arms the hourly poll; unset = manual only
REELS_MONTHLY_BUDGET_USD=5.00     # seeds ReelsBudget on first load
REELS_RETENTION_DAYS=0            # media TTL; 0 = keep media forever
REELS_BUDGET_ALERT_PCT=50,80,100  # Telegram staff alert thresholds
```

**R2 needs no new settings.** `core.settings` already wires Cloudflare R2 as
Django's *default storage* — `R2_ACCESS_KEY`, `R2_SECRET_KEY`, `R2_ACCOUNT_ID`,
`R2_BUCKET`, `R2_PUBLIC_DOMAIN`, `R2_LOCATION_PREFIX` — with `django-storages[s3]`
and `boto3` already in `requirements.txt`. Reel media is therefore a plain
`FileField`/`ImageField`: it lands on R2 when those vars are set and on the local
filesystem otherwise, and nothing in `apps.reels` touches boto3 directly. The
only outstanding infra step is pointing `cdn.nemoapps.xyz` at the bucket.

Reconciliation reads Apify's own reported usage through `APIFY_TOKEN`; R2's
side is derived from stored bytes and cross-checked in the Cloudflare dashboard,
so no Cloudflare API token is required.

---

## API

Mirrors the existing DRF style (`apps/books/urls.py` as the shape reference).

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/reels/` | Feed. `?unseen=1` (default) filters out the user's `ReelView` rows; cursor pagination on `-posted_at`; filtered by [language matching](#language-matching). Returns `needs_language_prefs: true` instead of items when the user hasn't been asked yet. |
| `POST` | `/api/reels/<id>/seen/` | Mark seen (idempotent). Sent when a card scrolls past / is opened. |
| `POST` | `/api/reels/<id>/save/` | Toggle `saved`. |
| `GET` | `/api/reels/saved/` | The user's saved reels. |
| `GET` | `/api/reels/sources/` | Sources, for a filter chip row. |
| `POST` | `/api/reels/sources/<id>/fetch/` | **Staff only.** Manual fetch. Returns items found / new / cost. |

Feed query, indexed on `(is_published, language, posted_at)`:

```python
Reel.objects.filter(is_published=True, media_status="stored")
            .filter(target_language__in=user.learning_languages)
            .filter(Q(base_language__in=user.known_languages) | Q(base_language=""))
            .exclude(views__user=user)
            .order_by(F("pin_until").desc(nulls_last=True), "-posted_at")
```

Implemented once in `apps/reels/matching.py` (`feed_for` / `unseen_for`) rather
than inline, so the API, the admin and any future surface can't drift apart on
the rule that decides what a user can actually understand.

`pin_until` first means a pinned own reel leads the feed while its window is
open, then falls back into normal date order — no separate "featured" query.

Once a user has seen everything, fall back to seen reels sorted by `posted_at`
rather than returning an empty feed.

---

## Frontend

- New route `/app/reels` → `pages/Reels.tsx`, inside `AppShell`.
- New nav entry `nav.reels` in `AppShell.tsx` + `i18n/en.json` and `i18n/fa.json`
  (`"reels": "Reels"` / `"ریلز"`), with an inline icon like the existing ones.
  **Note:** the mobile tab bar currently holds 4 items (Home, Decks, Practice,
  Quiz). Adding Reels makes 5 — either accept 5 (tight but workable) or move
  Quiz into the account menu. Decide when building Phase 2.
- Behind the `STAFF` feature flag (`lib/features.ts`) during Phase 2, exactly as
  Books was, then opened to everyone.

**Playback is a plain `<video>` tag** pointed at our own CDN — no Instagram
iframe, no third-party script, and it works regardless of whether Instagram is
reachable:

```html
<video src="https://cdn.nemoapps.xyz/reels/<key>.mp4"
       poster="https://cdn.nemoapps.xyz/reels/<key>.jpg"
       playsinline controls preload="none" />
```

`preload="none"` matters: it's what keeps a scroll through the feed from pulling
6 MB per card on someone's mobile data. Posters load; video bytes only move on
tap.

MVP is a vertical list of cards — poster, source avatar + username, caption
(clamped), duration, and a **link back to the original reel on Instagram** (see
[Risks](#risks); attribution is non-negotiable, even though most users can't
follow the link). Tapping plays inline. Full-screen TikTok-style swiping is
Phase 4 — a UX upgrade, not a prerequisite.

Mark-as-seen fires on play, and on a card being ≥50% visible for 2s.

---

## Admin

Staff tooling lives in **Django admin**, not the React app — it reuses the
existing staff login, gets tables and forms for free, and matches how `BookAdmin`
and the rest of the project already work. A staff-only React page would mean
duplicating auth and spending frontend time on an audience of two.

### The Reels dashboard

One custom admin view at **`/admin/reels/dashboard/`** (registered via
`ModelAdmin.get_urls()` on `ReelSource`, rendering an admin template) is the
single entry point. The per-model admins below stay as the detail/edit views;
the dashboard is what you actually open.

**1 — Money, at the top.** The "what is this costing me" answer, on one screen:

| | This month |
|---|---|
| Apify spend / budget | $3.12 / $5.00 — progress bar |
| Reels billed / new kept | 1,340 / 428 → **$0.0073 per new reel** |
| R2 stored | 12.4 GB → **$0.04/mo** |
| Next purge | in 3 days, ~180 reels / ~1.1 GB |

**2 — Add content.** Two inline forms side by side:

- **Add source** — kind, username, language, level, `results_limit`,
  `poll_interval_hours`, `retention_days`, `permission_granted`.
- **Upload a reel** — video + poster + title + caption + language + level +
  channel + `pin_until`, plus an optional original URL. Serves both
  [our own reels](#our-own-reels) and any hand-picked Instagram reel we want in
  the feed. **Genuinely zero cost — no Apify call is involved.**

  *Implementation note:* an earlier draft listed a separate "add reel by URL"
  action. It was folded into this form, because pasting a URL still can't
  produce a playable video without a scrape — the signed `videoUrl` only ever
  comes from the actor. Uploading the file is the honest zero-cost path. When
  the URL points at a real reel, the form reuses its **shortcode** as the `key`,
  so a later scrape of that account doesn't create a duplicate.

**3 — Sources table.** username · active · permission · last polled · reels
stored · 30-day cost · cost per new reel, with per-row **Fetch now** and
**Deactivate**. The cost-per-new-reel column is the one that tells you which
account's `results_limit` is set too high.

**4 — Reels grid.** Poster thumbnails, newest first, filterable by source /
language / **kind (ours vs Instagram)** / status (`stored`, `purged`, `failed`,
unpublished). Each tile has publish/unpublish, mark-evergreen, pin, and delete.
This is the moderation surface.

**5 — Purge panel.** The requested "delete reels before a date":

> Purge media for reels posted before `[ 2026-03-01 ]` — [Preview]
>
> → *Would purge 1,240 reels, freeing 7.4 GB (~$0.11/mo). Skips 47 of our own
> reels, 38 evergreen and 12 saved. This cannot be undone.* — [Confirm purge]

**Preview is mandatory before confirm.** A one-click irreversible bulk delete on
a page you also use for daily browsing is how a library gets wiped by accident.
The preview runs the exact same queryset as the purge. A second, separately
styled control offers **hard delete** with an explicit warning that re-scraping
those reels will cost money again (see [the trap](#the-trap-deleting-a-reel-makes-us-pay-for-it-again)).

### The Costs page

The dashboard header answers *"what is it costing me right now"*. A second view
at **`/admin/reels/costs/`** answers *"is it under control, and where is the
money going"* — every cost this feature generates, in one place, in Django admin,
with no need to log into Apify or Cloudflare.

**1 — This month.**

| | |
|---|---|
| Apify | **$3.12** / $5.00 budget · 64% · progress bar |
| R2 storage | 12.4 GB-month → **$0.04** |
| R2 egress + ops | **$0.00** (free tier: 0.4% of Class B used) |
| **Total** | **$3.16** |
| **Projected month-end** | **$4.85** — *within budget* |

The projection is a straight run-rate from days elapsed. It is what turns this
page from a report into a control: it tells you a budget breach is coming while
there is still time to lower a `results_limit`.

**2 — Month-by-month history** (last 12 months, from `ReelsCostMonth`):

| Month | Reels billed | New kept | Apify $ | Avg GB | Storage $ | **Total** | **$ / new reel** |
|---|---|---|---|---|---|---|---|
| 2026-08 | 1,340 | 428 | $3.12 | 12.4 | $0.04 | **$3.16** | $0.0074 |
| 2026-07 | 1,860 | 502 | $4.31 | 11.8 | $0.03 | **$4.34** | $0.0086 |

History is stored as rolled-up rows, so it **survives retention purges and row
deletion** — the cost record must outlive the content it paid for.

**3 — Cost by source**, for a selectable period: username · reels billed · new
kept · Apify $ · GB stored · storage $ · **$ per new reel**, sorted by total
descending. This is the page's real job — it names the account that is wasting
money, and links straight to its edit form to fix `results_limit` or
`poll_interval_hours`.

**4 — Budget controls, inline.** `monthly_budget_usd`, `default_results_limit`,
`default_retention_days` are editable on this page. Seeing the overspend and
fixing it should not be two separate journeys.

**5 — Reconciliation.** Our ledger is our own arithmetic and can drift from what
the vendors actually charge. The page shows, side by side:

- our summed `ReelFetchRun.cost_usd` vs **Apify's own reported account usage**
  (pulled from the Apify API), and
- our `sum(video_bytes)` vs **Cloudflare's reported R2 storage**
  (GraphQL analytics API).

A divergence over ~5% is flagged in red. Without this, a silent billing surprise
is possible; with it, the number on the page is trustworthy.

**6 — Alerts, not just a page.** Nobody opens a dashboard daily. Budget
thresholds at **50% / 80% / 100%** fire a staff alert through the existing
Telegram channel (`core.telegram.send_telegram_message`, already used for new
signups and support messages) — one message per threshold per month, no spam.
100% also means the budget guard has already stopped scraping, so the alert
explains an outage rather than merely warning about one.

### Cost bookkeeping

Two small models keep the above honest, and one daily task feeds them:

- **`ReelsStorageSnapshot`** — `day`, `stored_bytes`, `reel_count`. Written
  daily. R2 bills GB-*month*, so the monthly storage figure is the **mean of the
  daily snapshots**, not a reading taken on the last day — otherwise a purge on
  the 29th would make the month look free.
- **`ReelsCostMonth`** — `month`, `reels_billed`, `reels_new`, `apify_usd`,
  `storage_gb_month`, `storage_usd`, `total_usd`. Rolled up daily for the current
  month and frozen at month end. Read-only in admin.

```python
"snapshot-reels-storage": {
    "task": "apps.reels.tasks.snapshot_reels_storage",   # + roll up the month
    "schedule": crontab(hour=3, minute=40),              # daily, after the purge
},
```

Both are cheap: one aggregate query a day.

### Per-model admins

- `ReelSourceAdmin` — `username`, `language`, `is_active`, `permission_granted`,
  `poll_interval_hours`, `results_limit`, `retention_days`, `last_polled_at`,
  reel count, 30-day cost. Actions: *Fetch now*, *Activate*, *Deactivate*.
- `ReelAdmin` — moderation list with poster preview. Filters on source,
  language, `is_published`, `media_status`. Actions: *Publish*, *Unpublish*,
  *Mark evergreen*, *Purge media (keep row)*, *Hard delete*.
- `ReelFetchRunAdmin` — read-only spend ledger: items returned vs new, cost, error.
- `ReelPurgeLogAdmin` — read-only deletion ledger.
- `ReelsCostMonthAdmin` — read-only monthly cost history.
- `ReelsBudgetAdmin` — single row: budget, alert thresholds, default
  `results_limit`, default `retention_days`.

---

## Phases

| Phase | Scope | Spend risk |
|---|---|---|
| **0** ✅ | **Done 2026-08-15** — see [Measured, not modelled](#7-measured-not-modelled--phase-0-results). Rate is $2.07/1k, reels are ~0.10 MB/s, the actor's field names match, and stored MP4s play. Original scope: sign up for Apify Free; run `instagram-reel-scraper` by hand against 3 accounts and confirm multi-username input, the output field names, and the real per-result charge. Then: **(a)** download one `videoUrl` and record the actual MB — the storage model assumes 6 MB; **(b)** check the download works from a Render-like datacenter IP; **(c)** put one MP4 on R2 behind `cdn.nemoapps.xyz` and **test playback from a real Iranian connection**. **(c) is still outstanding and is the one that can still change the architecture.** | ~$0.01 spent |
| **1** | `apps.reels` app: models, migrations, Apify client, R2 ingest, budget guard. **The admin dashboard** — add source, **upload our own reels**, sources table, reels grid, manual *Fetch now*, reel upload, purge panel with preview — and **the Costs page** with spend, projection, per-source breakdown and Telegram budget alerts. No scheduler, no user-facing frontend. Move `nemoapps.xyz` DNS to Cloudflare. | Manual only |
| **2** | API + `/app/reels` page + nav + seen tracking, behind the `STAFF` flag. Seed the feed with our own reels, then register the first ~20 accounts (starting with the ones that granted permission). | Manual only |
| **3** | Enable `.github/workflows/reels-poll.yml` (set the `REELS_SCRAPING_ENABLED` variable and the secrets), budget $5/mo, `REELS_RETENTION_DAYS=90`. Open the feature to all users. | **~$0/mo** |
| **4** | Saved tab, level/topic filters, full-screen swipe player, `ffmpeg` in the image for auto-poster extraction, and — the real prize — *"make cards from this reel"*: an optional deck/`BookLesson` FK on own reels turning watch into one-tap import, plus the Gemini caption pipeline for scraped ones. | Marginal |

---

## Risks

| Risk | Mitigation |
|---|---|
| Runaway Apify spend | `maxTotalChargeUsd` per run + monthly budget guard + kill switch + manual-only Phase 1. |
| Cost creeping up unnoticed | The [Costs page](#the-costs-page) projects month-end spend, and 50/80/100% thresholds fire Telegram alerts — you find out from a message, not from a dashboard you forgot to open. |
| Our ledger drifting from the real vendor bill | The Costs page reconciles our totals against Apify's reported usage and Cloudflare's reported R2 storage, flagging >5% divergence. |
| Paying for reels we already have | `results_limit` tuned per source; `items_returned` vs `items_new` tracked per run so waste is measurable. |
| Storage growing unbounded | The 90-day media TTL pins it flat at ~$0.01/mo regardless of how long we run. |
| **Purge causes us to re-pay for the same reels** | The TTL purges *media*, never rows — the row stays as a dedupe tombstone. Hard delete is manual-only and warns about exactly this. |
| Bulk purge wipes the library by accident | Preview-before-confirm is mandatory on the purge panel; evergreen and user-saved reels are exempt; every purge is logged to `ReelPurgeLog`. |
| Signed IG media URL expires before we download it | Ingest runs in the same job as the fetch, with retries; `media_status` keeps half-ingested reels out of the feed. |
| IG CDN throttles our datacenter IP | Fall back to Apify's per-MB download add-on, or stream IG → R2 from a Cloudflare Worker. Checked in Phase 0. |
| **Cloudflare/R2 unreachable from Iran** | Phase 0 tests this from a real connection *before* the architecture is committed. Fallback: Bunny.net (~$8/mo, different IP footprint) or ArvanCloud. |
| Actor breaks / IG changes | PPE means a broken run costs ~nothing. Swap to `apify/instagram-scraper` — the field mapping is nearly identical. Worst case, [our own reels](#our-own-reels) keep the feature alive. |
| Own reel purged with no way back | The purge job excludes `source.kind="own"` at the query level, not via a toggleable flag. |
| Own reel won't play on iOS | MP4/H.264 + AAC enforced at upload with a clear rejection message, rather than found out on a user's iPhone. |
| User mobile-data cost | `preload="none"`, tap-to-play, no autoplay. This is the user's bill, not ours — treat it as a real constraint. |

### Copyright & ToS — the one that got worse

Re-hosting is **meaningfully more exposure than embedding**, and the plan should
say so plainly rather than bury it. Embedding is a link; a copy on our CDN is a
copy. Since the Iran block rules embedding out, the mitigations have to carry the
weight instead:

- **Public accounts only**, never private ones.
- **Attribution is part of the UI**, not a footnote — creator handle and avatar on
  every card, plus a link to the original reel.
- **Takedown in one click** — `is_published=False` unpublishes and the retention
  job can purge the R2 object. Publish a contact address.
- **Never behind the paywall.** Reels stays on the free tier. The content isn't
  ours to sell, and its business value is retention and daily-open rate, not
  revenue — which is also why $0–30/month is the right budget for it.
- **Ask the creators.** For a launch set of ~20 accounts this is an afternoon of
  DMs. A German-teaching account with a few thousand followers is usually glad to
  be featured in a learning app that links back and credits them. Written
  permission from even half of them turns the biggest risk in this document into
  a partnership — and it's the single highest-value non-engineering task in the
  whole plan. Track consent as a `permission_granted` field on `ReelSource` and
  launch with the accounts that said yes.

---

## Sources

- [Instagram Reel Scraper — Apify](https://apify.com/apify/instagram-reel-scraper)
- [Instagram Scraper — Apify](https://apify.com/apify/instagram-scraper)
- [Apify pricing](https://apify.com/pricing)
- [Actors in Store — pay-per-event & charge limits](https://docs.apify.com/platform/actors/running/actors-in-store)
- [Run Actor API (`maxTotalChargeUsd`)](https://docs.apify.com/api/v2/act-runs-post)
- [Instagram oEmbed — Meta for Developers](https://developers.facebook.com/docs/instagram-platform/oembed/)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [R2 public buckets & custom domains](https://developers.cloudflare.com/r2/buckets/public-buckets/)
- [Cloudflare Stream pricing](https://developers.cloudflare.com/stream/pricing/)
- [Cloudflare ToS — CDN content restrictions moved to service-specific terms](https://blog.cloudflare.com/updated-tos) (video is allowed on the CDN when hosted by R2/Stream/Images)
- [Bunny.net pricing](https://bunny.net/pricing/)
- Instagram blocked in Iran since 2022 and through the 2026 restrictions —
  [TechRadar: ~90% of Iranians use a VPN](https://www.techradar.com/vpn/vpn-privacy-security/nearly-90-percent-of-iranians-now-use-a-vpn-to-bypass-internet-censorship-heres-everything-we-know)
