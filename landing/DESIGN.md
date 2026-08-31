# Nemo Apps — design system

Brand identity for nemoapps.xyz and (optionally) the Nemo family of apps.
The tokens below are the source of truth; `index.html` defines them as CSS
custom properties on `:root`.

## Logo

**The seeker's flask** (`assets/logo.webp`, favicon `assets/favicon.png`).

A drop-shaped alchemist's vessel drawn as a single indigo → teal gradient
line, holding a four-pointed compass star with a coral heart at its center.

**Concept:** exploration + alchemy. The compass star is the seeking — going
out to look for problems worth solving (Saadi: "better to set out across
the desert than to sit idle"); the flask is the transmutation — everyday
needs distilled into apps, effort into social good. The coral dot is the
heart it's all for. Generated with Gemini (`gemini-2.5-flash-image`);
master PNG with transparency at 512×512.

Usage: keep clear space of at least ½ the mark's height around it; don't
recolor, outline, or place on busy backgrounds. Pair with the "Nemo Apps"
wordmark in Manrope ExtraBold (the word "Nemo" may carry the brand gradient).

## Color

| Token          | Value                              | Use                              |
| -------------- | ---------------------------------- | -------------------------------- |
| `--brand`      | `#4c6ef5`                          | primary indigo, links, CTAs      |
| `--brand-dark` | `#3b5bdb`                          | hover/dark end of brand gradient |
| `--teal`       | `#12b886`                          | success, growth, gradient end    |
| `--teal-dark`  | `#0ca678`                          | teal hover                       |
| `--coral`      | `#ff6b52`                          | warmth, impact accents           |
| `--grad-brand` | `linear-gradient(100deg, #4c6ef5, #12b886)` | headline highlights, wordmark |
| `--ink`        | `#1a1f2e`                          | headings/body                    |
| `--ink-soft`   | `#4a5168`                          | secondary text                   |
| `--ink-faint`  | `#8a90a2`                          | captions, footer                 |
| `--bg`         | `#f6f7fb`                          | page background                  |
| `--surface`    | `#ffffff`                          | cards                            |
| `--line`       | `#e6e8ef`                          | hairline borders                 |

Impact tag tint: coral at 16% alpha; Live tag tint: `#1f9d57` at 12% alpha.

## Typography

**Manrope** (Google Fonts), system-ui fallback. The landing is
English-only — no Persian text on the page (the Saadi quote appears in
English translation).

- Display / h1: 800, `clamp(2.1rem, 5.4vw, 3.4rem)`, letter-spacing −0.02em
- h2: 800, `clamp(1.5rem, 3.4vw, 2.1rem)`
- Eyebrow labels: 700, 0.78rem, uppercase, letter-spacing 0.08em
- Body: 400–500, 1rem–1.13rem, line-height 1.55

## Shape & elevation

- Radii: `--radius-s` 13px (chips/icons) · `--radius` 20px (cards) ·
  `--radius-l` 28px (feature panels, hero art) · 999px (pills/buttons)
- Shadows: `--shadow` 0 10px 30px rgba(28,40,80,.08) resting ·
  `--shadow-lift` 0 22px 50px rgba(28,40,80,.14) hover/hero

## Illustration style

Flat vector, full-bleed scenes (no white margins), soft gradients in the
brand palette with warm coral/amber accents, optimistic light, no embedded
text. Card art is 4:3 and object-fit: cover; hero is 16:9. Generated with
Gemini and compressed to WebP (`cwebp -resize 1280 0 -q 82`).

## Motion

Reveal-on-scroll: fade + 22px rise, 0.6s ease, once per element.
Hover: cards lift −4px with `--shadow-lift`; images scale 1.045 over 0.35s.
All motion is disabled under `prefers-reduced-motion: reduce`.
