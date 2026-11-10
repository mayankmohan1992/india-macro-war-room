# Embed a live chart in any page

A single `<div>` and a single `<script>` put one of the tracked indicators into your page — a blog
post, a newsletter's web version, a Notion-exported page, a class handout, a company dashboard.

No API key. No signup. No build step. No dependency. No cookies, no tracking, nothing sent
anywhere except a fetch of static JSON from GitHub Pages.

- **Live demo:** <https://mayankmohan1992.github.io/india-macro-war-room/embed.html>
- **The script:** `https://mayankmohan1992.github.io/india-macro-war-room/embed.js` (≈11 KB, cached)
- **The data:** `https://mayankmohan1992.github.io/india-macro-war-room/api/v1/`

## 30 seconds

```html
<div data-imwr-series="repo" data-imwr-range="10y" data-imwr-height="200"></div>
<script src="https://mayankmohan1992.github.io/india-macro-war-room/embed.js" async></script>
```

That renders the policy repo rate over ten years: the reading, the change since the previous
publication, the axis bounds, the date range, and a credit line naming RBI as the source.

Put the `<script>` **once** per page. Every element carrying `data-imwr-series` renders itself,
including elements added after load if you call `IMWR.render()` (see below).

## Attributes

| attribute | required | default | what it does |
|---|---|---|---|
| `data-imwr-series` | **yes** | — | Indicator id from [`api/v1/index.json`](../api/v1/index.json) — `repo`, `cpi`, `usdinr`, `gsec`, `credit`, … |
| `data-imwr-range` | no | `5y` | `1y`, `3y`, `5y`, `10y` or `all` — measured back from the last observation, not from today |
| `data-imwr-height` | no | `200` | Plot height in CSS pixels. Width always follows the container. |
| `data-imwr-title` | no | the indicator's own label | Overrides the heading, e.g. a headline written for your article |
| `data-imwr-frame` | no | off | `on` draws the hairline card border and padding |

The chart re-renders when its container changes width (via `ResizeObserver`), so it survives sidebars,
flex layouts and orientation changes without any code.

## Series ids

Any id in [`api/v1/index.json`](../api/v1/index.json) works, and the list grows with the dataset.
The common ones:

`cpi` · `cpirural` · `cpiurban` · `wpi` · `wpiprim` · `wpifuel` · `wpimanu` · `repo` · `callmoney` ·
`crr` · `slr` · `m3` · `m1` · `rm` · `notes` · `moneymult` · `liquidity` · `bankdep` · `credit` ·
`nonfood` · `food` · `deposit` · `cdr` · `invest` · `gsec` · `yld91` · `termspread` · `turnover` ·
`cdout` · `cpout` · `fxa` · `fca` · `gold` · `fwd3m` · `usdinr` · `tbill` · `rbicredit` · `rupeesec`

Each id also has a CSV twin (`series/<id>.csv`) if you would rather read the numbers directly.

## Matching your page

The chart follows the reader's light/dark preference automatically. Override any of its colours per
element with CSS custom properties on the `div`:

```html
<div data-imwr-series="credit" data-imwr-range="3y" data-imwr-title="Bank credit growth"
     style="--imwr-accent:#2f6f4f; --imwr-rule:#cfd8d2; --imwr-ink:#14231b; --imwr-muted:#5b6b62"></div>
```

| property | governs |
|---|---|
| `--imwr-ink` | label and value text |
| `--imwr-muted` | axis labels and the credit line |
| `--imwr-rule` | the frame border and the zero line |
| `--imwr-accent` | the line and the last-point dot |
| `--imwr-fill` | the area under the line |

The widget renders inside a shadow root: your page's CSS cannot break it, and it cannot leak styles
back into your page.

## Javascript API

For pages that add content after load (SPAs, infinite scroll, tabs):

```js
// render everything not yet rendered (idempotent)
IMWR.render();

// or one element, with options that override the data-attributes
IMWR.embed(document.getElementById('my-chart'), {
  series: 'cpi', range: 'all', height: 240, title: 'Retail inflation', frame: true
}).then(indicator => console.log(indicator.latest));

// where the data is being read from
console.log(IMWR.base);   // .../api/v1/
```

`embed()` returns a promise that resolves with the indicator payload — the same object as
`api/v1/series/<id>.json` — so you can drive your own UI from it.

## What it will not do

- **It will not interpolate, smooth, extrapolate or pad.** A short series looks short. CPI's official
  y-o-y series begins at the 2024=100 base-year revision, so its chart shows nine points and the
  dashboard explains why; the widget does not invent the rest.
- **It will not hide the credit line.** The dataset is MIT, but the underlying numbers are RBI's and
  the arithmetic is documented. Attribution is part of using it.
- **It does not know about your timezone or session.** No cookies, no localStorage, no analytics, no
  beacon. One GET per chart per page load.
- **It does not silently succeed.** If the data cannot be fetched the widget says so and links to the
  dashboard, in the same footprint — it never renders an empty chart as if the series were missing.

## Self-hosting

The script derives its data root from its own `src`, so a copy works without edits:

```html
<!-- your own mirror: BASE becomes https://example.org/warroom/api/v1/ -->
<script src="https://example.org/warroom/embed.js" async></script>
```

Everything is static: copy `embed.js` and the `api/v1/` tree onto any web server. If you serve the
API from a different origin than `embed.js`, set `IMWR.base` **before** the script renders, or fetch
the JSON yourself and pass it to your own renderer — the payloads are plain and documented in
[API.md](API.md).

## Content Security Policy

If your page sets a CSP, allow:

```
script-src  'self' https://mayankmohan1992.github.io;
connect-src 'self' https://mayankmohan1992.github.io;
```

No `style-src` entry is needed: the widget injects its styles inside its own shadow root.

## Troubleshooting

| symptom | cause |
|---|---|
| nothing renders, console shows `missing data-imwr-series` | the attribute is misspelled or empty |
| `could not load the series (HTTP 404 …)` | the id is not in `index.json` |
| `could not load the series (Failed to fetch)` | CSP `connect-src`, or an offline/page-cache context |
| `only 1 point(s) in range` | the range is narrower than the series' publication interval — widen `data-imwr-range` |
| blank space where the chart should be | the container has zero width (a hidden tab); it paints on the next resize |

## Freshness

The dataset is rebuilt every morning (06:00 UTC) and republished only after the verification gate
passes, so the chart is never staler than the last good refresh. The exact timestamp is in
[`api/v1/status.json`](../api/v1/status.json) (`retrieved_at`), and each chart prints its own as-of
date under the plot.
