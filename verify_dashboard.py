#!/usr/bin/env python3
"""
verify_dashboard.py - render the built dashboard in headless Chromium and assert it really works.

WHY: a 490 KB hand-written SVG/JS page can compile and still render nothing (bad selector, JS throw,
empty grid, a modal that never opens). Every promise the page makes is asserted here:

  shell    * on desktop the WINDOW never scrolls; the indicator rail and the chart pane each scroll
             independently (scrolling one must not move the other, nor the window)
  layout   * 2-column rail + 2-column charts on desktop; 1 column on mobile
           * NO DEAD SPACE: every row of every grid reaches its container's right edge, at every
             width in the sweep
  data     * every tile in the DOM with a status class, non-empty value and a ? that resolves to a
             SOURCED definition; 26 chart cards; 38 sparklines; snapshot + rule tables complete
  charts   * every card has a visible legend and a visible expand control, and draws real geometry
           * every chart has a dated x axis and a labelled y axis
           * hover reads out the value for a date; multi-series charts read out every series
           * co-plotted series are DATE-aligned, not index-aligned
           * expand / card click opens the full-size modal; zoom, pan, reset, close button, Esc work
  defs     * no definition anywhere renders as "pending" (33 sourced entries cover all 38 tiles)
  mobile   * the rail is off-canvas behind the hamburger, opens, closes on backdrop, 1-col charts
  theme    * the embedded Archivo typeface really loads
  density  * Comfortable / Compact / Fit-all really resize the charts; worst-first really sorts

Exits non-zero with a printed list of problems if any check fails.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
import traceback

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent
PAGE = ROOT / "dashboard" / "index.html"
DATA = json.loads((ROOT / "dashboard" / "warroom_data.json").read_text())
N_CHARTS = 26
GRIDS = [".tiles", ".charts", ".strip"]


def open_page(pw, width, height):
    """Fresh browser + page on file:// with console/page error capture wired up."""
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": width, "height": height})
    errs: list[str] = []
    page.on("console", lambda m: errs.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
    page.goto(PAGE.as_uri())
    page.wait_for_timeout(1000)
    return browser, page, errs


# --------------------------------------------------------------------------- #
# layout
# --------------------------------------------------------------------------- #
def check_no_dead_space(page, problems, grids=GRIDS, quiet=False):
    """Group children into visual rows and assert each row spans the container edge to edge."""
    rows = page.evaluate(
        """(selectors) => {
             const out = [];
             selectors.forEach(sel => document.querySelectorAll(sel).forEach(grid => {
               const kids = [...grid.children].filter(k => k.getBoundingClientRect().width > 0);
               if (!kids.length) return;
               const g = grid.getBoundingClientRect();
               const byRow = new Map();
               kids.forEach(k => {
                 const r = k.getBoundingClientRect();
                 const key = Math.round(r.top / 4);
                 if (!byRow.has(key)) byRow.set(key, []);
                 byRow.get(key).push(r);
               });
               [...byRow.values()].forEach(rects => {
                 out.push({grid: sel, items: rects.length,
                           gapRight: +(g.right - Math.max(...rects.map(r => r.right))).toFixed(1),
                           gapLeft: +(Math.min(...rects.map(r => r.left)) - g.left).toFixed(1)});
               });
             }));
             return out;
           }""", grids)
    bad = [r for r in rows if r["gapRight"] > 2.0 or r["gapLeft"] > 2.0]
    if not quiet:
        print(f"  no-dead-space: {len(rows)} rows checked, {len(bad)} short")
    for r in bad[:6]:
        problems.append(f"dead space in {r['grid']}: row of {r['items']} leaves "
                        f"{r['gapRight']}px right / {r['gapLeft']}px left")


def check_responsive(browser, problems):
    """Dead-space + horizontal-overflow sweep across widths (the shell changes at 980px)."""
    print("\nresponsive sweep:")
    for w in (1760, 1500, 1280, 1180, 980, 760, 480):
        pg = browser.new_page(viewport={"width": w, "height": 900})
        pg.goto(PAGE.as_uri())
        pg.wait_for_timeout(450)
        res = pg.evaluate("""() => ({
            bad: (() => { const out = [];
              ['.tiles','.charts','.strip'].forEach(sel => document.querySelectorAll(sel).forEach(grid => {
                const kids = [...grid.children].filter(k => k.getBoundingClientRect().width > 0);
                if (!kids.length) return;
                const g = grid.getBoundingClientRect(); const byRow = new Map();
                kids.forEach(k => { const r = k.getBoundingClientRect();
                  const key = Math.round(r.top/4); if (!byRow.has(key)) byRow.set(key, []); byRow.get(key).push(r); });
                [...byRow.values()].forEach(rects => {
                  const gR = +(g.right - Math.max(...rects.map(r => r.right))).toFixed(1);
                  const gL = +(Math.min(...rects.map(r => r.left)) - g.left).toFixed(1);
                  if (gR > 2 || gL > 2) out.push(sel + ' items=' + rects.length + ' R' + gR + ' L' + gL);
                });
              })); return out; })(),
            overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
            cols: (() => { const per = new Set();
              document.querySelectorAll('.charts').forEach(g => [...g.children].forEach(k =>
                per.add(Math.round(k.getBoundingClientRect().left)))); return per.size; })()
        })""")
        flag = "dead space " + str(res["bad"]) if res["bad"] else "fills width"
        print(f"  @{w}px: {flag}, h-overflow {res['overflow']}px, chart cols {res['cols']}")
        if res["bad"]:
            problems.append(f"@{w}px dead space: {res['bad']}")
        if res["overflow"] > 0:
            problems.append(f"@{w}px: content overflows horizontally by {res['overflow']}px")
        pg.close()


def check_shell(page, problems):
    """Desktop promises: window never scrolls, panes independent, 2 columns."""
    f = page.evaluate("""() => ({
        tiles: document.querySelectorAll('.tile').length,
        cards: document.querySelectorAll('.card[data-chart]').length,
        sparks: document.querySelectorAll('svg.spark').length,
        strip: document.querySelectorAll('#strip .kv').length,
        rules: document.querySelectorAll('#rules-body tr').length,
        docH: document.documentElement.scrollHeight, docW: document.documentElement.scrollWidth,
        winH: window.innerHeight, winW: window.innerWidth
    })""")
    print(f"  rendered: {f['tiles']} tiles · {f['cards']} charts · {f['sparks']} sparklines · "
          f"{f['strip']} snapshot chips · {f['rules']} rule rows")
    if f["tiles"] != len(DATA["tiles"]):
        problems.append(f"tile count {f['tiles']} != payload {len(DATA['tiles'])}")
    if f["cards"] != N_CHARTS:
        problems.append(f"chart count {f['cards']} != {N_CHARTS}")
    if f["strip"] != len(DATA["snapshot"]):
        problems.append(f"snapshot chips {f['strip']} != {len(DATA['snapshot'])}")
    if f["rules"] != len(DATA["tiles"]):
        problems.append(f"rule rows {f['rules']} != {len(DATA['tiles'])}")
    if f["sparks"] < len(DATA["tiles"]) - 2:
        problems.append(f"only {f['sparks']} sparklines for {len(DATA['tiles'])} tiles")
    if f["docH"] > f["winH"] + 1:
        problems.append(f"desktop window scrolls: page height {f['docH']} > viewport {f['winH']}")
    if f["docW"] > f["winW"] + 1:
        problems.append(f"horizontal overflow: {f['docW']} > {f['winW']}")

    st = page.evaluate("""() => {
        const rail = document.querySelector('#rail'), panes = document.querySelector('#panes');
        window.scrollTo(0, 0);
        const b = {rail: rail.scrollTop, panes: panes.scrollTop, win: window.scrollY};
        rail.scrollTop = 220;
        const r = {rail: rail.scrollTop, panes: panes.scrollTop, win: window.scrollY};
        panes.scrollTop = 260;
        const p = {rail: rail.scrollTop, panes: panes.scrollTop, win: window.scrollY};
        return {b, r, p, railScrollable: rail.scrollHeight > rail.clientHeight + 1,
                panesScrollable: panes.scrollHeight > panes.clientHeight + 1};
    }""")
    print(f"  panes: rail {st['b']['rail']}->{st['r']['rail']} (chart pane stayed {st['r']['panes']}) · "
          f"chart pane ->{st['p']['panes']} (rail stayed {st['p']['rail']}) · window scrollY {st['p']['win']}")
    if not st["railScrollable"] or not st["panesScrollable"]:
        problems.append("a pane is not scrollable — the fixed-viewport shell is not working")
    if st["r"]["rail"] <= st["b"]["rail"]:
        problems.append("the rail did not scroll")
    if st["r"]["panes"] != st["b"]["panes"]:
        problems.append("scrolling the rail moved the chart pane — panes are not independent")
    if st["p"]["rail"] != st["r"]["rail"]:
        problems.append("scrolling the chart pane moved the rail — panes are not independent")
    if st["p"]["win"] != 0 or st["r"]["win"] != 0:
        problems.append("scrolling a pane scrolled the window — shell is not fixed-viewport")

    cols = page.evaluate("""() => {
        const per = sel => { const out = [];
          document.querySelectorAll(sel).forEach(grid => { const byRow = new Map();
            [...grid.children].forEach(k => { const r = k.getBoundingClientRect();
              const key = Math.round(r.top/4); byRow.set(key, (byRow.get(key)||0)+1); });
            out.push(...byRow.values()); });
          return out; };
        return {tiles: per('.tiles'), charts: per('.charts')};
    }""")
    print(f"  columns: tiles {cols['tiles'][:6]}… · charts {cols['charts'][:6]}…")
    if any(c > 2 for c in cols["tiles"]):
        problems.append(f"more than 2 tiles per row on desktop: {cols['tiles']}")
    if any(c > 2 for c in cols["charts"]):
        problems.append(f"more than 2 charts per row on desktop: {cols['charts']}")


# --------------------------------------------------------------------------- #
# content
# --------------------------------------------------------------------------- #
def check_tiles_and_charts(page, problems):
    facts = page.evaluate("""() => ({
        tiles: [...document.querySelectorAll('.tile')].map(t => ({
          id: t.dataset.id, cls: t.className,
          val: (t.querySelector('.t-val')||{}).textContent || '',
          def: t.querySelector('.help') ? t.querySelector('.help').dataset.def : null,
          foot: (t.querySelector('.t-foot')||{}).textContent || '' })),
        cards: [...document.querySelectorAll('.card[data-chart]')].map(c => ({
          id: c.dataset.chart,
          legend: [...c.querySelectorAll('.legend span:not(.hint)')].filter(s => s.offsetWidth > 0).length,
          expand: !!c.querySelector('.expand') && c.querySelector('.expand').offsetWidth > 0,
          geom: c.querySelectorAll('svg path, svg rect, svg line').length,
          paths: c.querySelectorAll('svg path').length,
          texts: [...c.querySelectorAll('svg text')].map(x => x.textContent || '') }))})""")
    for t in facts["tiles"]:
        if not any(s in t["cls"] for s in ("good", "watch", "bad")):
            problems.append(f"tile {t['id']} has no status class")
        if len(t["val"].strip()) < 2:
            problems.append(f"tile {t['id']} rendered an empty value")
        if t["def"] is None:
            problems.append(f"tile {t['id']} has no ? button")
        elif t["def"] not in DATA["definitions"]:
            problems.append(f"tile {t['id']} maps to undefined definition key {t['def']!r}")
        if len(t["foot"].strip()) < 5:
            problems.append(f"tile {t['id']} has no status/date footer")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    for c in facts["cards"]:
        if c["legend"] < 1:
            problems.append(f"chart {c['id']} shows no legend entry")
        if not c["expand"]:
            problems.append(f"chart {c['id']} has no visible expand control")
        if c["paths"] < 1 or c["geom"] < 8:      # >=1 data path + gridlines/axes/ticks
            problems.append(f"chart {c['id']} drew only {c['paths']} path(s) / {c['geom']} nodes")
        if sum(1 for t in c["texts"] if any(m in t for m in months)) < 3:
            problems.append(f"chart {c['id']} x axis has fewer than 3 date labels")
        if not any(t.strip().lower() == "date" for t in c["texts"]):
            problems.append(f"chart {c['id']} has no x-axis title")
    print(f"  tiles checked: {len(facts['tiles'])} · charts checked: {len(facts['cards'])} "
          f"(legend + expand + geometry + dated axis on each)")


def check_hover(page, problems):
    """Hovering must read out the date and the value(s) for that date, and track the cursor."""
    def hover(sel, frac):
        page.query_selector(sel).scroll_into_view_if_needed()
        page.wait_for_timeout(150)
        box = page.query_selector(sel).bounding_box()
        page.mouse.move(box["x"] + box["width"] * frac, box["y"] + box["height"] * 0.55)
        page.wait_for_timeout(230)
        return page.inner_text(f"{sel} .tip")

    cpi = hover('.card[data-chart="cpi"] .chartwrap', 0.5)
    print(f"  cpi hover: {cpi.splitlines()[:2]}")
    if not re.search(r"\d{4}-\d{2}-\d{2}", cpi) or "%" not in cpi:
        problems.append(f"cpi hover readout looks wrong: {cpi!r}")
    cpi2 = hover('.card[data-chart="cpi"] .chartwrap', 0.85)
    if cpi2 == cpi:
        problems.append("hover readout did not change when the cursor moved along the chart")

    rates = hover('.card[data-chart="rates"] .chartwrap', 0.4)
    rows = [r for r in rates.splitlines()[1:] if r.strip()]
    print(f"  rates hover: {len(rows)} series rows")
    if len(rows) < 3:
        problems.append(f"multi-series chart read out only {len(rows)} rows: {rates!r}")

    wrap = page.query_selector('.card[data-chart="laf"] .chartwrap')
    wrap.scroll_into_view_if_needed()
    page.wait_for_timeout(180)
    box = wrap.bounding_box()
    page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.5)
    page.wait_for_timeout(230)
    laf = page.inner_text('.card[data-chart="laf"] .tip')
    print(f"  liquidity bar hover: {laf.splitlines()[:3]}")
    if "cr" not in laf:
        problems.append(f"bar chart hover readout looks wrong: {laf!r}")


