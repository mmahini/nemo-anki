# Subscription — plan

## Summary

A subscription in **two tiers** — **Basic** and **Pro**. A user either has an
active subscription or not; the tier only changes the **daily AI usage limit**
(both tiers include all features). Each tier has three billing durations, plus a
free trial. Access state is one of `trial`, `active`, or `expired`.

This document is the source of truth for the feature. Phase 1 (below) is what is
built now; Phase 2 is deliberately deferred.

## Pricing & tiers

| Tier  | 1 month | 3 months | 12 months | AI limit / day |
|-------|---------|----------|-----------|----------------|
| Basic | $1.00   | $2.50    | $9.00     | 80             |
| Pro   | $5.00   | $12.50   | $45.00    | 500            |

Plan keys: `basic_monthly` / `basic_quarterly` / `basic_yearly` and
`pro_monthly` / `pro_quarterly` / `pro_yearly` (see `plans.py`).

- **Trial:** every user gets a **7-day** trial starting at signup
  (`trial_end = date_joined + 7 days`).
- Buying a plan sets/extends `current_period_end` and stamps the `tier`. If a
  subscription is still active, a new purchase **stacks** onto the remaining
  time; otherwise it starts from now.

## AI usage limits

To stop abuse and keep Gemini cost below the subscription price, every user has a
**daily AI-action limit** in a fixed 1-day (UTC) window — like an API rate limit.
One "action" = one Gemini-backed request (import parse, enrich, conjugate,
gender-colour, writing prompt/topic/check, conversation reply/text).

| Access level         | AI actions / day |
|----------------------|------------------|
| No sub / expired     | 10               |
| Trial                | 40               |
| Basic                | 80               |
| Pro                  | 500              |
| Staff                | unlimited        |

- Enforced server-side (`AiQuotaMixin` → `consume_ai_quota`) — over the limit
  returns **HTTP 429**. Counters live in `AiUsage(user, day, count)`.
- Usage is shown at the top of the app ("AI used/limit today") via the
  subscription summary. Limits are tunable in `plans.py`.
- Future refinement: weight heavier actions (conversation, batch colour) more
  than a single enrich, or meter by token spend.

## State model

`Subscription` (one per user):

- `trial_end` — end of the 7-day trial.
- `current_period_end` — end of the paid period (null until first purchase).
- `access_until` = latest of (`trial_end`, `current_period_end`).
- **Access is computed live**: a user has access when `now < access_until`.
- `status` (`trial` / `active` / `expired`) is a **cached label** for admin
  listing, recomputed by the admin "Check all subscriptions" button. Live access
  never depends on the button — so there is no need for a cron job yet.

`SubscriptionRequest` records a user's "I've paid" submission (plan + timestamp,
`pending` → `approved`/`rejected`). It is the admin's verification queue.

> Note: the subscription is **informational + purchasable** right now. It does
> not gate any app functionality. Gating (if desired) is a later decision.

## Phase 1 — manual crypto (now)

Payment is a **manual** crypto transfer; there is no payment gateway.

1. User taps **Subscribe** → payment page shows the three plans and pay-by-crypto
   instructions:
   - Network: **BSC (BEP-20)**
   - Wallet: `0x8D15fba1C27DBb1a056aB5245Bd8Eb3471B5CD66`
   - Amount: the chosen plan's USD price (in the equivalent stablecoin/token).
2. After sending, the user taps **"I've paid"** → creates a pending
   `SubscriptionRequest` and shows: *"An admin will verify your payment and
   activate your subscription within 24 hours."*
3. **Admin** (Django admin):
   - Can **activate a subscription** for any user directly (actions:
     Activate monthly / 3 months / yearly).
   - Reviews pending `SubscriptionRequest`s and **Approves** (activates the
     matching plan) or Rejects them.
   - **"Check all subscriptions"** button recomputes every user's `status`
     label (expired vs not) on demand.

No background job checks subscriptions in Phase 1 — the admin button covers it.

## Phase 2 — automated crypto (later, NOT now)

Deferred. When we're ready to remove the manual step:

- Integrate a crypto payment platform / processor (e.g. a hosted checkout or an
  on-chain watcher for the BSC wallet) so a confirmed transfer **auto-activates**
  the subscription — no admin approval.
- Map an incoming on-chain payment to a `SubscriptionRequest` (by amount + a
  per-user memo/reference) and approve it programmatically.
- Add a scheduled job to expire subscriptions and (optionally) send renewal
  reminders, replacing the manual "Check all" button.
- Optionally gate premium features behind `subscription.is_active`.

Until Phase 2 ships, everything in Phase 1 stays manual.
