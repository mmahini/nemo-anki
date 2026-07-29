# Subscription — plan

## Summary

A single-tier subscription: a user either **has an active subscription or not**.
There are no feature levels — just three billing durations at different prices,
plus a free trial. Access state is one of `trial`, `active`, or `expired`.

This document is the source of truth for the feature. Phase 1 (below) is what is
built now; Phase 2 is deliberately deferred.

## Pricing

| Plan        | Price  | Duration |
|-------------|--------|----------|
| `monthly`   | $1.00  | 30 days  |
| `quarterly` | $2.50  | 90 days  |
| `yearly`    | $9.00  | 365 days |

- **Trial:** every user gets a **7-day** trial starting at signup
  (`trial_end = date_joined + 7 days`).
- Buying a plan sets/extends `current_period_end`. If a subscription is still
  active, a new purchase **stacks** onto the remaining time; otherwise it starts
  from now.

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