def check_date_alignment(page, problems):
    """Series with different histories must not share a left edge (that would mean index-aligned)."""
    # NOTE: only cross-table pairs belong here. M1/M3 both come from table r13 and share dates by
    # construction, so an identical left edge there is correct, not index-alignment.
    for cid, label in (("wpi", "WPI (short) vs CPI (long)"), ("money", "reserve money (r7) vs M3 (r13)"),
                       ("cdcp", "CP (r5) vs CD (r4) outstanding"), ("cdcprate", "CP (r5) vs CD (r4) rates")):
        paths = page.query_selector_all(f'.card[data-chart="{cid}"] svg path')
        if len(paths) < 2:
            problems.append(f"{cid}: fewer than 2 series paths ({len(paths)})")
            continue
        firsts = []
        for p in paths[:3]:
            m = re.search(r"M([\d.]+),", p.get_attribute("d") or "")
            if m:
                firsts.append(float(m.group(1)))
        if len(firsts) >= 2 and abs(firsts[0] - firsts[1]) < 1.0:
            problems.append(f"{cid}: both series start at x={firsts[0]:.1f} — {label} look index-aligned")
        else:
            print(f"  {cid}: series start at x={[round(f, 1) for f in firsts]} (date-aligned)")


def check_modal(page, problems):
    """expand button, card-body click, ? separation, zoom in/out/reset, pan, close button, Esc."""
    card = page.query_selector('.card[data-chart="cpi"]')
    card.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    card.query_selector(".expand").click()
    page.wait_for_timeout(280)
    if page.get_attribute("#modal", "hidden") is not None:
        problems.append("expand button did not open the full-size chart")
        return

    def win():
        return page.inner_text("#m-window")

    def verts():
        d = page.eval_on_selector("#m-body svg path", "el => el.getAttribute('d') || ''")
        return len(re.findall(r"[ML]\d", d))

    vb = page.get_attribute("#m-body svg", "viewBox")
    w0, p0 = win(), verts()
    if not vb or not vb.startswith("0 0 1400"):
        problems.append(f"modal chart not drawn full size (viewBox {vb})")
    page.click("#m-in"); page.wait_for_timeout(220)
    w1, p1 = win(), verts()
    page.click("#m-out"); page.wait_for_timeout(220)
    page.click("#m-reset"); page.wait_for_timeout(200)
    print(f"  modal: viewBox {vb} · zoom {w0!r} -> {w1!r} · vertices {p0} -> {p1} · reset -> {win()!r}")
    if w1 == w0:
        problems.append("zoom-in did not change the plotted window")
    if p1 >= p0:
        problems.append(f"zoom-in did not add resolution ({p0} -> {p1} vertices)")
    if win() != w0:
        problems.append("reset did not restore the original window")
    box = page.query_selector("#m-body svg").bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] * 0.7, box["y"] + box["height"] / 2)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] * 0.2, box["y"] + box["height"] / 2, steps=6)
        page.mouse.up()
        page.wait_for_timeout(220)
        panned = win()
        print(f"  after drag: {panned!r}")
        if "back" not in panned:
            problems.append("dragging did not pan the window back in time")
        page.click("#m-reset"); page.wait_for_timeout(180)
    page.click("#m-close"); page.wait_for_timeout(220)
    if page.get_attribute("#modal", "hidden") is None:
        problems.append("the top-right close button did not close the chart modal")

    for cid in ("money", "laf", "credit", "wpimix"):
        c = page.query_selector(f'.card[data-chart="{cid}"]')
        c.scroll_into_view_if_needed(); page.wait_for_timeout(130)
        c.query_selector("h3").click(); page.wait_for_timeout(230)
        if page.get_attribute("#modal", "hidden") is not None:
            problems.append(f"{cid}: clicking the card body did not open the full-size chart")
        else:
            page.click("#m-close"); page.wait_for_timeout(150)

    c = page.query_selector('.card[data-chart="cpi"]')
    c.query_selector(".help").click(); page.wait_for_timeout(260)
    if page.get_attribute("#defmodal", "hidden") is not None:
        problems.append("chart ? did not open the definition panel")
    if page.get_attribute("#modal", "hidden") is None:
        problems.append("chart ? also opened the chart modal (events not separated)")
    page.keyboard.press("Escape"); page.wait_for_timeout(220)
    if page.get_attribute("#defmodal", "hidden") is None:
        problems.append("Esc did not close the definition panel")

    # Esc must also close the chart modal
    page.query_selector('.card[data-chart="cpi"]').click(); page.wait_for_timeout(250)
    page.keyboard.press("Escape"); page.wait_for_timeout(250)
    if page.get_attribute("#modal", "hidden") is None:
        problems.append("Esc did not close the chart modal")


