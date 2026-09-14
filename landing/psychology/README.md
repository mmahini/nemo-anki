# `/psychology` — private, unlisted practice & test section

## ⛔ The one rule: never link to this from the landing

**FA —** این بخش عمداً پنهان و «لینک‌نشده» است. هیچ لینکی، هیچ آیتمی در منو، هیچ
اشاره‌ای در فوتر یا متن، و هیچ ردی در متادیتای لندینگ اصلی `nemowise.com`
نباید به این قسمت اضافه شود. تنها راه دسترسی، داشتن آدرس مستقیم است:
`https://nemowise.com/psychology/`
اگر در آینده کسی (یا دستیار هوش مصنوعی‌ای) خواست سایت را به‌روز کند، این قانون
سر جای خودش باقی است: **این بخش در لندینگ دیده نمی‌شود.**

**EN —** This section is intentionally hidden and unlisted. Do **not** add a link to
it, a nav item, a footer entry, a sentence mentioning it, or any trace of it in the
metadata of the main `nemowise.com` landing. The only way in is the direct URL:
`https://nemowise.com/psychology/`

Concretely, this means **no** references to `/psychology` in:

- `landing/index.html` — header nav, hero, any section, the footer
- `landing/about.html`, `landing/impressum.html`, `landing/datenschutz.html`
- any sitemap, OG/canonical metadata, or `vercel.json` redirect

If a future change needs to surface these tests publicly, that is a deliberate
product decision — raise it first, don't do it as a side effect of another task.

### How the "unlisted" property is enforced

| Layer | Where |
| --- | --- |
| No inbound links | nothing on the landing points here (the rule above) |
| `noindex, nofollow, noarchive, nosnippet` | `<meta name="robots">` on every page in this folder |
| Crawler exclusion | `Disallow: /psychology/` in `landing/robots.txt` |

Note that "unlisted" is *obscurity*, not authentication. Anyone who receives the
URL can open it and can pass it on. Don't put anything here that would be harmful
if it leaked. There is no login, and none is planned.

## What's in here

```
psychology/
├── README.md                  ← this file
├── index.html                 ← hub: the list of available tests (fa, RTL)
├── fonts/                     ← Vazirmatn woff2 subsets, shared by all pages
└── pearson-archetype/
    ├── index.html             ← the test itself
    ├── dc-runtime.js          ← template/rendering runtime the test is built on
    ├── react.js               ← React 18.3.1 UMD (self-hosted, no CDN)
    └── react-dom.js           ← ReactDOM 18.3.1 UMD (self-hosted, no CDN)
```

### Test 1 — Pearson 12-archetype questionnaire

`pearson-archetype/` — پرسش‌نامهٔ «اِی»، شاخص اسطورهٔ قهرمانی (Heroic Myth Index)
by Carol S. Pearson. 72 statements, scores 12 archetypes, plots them on a radar
chart and positions the taker on six archetypal dualities.

Source: an offline single-file bundle
(`آزمون-آرکتایپی-پیرسن-آفلاین.html`) that was unpacked into plain static files —
the base64 manifest, the gzip step and the "Unpacking…" loader are gone, so the
page just loads. The Google-Fonts CDN and unpkg references were replaced with
self-hosted copies, which keeps the page GDPR-clean and working offline, in line
with the rest of the site.

Answers live in `localStorage` under `pearson-hai-answers-v1`. Nothing is sent to
a server; there is no backend behind this section at all.

## Adding another test

1. Create `psychology/<slug>/index.html`.
2. Put `<meta name="robots" content="noindex, nofollow, noarchive, nosnippet">` in
   its `<head>` and reference the shared fonts at `../fonts/`.
3. Add a `<a class="card">` entry for it in `psychology/index.html`.
4. Keep everything self-hosted — no CDN, no external fetches.
5. Do not touch the landing. See the rule at the top.