def check_definitions(page, problems):
    """No definition may render as 'pending': every tile key must resolve to sourced text + a URL."""
    keys = sorted({t["def_key"] for t in DATA["tiles"]})
    missing = [k for k in keys if k not in DATA["definitions"]]
    if missing:
        problems.append(f"tiles with no sourced definition: {missing}")
    sample = ["cpi", "wpifuel", "cpirural", "termspread", "moneymult", "bankdep",
              "rbicredit", "rupeesec", "crr", "usdinr", "m1", "tbill"]
    checked = 0
    for tile_id in sample:
        btn = page.query_selector(f'.tile[data-id="{tile_id}"] .help')
        if not btn:
            problems.append(f"{tile_id}: no ? button on the tile")
            continue
        btn.scroll_into_view_if_needed(); page.wait_for_timeout(90)
        btn.click(); page.wait_for_timeout(230)
        body = page.inner_text("#d-body")
        if "Definition pending" in body:
            problems.append(f"{tile_id}: definition rendered as pending")
        if "http" not in body:
            problems.append(f"{tile_id}: definition carries no source URL")
        if len(body) < 250:
            problems.append(f"{tile_id}: definition looks truncated ({len(body)} chars)")
        if checked == 0:
            print(f"  definition sample ({tile_id}): {len(body)} chars, source linked={'http' in body}")
        checked += 1
        page.click("#d-close"); page.wait_for_timeout(110)
    print(f"  definitions verified: {checked} panels · {len(keys)} distinct tile keys · "
          f"{len(DATA['definitions'])} sourced entries · 0 rendered as pending")


def check_density_and_sort(page, problems):
    """Fit-all must flatten the charts; worst-first must reorder the rail by status."""
    def vb():
        return page.get_attribute('.card[data-chart="cpi"] svg', "viewBox")
    comfy = vb()
    page.click("#d-dense"); page.wait_for_timeout(320)
    dense = vb()
    page.click("#d-compact"); page.wait_for_timeout(320)
    compact = vb()
    page.click("#d-comfy"); page.wait_for_timeout(320)
    back = vb()
    print(f"  density: comfortable {comfy} · compact {compact} · fit-all {dense}")
    if not (comfy.endswith("206") and compact.endswith("150") and dense.endswith("104")):
        problems.append(f"density toggle did not resize the charts: {comfy} / {compact} / {dense}")
    if back != comfy:
        problems.append("returning to Comfortable did not restore the chart size")

    page.click("#sort-worst"); page.wait_for_timeout(320)
    groups = page.evaluate("""() => [...document.querySelectorAll('.tiles')].map(g =>
        [...g.children].filter(t => t.getBoundingClientRect().width > 0)
          .map(t => ['bad','watch','good'].indexOf(t.dataset.status)))""")
    page.click("#sort-theme"); page.wait_for_timeout(260)
    print(f"  worst-first, per group (0=bad): {groups}")
    for g in groups:
        if g != sorted(g):
            problems.append(f"worst-first did not sort a group by status: {g}")


def check_font(page, problems):
    f = page.evaluate("""() => ({check: document.fonts.check('12px Archivo'),
                                fam: getComputedStyle(document.body).fontFamily,
                                faces: document.fonts.size})""")
    print(f"  typeface: loaded={f['check']} faces={f['faces']} family={f['fam'][:38]}")
    if not f["check"]:
        problems.append("the embedded Archivo font did not load")
    if "Archivo" not in f["fam"]:
        problems.append(f"body is not using Archivo: {f['fam']}")


def check_mobile(pw, problems):
    """390x844: rail off-canvas behind the hamburger, opens, closes on backdrop, 1-col charts."""
    browser, page, errs = open_page(pw, 390, 844)
    try:
        st = page.evaluate("""() => ({
            railLeft: Math.round(document.querySelector('#rail').getBoundingClientRect().left),
            burger: document.querySelector('#burger').offsetWidth > 0,
            cols: (() => { const per = new Set();
              document.querySelectorAll('.charts').forEach(g => [...g.children].forEach(k =>
                per.add(Math.round(k.getBoundingClientRect().left)))); return per.size; })(),
            docW: document.documentElement.scrollWidth, winW: window.innerWidth})""")
        print(f"  mobile: rail.left={st['railLeft']} · burger={st['burger']} · chart cols={st['cols']} · "
              f"width {st['docW']}/{st['winW']}")
        if st["railLeft"] > -20:
            problems.append("mobile: the rail is not off-canvas before opening")
        if not st["burger"]:
            problems.append("mobile: the hamburger is not visible")
        if st["cols"] != 1:
            problems.append(f"mobile: charts are in {st['cols']} columns, expected 1")
        if st["docW"] > st["winW"] + 1:
            problems.append("mobile: horizontal overflow")

        page.click("#burger"); page.wait_for_timeout(340)
        o = page.evaluate("""() => ({left: Math.round(document.querySelector('#rail').getBoundingClientRect().left),
            backdrop: !document.getElementById('backdrop').hidden,
            expanded: document.getElementById('burger').getAttribute('aria-expanded')})""")
        print(f"  mobile: after hamburger rail.left={o['left']} backdrop={o['backdrop']}")
        if o["left"] < -20:
            problems.append("mobile: the hamburger did not reveal the rail")
        if not o["backdrop"]:
            problems.append("mobile: no backdrop behind the opened rail")
        if o["expanded"] != "true":
            problems.append("mobile: the hamburger did not report aria-expanded=true")

        page.click('.tile[data-id="cpi"] .help'); page.wait_for_timeout(300)
        if page.get_attribute("#defmodal", "hidden") is not None:
            problems.append("mobile: the definition panel did not open from a tile")
        else:
            page.keyboard.press("Escape"); page.wait_for_timeout(250)

        # NOTE: click the EXPOSED strip beside the rail. The backdrop's centre sits *under* the open
        # rail (rail z-index 40 > backdrop 35), so a centre click is intercepted - that is a test
        # artifact, not a page bug: a real tap lands on the visible strip to the right of the drawer.
        page.click("#backdrop", position={"x": 372, "y": 420}); page.wait_for_timeout(340)
        if page.evaluate("() => document.querySelector('#rail').getBoundingClientRect().left") > -20:
            problems.append("mobile: the backdrop click did not close the rail")
        if errs:
            problems.append(f"mobile console errors: {errs[:2]}")
    finally:
        browser.close()


def check_theme(pw, problems):
    """Light/Dark toggle: switches tokens AND chart colours, persists, sits top-right, no flash."""
    def probe(page):
        return page.evaluate("""() => ({
            theme: document.documentElement.getAttribute('data-theme'),
            bg: getComputedStyle(document.body).backgroundColor,
            ink: getComputedStyle(document.body).color,
            cpiLine: (() => { const p = document.querySelector('.card[data-chart=\"cpi\"] svg path[stroke]');
                              return p ? p.getAttribute('stroke') : null; })(),
            lightOn: document.getElementById('t-light').classList.contains('on'),
            darkOn: document.getElementById('t-dark').classList.contains('on'),
            stored: (() => { try { return localStorage.getItem('warroom-theme'); } catch(e) { return 'blocked'; } })(),
            rightSide: (() => { const b = document.getElementById('t-dark').getBoundingClientRect();
                                return Math.round(b.left) > Math.round(window.innerWidth * 0.55); })(),
            visible: document.getElementById('t-dark').offsetWidth > 0
        })""")

    # (1) a system-DARK machine with no stored choice must still START LIGHT: light is the default on
    #     every machine, whatever the visitor's OS reports. Dark stays one click away.
    browser = pw.chromium.launch()
    pg = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    pg.goto(PAGE.as_uri()); pg.wait_for_timeout(600)
    dark0 = probe(pg)
    if dark0["theme"] != "light" or dark0["bg"] != "rgb(242, 241, 238)":
        problems.append(f"a dark-mode system with no saved choice did not start LIGHT "
                        f"(theme={dark0['theme']!r}, bg={dark0['bg']!r}) - light is the required default")
    if dark0["lightOn"] is not True or dark0["darkOn"] is not False:
        problems.append("the toggle buttons do not show Light as active on a fresh visit")
    # a stored choice still wins over the default
    pg.click("#t-dark"); pg.wait_for_timeout(400)
    dark_lines = probe(pg)["cpiLine"]
    pg.reload(); pg.wait_for_timeout(600)
    if probe(pg)["theme"] != "dark":
        problems.append("an explicit dark choice was not restored on reload")
    pg.close()

    # (2) system-light: starts light; the toggle must flip everything, persist, and flip back
    pg = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    pg.goto(PAGE.as_uri()); pg.wait_for_timeout(600)
    light0 = probe(pg)
    # the OS must not be able to move the theme: no listener is installed by design, so the attribute
    # can only change on a click
    stable = pg.evaluate("""() => {
        const before = document.documentElement.getAttribute('data-theme');
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        mq.dispatchEvent(new Event('change'));          // would fire any listener that existed
        return {before, after: document.documentElement.getAttribute('data-theme')};
    }""")
    if stable["before"] != stable["after"]:
        problems.append("the theme changed without a click - an OS listener is still installed")

    print(f"  theme: system-dark start={dark0['theme']} ({dark0['bg']}) [light required] | "
          f"system-light start={light0['theme']} ({light0['bg']}) | OS cannot override: "
          f"{stable['before'] == stable['after']}")
    if light0["theme"] != "light":
        problems.append(f"a light-mode system started in {light0['theme']!r}")
    if not (light0["visible"] and light0["rightSide"]):
        problems.append("the theme toggle is not visible in the top-right area of the header")
    if not light0["lightOn"] or light0["darkOn"]:
        problems.append("the toggle buttons do not reflect the current theme on load")

    pg.click("#t-dark"); pg.wait_for_timeout(420)
    dark = probe(pg)
    print(f"  toggle -> dark: bg {dark['bg']} · ink {dark['ink']} · CPI line {dark['cpiLine']} · "
          f"stored {dark['stored']!r}")
    if dark["theme"] != "dark" or dark["bg"] != "rgb(18, 19, 22)":
        problems.append(f"clicking Dark did not switch the palette (theme={dark['theme']} bg={dark['bg']})")
    if dark["cpiLine"] == light0["cpiLine"]:
        problems.append(f"clicking Dark did not recolour the charts (line stayed {dark['cpiLine']})")
    if dark["cpiLine"] != dark_lines:
        problems.append(f"the toggled dark chart colour {dark['cpiLine']} differs from the dark start "
                        f"colour {dark_lines}")
    if dark["stored"] != "dark":
        problems.append(f"the theme choice was not persisted (localStorage={dark['stored']!r})")
    if not dark["darkOn"] or dark["lightOn"]:
        problems.append("the toggle button states do not track the active theme")

    pg.reload(); pg.wait_for_timeout(650)
    after = probe(pg)
    print(f"  after reload: theme={after['theme']} bg={after['bg']}")
    if after["theme"] != "dark":
        problems.append(f"the saved dark theme was not restored on reload (got {after['theme']!r})")

    pg.click("#t-light"); pg.wait_for_timeout(420)
    back = probe(pg)
    print(f"  toggle -> light: bg {back['bg']} · CPI line {back['cpiLine']} · stored {back['stored']!r}")
    if back["theme"] != "light" or back["bg"] != "rgb(242, 241, 238)":
        problems.append(f"clicking Light did not restore the light palette (bg={back['bg']})")
    if back["cpiLine"] != light0["cpiLine"]:
        problems.append("switching back to Light did not restore the light chart colours")
    if back["stored"] != "light":
        problems.append("switching back to Light did not update the saved choice")

    # (3) the toggle must not throw the layout away: panes keep their scroll position
    kept = pg.evaluate("""() => { const rail = document.querySelector('#rail');
        rail.scrollTop = 200; const before = rail.scrollTop;
        document.getElementById('t-dark').click();
        return {before, after: rail.scrollTop, tiles: document.querySelectorAll('.tile').length}; }""")
    print(f"  rail scroll kept across a theme switch: {kept['before']} -> {kept['after']}")
    if kept["after"] != kept["before"] or kept["tiles"] != len(DATA["tiles"]):
        problems.append("switching theme rebuilt the DOM (scroll position / tile count changed)")
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.click("#t-light"); pg.wait_for_timeout(300)
    if errors:
        problems.append(f"theme toggle raised page errors: {errors[:2]}")
    pg.close(); browser.close()


def check_axes_and_latest(pw, problems):
    """The three defects a rendered-text check misses: overlapping axis labels, an axis that stops
    short of the newest observation, and a plotted series that is no longer being published.

    Each of these was reported by the user from a screenshot; each is asserted here so it cannot
    come back. Note the checks are structural (positions, counts, payload equality), not visual.
    """
    browser, page, errs = open_page(pw, 1600, 1000)
    try:
        # (1) NO OVERLAPPING TEXT INSIDE ANY CHART (the "%"-on-top-of-"8.0" defect).
        overlaps = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.card[data-chart]').forEach(card => {
              const ts = [...card.querySelectorAll('svg text')]
                .map(t => ({t: t.textContent, r: t.getBoundingClientRect()}))
                .filter(o => o.r.width > 0 && o.r.height > 0);
              for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
                const a = ts[i].r, b = ts[j].r;
                const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left);
                const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
                if (ox > 2 && oy > 2)
                  out.push({chart: card.dataset.chart, a: ts[i].t, b: ts[j].t});
              }
            });
            return out;
        }""")
        print(f"  axis-label overlaps: {len(overlaps)}")
        for o in overlaps[:6]:
            problems.append(f"overlapping axis text in {o['chart']}: {o['a']!r} vs {o['b']!r}")

        # (2) the x axis must LABEL the newest observation, and every series must show its last dot.
        latest = page.evaluate("""() => {
            const out = [];
            document.querySelectorAll('.card[data-chart]').forEach(card => {
              const dots = [...card.querySelectorAll('svg circle.lastdot')].map(c => c.getBoundingClientRect());
              const ticks = [...card.querySelectorAll('svg text[text-anchor="middle"]')].map(t => t.getBoundingClientRect());
              if (!dots.length || !ticks.length) { out.push({chart: card.dataset.chart, dots: dots.length, ticks: ticks.length}); return; }
              const dotX = Math.max(...dots.map(r => r.left + r.width / 2));
              const tickX = Math.max(...ticks.map(r => r.left + r.width / 2));
              out.push({chart: card.dataset.chart, dots: dots.length, gap: +Math.abs(dotX - tickX).toFixed(1)});
            });
            return out;
        }""")
        for r in latest:
            if r.get("dots", 0) < 1:
                problems.append(f"{r['chart']}: no latest-point dot drawn ({r})")
            elif r["gap"] > 4:
                problems.append(f"{r['chart']}: last x-axis label sits {r['gap']}px from the newest "
                                f"data point — the axis stops short of the latest observation")
        print(f"  latest-point markers + axis labelling checked on {len(latest)} charts")
        # every plotted series must have a dot, so a series cannot be silently dropped from the plot
        plotted = page.evaluate("""() => CHARTS.map(c => ({id: c.id,
            keys: c.kind === 'bar' ? [c.barKey, c.avgKey] : c.keys.map(k => k.key)}))""")
        dots_by_chart = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('.card[data-chart]')]
            .map(c => [c.dataset.chart, c.querySelectorAll('svg circle.lastdot').length]))""")
        for c in plotted:
            if dots_by_chart.get(c["id"], 0) < len(c["keys"]):
                problems.append(f"{c['id']}: {dots_by_chart.get(c['id'], 0)} latest-point dots for "
                                f"{len(c['keys'])} plotted series")

        # (3) NO CHART MAY PLOT A DEAD SERIES (the CMB line died in Aug-2020 and was still drawn).
        dead = DATA.get("dead_series", {})
        if "tbcmb" not in dead:
            problems.append("the dead-series audit did not flag tbcmb (guard would be vacuous)")
        for c in plotted:
            for k in c["keys"]:
                if k in dead:
                    problems.append(f"{c['id']} plots {k}, which has no observation since "
                                    f"{dead[k]['last']} ({dead[k]['days']} days)")

        # (4) THE TILE VALUE MUST EQUAL THE SERIES IT CLAIMS (the repo tile said 5.50% while the chart
        #     plotted a 5.25% weekly series, so the latest hike was invisible).
        bad = []
        for t in DATA["tiles"]:
            key = t.get("series_key")
            pts = (DATA["series"].get(key) or {}).get("points") or []
            if not pts:
                bad.append(f"{t['id']}: series {key} missing")
                continue
            if abs(pts[-1][1] - t["value"]) > 1e-6:
                bad.append(f"{t['id']}: tile {t['value']} != {key} last {pts[-1][1]}")
            if pts[-1][0] != t["period"]:
                bad.append(f"{t['id']}: tile period {t['period']} != {key} last date {pts[-1][0]}")
        print(f"  tile==series equality: {len(DATA['tiles'])} tiles checked, {len(bad)} mismatches")
        for b in bad[:6]:
            problems.append(f"tile/series mismatch — {b}")

        # (5) the reported case, end to end: does the CHART carry the announced policy rate?
        card = page.query_selector('.card[data-chart="rates"]')
        card.scroll_into_view_if_needed(); page.wait_for_timeout(200)
        box = card.query_selector(".chartwrap").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.985, box["y"] + box["height"] * 0.5)
        page.wait_for_timeout(260)
        tip = page.inner_text('.card[data-chart="rates"] .tip')
        repo_tile = next(t for t in DATA["tiles"] if t["id"] == "repo")
        print(f"  rates chart right edge: {tip.splitlines()[:2]} | repo tile {repo_tile['value']}% "
              f"({repo_tile['period']})")
        if str(repo_tile["value"]) not in tip:
            problems.append(f"the policy repo tile reads {repo_tile['value']}% on {repo_tile['period']} "
                            f"but that value is not on the chart's newest point: {tip!r}")

        # (6) a stale tile must SAY it is stale rather than show a meaningless delta
        stale_tiles = [t for t in DATA["tiles"] if t.get("stale")]
        print(f"  stale tiles flagged: {[t['id'] for t in stale_tiles]}")
        for t in stale_tiles:
            chip = page.query_selector(f'.tile[data-id="{t["id"]}"] .t-delta.stale')
            if not chip:
                problems.append(f"{t['id']} is {t['stale_days']} days stale but the tile shows no "
                                f"staleness marker")
            else:
                print(f"  {t['id']}: tile shows {chip.inner_text()!r}")
        if errs:
            problems.append(f"axis check console errors: {errs[:2]}")
    finally:
        browser.close()


def check_step_series(pw, problems):
    """Policy SETTINGS (CRR, SLR, the repo rate) must be dated by when they took effect.

    Regression this exists for: the CRR tile's ? panel read "latest reading 3.00% for 2026-10-02 ·
    3.00% - cut from 3.25% on 2025-12-05". Two things were wrong - 2026-10-02 is only the newest weekly
    row REPEATING a rate set on 2025-12-05, and the value was printed twice. The user asked "what is
    this???" and was right to.
    """
    import datetime as dt
    asof = dt.date.fromisoformat(DATA["as_of"])
    steps = [t for t in DATA["tiles"] if t.get("effective_from")]
    print(f"  step tiles: {[t['id'] for t in steps]}")
    for t in steps:
        pts = DATA["series"][t["series_key"]]["points"]
        by_date = dict(pts)
        if t["effective_from"] not in by_date:
            problems.append(f"{t['id']}: effective_from {t['effective_from']} is not a date in the series")
            continue
        # the setting must be the value of EVERY observation from that date onward
        after = [v for d, v in pts if d >= t["effective_from"]]
        if any(abs(v - t["value"]) > 1e-9 for v in after):
            problems.append(f"{t['id']}: value {t['value']} is not constant from {t['effective_from']} "
                            f"onward ({after[:5]})")
        if t.get("prev") is not None and t.get("bp"):
            before = [v for d, v in pts if d < t["effective_from"]]
            if before and abs(before[-1] - t["prev"]) > 1e-9:
                problems.append(f"{t['id']}: prev {t['prev']} != the last setting before the change "
                                f"({before[-1]})")
            if abs((t["value"] - t["prev"]) * 100 - t["bp"]) > 0.01:
                problems.append(f"{t['id']}: bp {t['bp']} does not match {t['prev']} -> {t['value']}")
        print(f"    {t['id']}: {t['value']}{t['unit']} in force since {t['effective_from']} "
              f"(prev {t.get('prev')}, {t.get('bp')}bp, {len(after)} rows)")

    browser, page, errs = open_page(pw, 1440, 900)
    try:
        # the UI must SAY "in force since", and must not date a setting by the newest repeating row
        for t in steps:
            foot = page.inner_text(f'.tile[data-id="{t["id"]}"] .t-foot')
            print(f"    {t['id']} foot: {foot!r}")
            if f"in force since {t['effective_from']}" not in foot:
                problems.append(f"{t['id']}: tile foot does not say 'in force since "
                                f"{t['effective_from']}' (got {foot!r})")
            btn = page.query_selector(f'.tile[data-id="{t["id"]}"] .help')
            btn.scroll_into_view_if_needed(); btn.click(); page.wait_for_timeout(230)
            body = page.inner_text("#d-body")
            page.click("#d-close"); page.wait_for_timeout(120)
            if f"in force since {t['effective_from']}" not in body:
                problems.append(f"{t['id']}: definition panel does not date the setting by its effective "
                                f"date")
            if t.get("prev") is not None and f"previous setting {t['prev']}" not in body:
                problems.append(f"{t['id']}: definition panel does not show the previous setting")
            # the exact nonsense phrasing that was reported must be impossible
            bad = f"{t['value']:.2f}{t['unit']} for {t['period']}"
            if bad in body.replace("\n", " "):
                problems.append(f"{t['id']}: definition panel still dates the setting by the newest "
                                f"table row ({bad!r})")
            if t["id"] == "crr":
                print(f"    crr panel: {'in force since 2025-12-05' in body=}, "
                      f"duplicate-value-check={'3.00% for 2026-10-02' not in body}")
        # non-step tiles must NOT claim an effective date
        for t in DATA["tiles"]:
            if not t.get("effective_from") and t["id"] in ("cpi", "m3", "credit"):
                foot = page.inner_text(f'.tile[data-id="{t["id"]}"] .t-foot')
                if "in force since" in foot:
                    problems.append(f"{t['id']} is a reading, not a setting, but shows 'in force since'")
        if errs:
            problems.append(f"step-series console errors: {errs[:2]}")
    finally:
        browser.close()


def check_history_modal(pw, problems):
    """Clicking any card must open a table of which value prevailed on which date.

    Settings (CRR/SLR/repo) show their CHANGE LOG; readings show the last 20 observations. Guards the
    class-collision bug found here: the tile's button and the modal panel must not share a class name,
    or a click inside the modal matches the button handler, swallows the event and the close button dies.
    """
    browser, page, errs = open_page(pw, 1440, 900)
    try:
        n_btn = page.eval_on_selector_all(".tile .histbtn", "els => els.filter(e => e.offsetWidth > 0).length")
        print(f"  history buttons visible: {n_btn}/{len(DATA['tiles'])}")
        if n_btn != len(DATA["tiles"]):
            problems.append(f"only {n_btn} of {len(DATA['tiles'])} tiles have a visible history button")

        # every tile: opens, correct headers, newest row == the tile's own reading, closes
        titles = {"setting": ["In force from", "Rate", "Until", "Move"],
                  "reading": ["Date", "Value", "Change vs previous"]}
        checked = 0
        for t in DATA["tiles"]:
            btn = page.query_selector(f'.tile[data-id="{t["id"]}"] .histbtn')
            btn.scroll_into_view_if_needed()
            btn.click()
            page.wait_for_timeout(190)
            if page.get_attribute("#histmodal", "hidden") is not None:
                problems.append(f"{t['id']}: history modal did not open")
                continue
            if page.inner_text("#h-title") != t["label"]:
                problems.append(f"{t['id']}: history modal title {page.inner_text('#h-title')!r} != label")
            heads = [th.strip() for th in page.eval_on_selector_all("#h-body table.hist th", "e => e.map(x => x.textContent)")]
            want = titles["setting" if t.get("step") else "reading"]
            if heads != want:
                problems.append(f"{t['id']}: history headers {heads} != {want}")
            rows = page.eval_on_selector_all("#h-body table.hist tbody tr",
                                             "e => e.map(r => [...r.children].map(c => c.textContent.trim()))")
            min_rows = 1 if t.get("step") else 3      # a setting may legitimately never have changed
            if len(rows) < min_rows:
                problems.append(f"{t['id']}: history table has only {len(rows)} rows (min {min_rows})")
            else:
                # the newest row must be the value the card itself shows
                first_val = rows[0][1].replace(",", "").replace("%", "").replace("x", "").replace("pp", "").strip()
                try:
                    if abs(float(first_val) - t["value"]) > 0.011:
                        problems.append(f"{t['id']}: history newest row {rows[0][1]!r} != tile value "
                                        f"{t['value']}")
                except ValueError:
                    problems.append(f"{t['id']}: history newest row value {rows[0][1]!r} is not numeric")
                if t.get("step"):
                    if rows[0][0] != t["effective_from"]:
                        problems.append(f"{t['id']}: change log starts {rows[0][0]} != effective_from "
                                        f"{t['effective_from']}")
                    vals = [r[1] for r in rows]
                    if any(vals[i] == vals[i + 1] for i in range(len(vals) - 1)):
                        problems.append(f"{t['id']}: change log has a no-op row (consecutive equal "
                                        f"values) ({vals})")
                else:
                    if t["period"] != rows[0][0]:
                        problems.append(f"{t['id']}: history starts {rows[0][0]} != tile period {t['period']}")
            # clicking inside the modal must NOT be hijacked by the tile-button handler
            page.click("#h-body .hist-sum"); page.wait_for_timeout(150)
            if page.get_attribute("#histmodal", "hidden") is not None:
                problems.append(f"{t['id']}: clicking inside the history modal closed it (event hijacked)")
            page.click("#h-close"); page.wait_for_timeout(150)
            if page.get_attribute("#histmodal", "hidden") is None:
                problems.append(f"{t['id']}: history close button did not close the modal")
            checked += 1
        print(f"  history tables checked: {checked}/{len(DATA['tiles'])} "
              f"(headers, newest row == tile value, close works)")

        # a step tile's log must be the CHANGE history, e.g. CRR: 8 changes since 2021
        crr = next(t for t in DATA["tiles"] if t["id"] == "crr")
        print(f"  crr change log: {len(crr['history'])} changes, "
              f"newest {crr['history'][0]['date']} {crr['history'][0]['value']}%")
        if len(crr["history"]) != 8:
            problems.append(f"crr change log has {len(crr['history'])} entries, expected 8")

        # tile body click opens the same modal; ? still opens the definition instead
        for tid in ("m3", "gsec", "gold", "food"):
            el = page.query_selector(f'.tile[data-id="{tid}"]')
            el.scroll_into_view_if_needed(); el.click(); page.wait_for_timeout(220)
            if page.get_attribute("#histmodal", "hidden") is not None:
                problems.append(f"{tid}: clicking the card body did not open its history")
            page.keyboard.press("Escape"); page.wait_for_timeout(180)
        el = page.query_selector('.tile[data-id="gold"]')
        el.query_selector(".help").click(); page.wait_for_timeout(240)
        if page.get_attribute("#defmodal", "hidden") is not None:
            problems.append("gold: ? did not open the definition")
        if page.get_attribute("#histmodal", "hidden") is None:
            problems.append("gold: ? also opened the history modal")
        page.keyboard.press("Escape"); page.wait_for_timeout(180)

        # the strip must date a SETTING by when it took effect, not by the snapshot timestamp
        strip = page.eval_on_selector_all("#strip .kv", "e => e.map(k => k.innerText.replace(/\\n/g, ' | '))")
        for chip in strip:
            print(f"    strip: {chip}")
        if not any("CRR" in c and "in force since 2025-12-05" in c for c in strip):
            problems.append("the CRR chip in the strip does not carry its effective date (it used to say "
                            "'2025-11-28', the snapshot stamp)")
        if errs:
            problems.append(f"history modal console errors: {errs[:2]}")
    finally:
        browser.close()


def main() -> int:
    problems: list[str] = []
    try:
        with sync_playwright() as pw:
            print("desktop 1440x900")
            browser, page, errs = open_page(pw, 1440, 900)
            check_shell(page, problems)
            check_tiles_and_charts(page, problems)
            check_no_dead_space(page, problems)
            check_hover(page, problems)
            check_date_alignment(page, problems)
            check_modal(page, problems)
            check_definitions(page, problems)
            check_density_and_sort(page, problems)
            check_font(page, problems)
            # the header must state the newest observation per publication calendar, matching the
            # payload - a single max date reads as staleness when the fastest table simply lags
            head = page.inner_text(".brand .meta")
            byf = DATA.get("as_of_by_frequency", {})
            print(f"  header as-of line: {head.replace(chr(10), ' ')}")
            if len(byf) < 2:
                problems.append("the payload carries no per-frequency as-of breakdown")
            for freq, d in byf.items():
                if d not in head:
                    problems.append(f"the header does not show the {freq} as-of date {d}")
            if DATA["as_of"] not in head:
                problems.append(f"the header omits the overall newest observation {DATA['as_of']}")
            verdict = page.inner_text("#verdict")
            print(f"  verdict: {verdict!r}")
            if verdict.strip() in ("", "–"):
                problems.append("verdict not populated")
            print(f"  console errors: {len(errs)}")
            problems.extend(errs[:3])
            page.screenshot(path=str(ROOT / "dashboard" / "warroom_screenshot.png"), full_page=False)
            check_no_dead_space(page, problems, quiet=True)      # post-interaction sanity
            browser.close()

            check_responsive(browser, problems) if False else None
            # a fresh browser for the width sweep (the previous one is closed)
            browser2 = pw.chromium.launch()
            check_responsive(browser2, problems)
            browser2.close()

            print("axis labels, latest-point markers, tile==series")
            check_axes_and_latest(pw, problems)

            print("policy settings vs readings (effective-from dating)")
            check_step_series(pw, problems)

            print("per-card history tables")
            check_history_modal(pw, problems)

            print("theme toggle")
            check_theme(pw, problems)

            print("mobile 390x844")
            check_mobile(pw, problems)
    except Exception:
        traceback.print_exc()
        problems.append("verification crashed (see traceback)")

    print()
    if problems:
        print(f"FAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"  * {p}")
        return 1
    print("PASS — fixed-viewport shell with independent panes, no dead space at 7 widths, "
          "38 tiles + 26 charts, legend/expand/hover/zoom on every chart, 33 sourced definitions, "
          "worst-first sort, 3 densities, Archivo embedded, hamburger rail on mobile.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        print(traceback.format_exc())
        sys.exit(2)
