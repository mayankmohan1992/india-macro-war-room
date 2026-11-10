#!/usr/bin/env python3
"""
weekly_note.py - write "the week in six numbers" from the published API.

WHAT THIS IS FOR
  A short, citable note a person reads in 30 seconds and a journalist can quote without re-checking
  everything: six numbers, each with the date it refers to, what it moved by, and the threshold it is
  measured against. It is generated from api/v1/ - the same numbers the dashboard and the embed show -
  so the note cannot drift from the data.

WHAT IT REFUSES TO DO
  * No causal language, no forecast, no interpretation beyond arithmetic. "CPI is 1.54 points above
    the 4% target" is a fact this file can establish; "inflation is being driven by food" is an
    argument it cannot make. Commentary worth publishing gets added by a human on top of this.
  * No number without its observation date. The note is written on a Friday and most of these prints
    are weeks old, so nothing here says "this week" about a September figure.
  * No padding. If a series is missing or unreadable the slot says so and the count drops - the six
    slots do not get filled with something else to keep the shape.
  * No unit confusion. The repo rate moves in basis points and the table stores 25.0 for +25 bp; the
    liquidity series is negative when the RBI is absorbing; credit growth's `change` is against the
    previous *publication*, not against last week. Each of those is handled where it is used.

USAGE
  python tools/weekly_note.py                    # notes/YYYY-Www.md + notes/index.md
  python tools/weekly_note.py --card             # ...and the 1200x675 social card as HTML
  python tools/weekly_note.py --card --png       # ...and a screenshot of it (needs playwright)
  python tools/weekly_note.py --date 2026-11-13  # label the note with a specific date
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
API = ROOT / "api" / "v1"
NOTES = ROOT / "notes"

WINDOW_DAYS = 28        # "change over the past four weeks" for series that move inside it
TARGET = 4.0            # RBI's flexible inflation target, midpoint
BAND = (2.0, 6.0)       # ...and the tolerance band around it

# The six slots are fixed on purpose: a reader who saw last week's note can compare it line by line.
SLOT_ORDER = ["repo", "cpi", "wpi", "liquidity", "credit_wedge", "gsec"]


# --------------------------------------------------------------------------- #
# reading the API
# --------------------------------------------------------------------------- #
def load(ind_id: str) -> dict | None:
    p = API / "series" / f"{ind_id}.json"
    if not p.exists():
        return None
    payload = json.loads(p.read_text(encoding="utf-8"))
    ind = payload.get("indicator", payload)
    return ind if isinstance(ind, dict) else None


def points(ind: dict) -> list[tuple[str, float]]:
    out = []
    for d, v in ind.get("points", []) or []:
        if isinstance(v, (int, float)):
            out.append((str(d), float(v)))
    return out


def at_or_before(pts: list[tuple[str, float]], day: str) -> tuple[str, float] | None:
    for d, v in reversed(pts):
        if d <= day:
            return d, v
    return None


def latest(ind: dict) -> tuple[str, float]:
    lat = ind.get("latest") or {}
    return str(lat.get("date", "")), float(lat.get("value", 0.0))


# --------------------------------------------------------------------------- #
# formatting
# --------------------------------------------------------------------------- #
def num(v: float, unit: str = "") -> str:
    a = abs(v)
    dp = 0 if a >= 1000 else 1 if a >= 100 else 2
    return f"{v:,.{dp}f}" + (unit if unit else "")


def pct(v: float) -> str:
    return f"{v:.2f}%"


def pp(v: float) -> str:
    return f"{v:+.2f} pp"


def crore(v: float) -> str:
    """One way of saying it, chosen by size - never the same number twice in one sentence."""
    return f"₹{abs(v) / 100_000:.2f} lakh crore" if abs(v) >= 100_000 else f"₹{abs(v):,.0f} crore"


def short_date(iso: str) -> str:
    try:
        d = dt.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day} {d.strftime('%b %Y')}"


def ago(iso: str, asof: dt.date) -> str:
    try:
        days = (asof - dt.date.fromisoformat(iso)).days
    except ValueError:
        return ""
    return f"{days} days" if days >= 0 else ""


# --------------------------------------------------------------------------- #
# the six slots
# --------------------------------------------------------------------------- #
def cell(cid: str, label: str, value: str, delta: str, obs: str, clause: str,
         link: str, series: list[tuple[str, float]]) -> dict:
    return {"id": cid, "label": label, "value": value, "delta": delta, "obs": obs,
            "clause": clause, "link": link, "series": series[-160:]}


def repo_cell(asof: dt.date) -> dict | None:
    ind = load("repo")
    if not ind:
        return None
    pts = points(ind)
    d, v = latest(ind)
    # history entries are CHANGES: date = effective date, change = basis points (25.0 = +25 bp).
    hist = [h for h in (ind.get("history") or []) if isinstance(h, dict)]
    if hist:
        h = hist[0]
        bp = float(h.get("change") or 0.0)
        prev = float(h.get("previous", h.get("prev", v - bp / 100)) or 0.0)
        delta = f"{bp:+.0f} bp on {short_date(str(h.get('date', d)))}, from {pct(prev)}"
        clause = "the benchmark for every other rate in the economy"
    else:
        delta, clause = "no change on record", f"in force on {short_date(d)}"
    return cell("repo", "Policy repo rate", pct(v), delta, short_date(d), clause, "series/repo.html", pts)


def cpi_cell(asof: dt.date) -> dict | None:
    ind = load("cpi")
    if not ind:
        return None
    pts = points(ind)
    d, v = latest(ind)
    prior = at_or_before(pts, (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat())
    delta = (f"{v - prior[1]:+.2f} pp on the previous print ({short_date(prior[0])})" if prior
             else "first print in the series")
    gap = v - TARGET
    side = "above" if gap > 0 else "below"
    where = "inside" if BAND[0] <= v <= BAND[1] else "outside"
    clause = f"{abs(gap):.2f} pp {side} the {TARGET:.0f}% target, {where} the {BAND[0]:.0f}–{BAND[1]:.0f}% band"
    return cell("cpi", "CPI inflation", pct(v), delta, short_date(d), clause, "series/cpi.html", pts)


def wpi_cell(asof: dt.date) -> dict | None:
    ind = load("wpi")
    if not ind:
        return None
    pts = points(ind)
    d, v = latest(ind)
    prior = at_or_before(pts, (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat())
    delta = (f"{v - prior[1]:+.2f} pp on the previous print" if prior else "first print in the series")
    cpi = load("cpi")
    if cpi:
        cv = latest(cpi)[1]
        clause = (f"{abs(v - cv):.2f} pp above retail inflation" if v > cv
                  else f"{abs(v - cv):.2f} pp below retail inflation")
    else:
        clause = "wholesale price inflation"
    return cell("wpi", "WPI inflation", pct(v), delta, short_date(d), clause, "series/wpi.html", pts)


def liquidity_cell(asof: dt.date) -> dict | None:
    ind = load("liquidity")
    if not ind:
        return None
    pts = points(ind)
    d, v = latest(ind)
    # The series is net LAF operations: negative means the RBI is absorbing liquidity. The minus sign
    # carries that, so the number is never shown as a bare positive with the verb left to the prose.
    side = "absorption" if v < 0 else "injection"
    month = at_or_before(pts, (asof - dt.timedelta(days=WINDOW_DAYS)).isoformat())
    if month:
        then, now = abs(month[1]), abs(v)
        moved = now - then
        delta = (f"{side} {'fell' if moved < 0 else 'rose'} to {crore(now)} from {crore(then)} "
                 f"in {WINDOW_DAYS} days")
    else:
        delta = f"net {side}, no reading a month back to compare"
    c = cell("liquidity", "Liquidity (net LAF, 1-month avg)",
             ("\u2212" if v < 0 else "") + crore(v), delta, short_date(d),
             "1-month average of daily net RBI operations", "series/liquidity.html", pts)
    c["delta_card"] = delta.replace(f"in {WINDOW_DAYS} days", "in 4 weeks")
    return c


def wedge_cell(asof: dt.date) -> dict | None:
    credit, deposit = load("credit"), load("deposit")
    if not credit or not deposit:
        return None
    d, cv = latest(credit)
    _, dv = latest(deposit)
    wed = cv - dv
    ch = credit.get("latest", {}).get("change")
    dh = deposit.get("latest", {}).get("change")
    def way(x: float) -> str:
        return f"down {abs(x):.2f} pp" if x < 0 else f"up {x:.2f} pp"

    delta = (f"credit {pct(cv)} vs deposits {pct(dv)} on the same fortnight"
             + (f"; credit {way(ch)} and deposits {way(dh)} on the previous print"
                if isinstance(ch, (int, float)) and isinstance(dh, (int, float)) else ""))
    clause = ("credit growing faster than deposits — banks fund the difference elsewhere" if wed > 0
              else "deposits growing faster than credit")
    c = cell("credit_wedge", "Credit growth minus deposit growth", f"{wed:+.2f} pp", delta,
             short_date(d), clause, "series/credit.html", points(credit))
    if isinstance(ch, (int, float)) and isinstance(dh, (int, float)):
        c["delta_card"] = f"credit {pct(cv)} vs deposits {pct(dv)}; credit {way(ch)}, deposits {way(dh)}"
    return c


def gsec_cell(asof: dt.date) -> dict | None:
    ind = load("gsec")
    if not ind:
        return None
    pts = points(ind)
    d, v = latest(ind)
    month = at_or_before(pts, (asof - dt.timedelta(days=WINDOW_DAYS)).isoformat())
    delta = (f"{v - month[1]:+.2f} pp over {WINDOW_DAYS} days" if month else "no reading a month back")
    return cell("gsec", "10-year G-sec yield", pct(v), delta, short_date(d),
                "what the market charges the government to borrow for ten years", "series/gsec.html", pts)


def fx_cell(asof: dt.date) -> dict | None:
    """The seventh number, kept structured so it cannot read as a stray paragraph."""
    ind = load("usdinr")
    if not ind:
        return None
    pts = points(ind)
    d, v = latest(ind)
    month = at_or_before(pts, (asof - dt.timedelta(days=WINDOW_DAYS)).isoformat())
    if not month:
        return {"label": "Also · USD/INR", "value": f"{v:.2f}", "delta": "no reading a month back",
                "obs": short_date(d), "clause": "rupees per US dollar"}
    move, base = v - month[1], month[1]
    delta = (f"{(move):+.2f} ({(move) / base * 100:+.1f}%) in {WINDOW_DAYS} days").replace("-", "\u2212")
    return {"label": "Also · USD/INR", "value": f"{v:.2f}", "delta": delta, "obs": short_date(d),
            "clause": "rupees per US dollar, the rupee " + ("firmer" if move < 0 else "weaker") + " on the month"}


def freshness_line(asof: dt.date) -> str:
    """How old the oldest print behind the note is - measured to the day the note is written.

    The API's own `stale_days` is relative to the dataset's as-of date, which is not the same thing as
    "how old is this print today": on 2026-11-10 a 30 Sep print is 41 days old, not the 32 the dataset
    reported on 2026-11-01. The note says the age the reader can check.
    """
    rows = []
    for ind_id in ("cpi", "wpi", "credit", "gsec"):
        ind = load(ind_id)
        if not ind:
            continue
        obs, _ = latest(ind)
        try:
            age = (asof - dt.date.fromisoformat(obs)).days
        except ValueError:
            continue
        if age > 0:
            rows.append((age, ind.get("label", ind_id)))
    rows.sort(reverse=True)
    if not rows:
        return ""
    parts = [f"{label} ({n} days)" for n, label in rows[:3]]
    return ("Nothing here is real-time: the oldest prints this note leans on are "
            + "; ".join(parts) + ".")


def build(asof: dt.date) -> dict:
    status = json.loads((API / "status.json").read_text(encoding="utf-8"))
    counts = status.get("counts", {}) or {}
    dataset_as_of = (status.get("meta", {}) or {}).get("dataset_as_of") or status.get("as_of", "")

    builders = {"repo": repo_cell, "cpi": cpi_cell, "wpi": wpi_cell, "liquidity": liquidity_cell,
                "credit_wedge": wedge_cell, "gsec": gsec_cell}
    cells, missing = [], []
    for cid in SLOT_ORDER:
        c = builders[cid](asof)
        if c:
            cells.append(c)
        else:
            missing.append(cid.replace("_", " "))

    return {"cells": cells, "missing": missing, "counts": counts, "asof": asof,
            "dataset_as_of": dataset_as_of, "fx_cell": fx_cell(asof), "fresh": freshness_line(asof),
            "sha": (status.get("dataset_sha256") or "")[:12]}


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def render_md(note: dict) -> str:
    week = note["asof"].isocalendar()
    c = note["counts"]
    out = [f"# The week in six numbers — {week.year}-W{week.week:02d}", ""]
    out.append(f"*Six Indian macro indicators, as published rather than forecast. Data as of "
               f"{note['dataset_as_of']}; note compiled {note['asof'].isoformat()}.*")
    out.append("")
    if c:
        out.append(f"Of the 38 indicators this project tracks, **{c.get('good', 0)} are in range, "
                   f"{c.get('watch', 0)} need watching and {c.get('bad', 0)} are in stress** "
                   f"(rules are published with the data).")
        out.append("")
    filled = len(note["cells"])
    out.append(f"**The six.** {filled} of {len(SLOT_ORDER)} slots filled"
               + (f" — no readable {', '.join(note['missing'])} this week." if note["missing"] else "."))
    out.append("")
    for i, cell in enumerate(note["cells"], 1):
        out.append(f"{i}. **{cell['label']} — {cell['value']}** ({cell['obs']}). "
                   f"{cell['delta'][0].upper() + cell['delta'][1:]}; {cell['clause']}.")
    out.append("")
    if note["fx_cell"]:
        fx = note["fx_cell"]
        out.append(f"**{fx['label']} — {fx['value']}** ({fx['obs']}). "
                   f"{fx['delta'][0].upper() + fx['delta'][1:]}; {fx['clause']}.")
        out.append("")
    if note["fresh"]:
        out.append(note["fresh"])
        out.append("")
    out.append("Every figure is traceable to an RBI table: the dashboard draws the series, the API "
               "serves it, and the build fails rather than publish a short table. "
               "→ https://mayankmohan1992.github.io/india-macro-war-room/")
    out.append("")
    out.append(f"`dataset_sha256 {note['sha']}…` · source: RBI DBIE · MIT")
    return "\n".join(out) + "\n"


def spark(series: list[tuple[str, float]], w: int = 150, h: int = 34) -> str:
    if len(series) < 2:
        return ""
    vals = [v for _, v in series]
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    n = len(series)
    d = " ".join(f"{'M' if i == 0 else 'L'}{i * w / (n - 1):.1f} {h - (v - lo) / (hi - lo) * h:.1f}"
                 for i, (_, v) in enumerate(series))
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" class="spark" aria-hidden="true">'
            f'<path d="{d}" fill="none" stroke="currentColor" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')


def protect(text: str) -> str:
    """Keep a range and a rupee amount from being split across lines in the card."""
    text = re.sub(r"(\d+[–-]\d+%)", r'<span class="nw">\1</span>', text)
    text = re.sub(r"(₹[\d.,]+ lakh crore)", r'<span class="nw">\1</span>', text)
    text = re.sub(r"(\d+ weeks? ago)", r'<span class="nw">\1</span>', text)
    return text


def render_card_html(note: dict) -> str:
    week = note["asof"].isocalendar()
    c = note["counts"]
    cells = "".join(
        f'<div class="cell"><div class="k">{cell["label"]}</div>'
        f'<div class="v">{cell["value"]}</div>'
        f'<div class="d">{protect(cell.get("delta_card", cell["delta"]))}</div>'
        f'<div class="o">{cell["obs"]} · {protect(cell["clause"])}</div>{spark(cell["series"])}</div>'
        for cell in note["cells"])
    return f"""<!doctype html><meta charset="utf-8"><title>{week.year}-W{week.week:02d}</title>
<style>
  *{{box-sizing:border-box}}
  body{{margin:0;width:1200px;height:675px;padding:40px 52px;background:#f7f5f1;color:#17181a;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif}}
  .top{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid #d9d4cb;padding-bottom:12px}}
  h1{{font-size:33px;margin:0;letter-spacing:-.02em;font-weight:650}}
  .meta{{font-family:ui-monospace,Menlo,monospace;font-size:13px;color:#5f6065;text-align:right;line-height:1.5}}
  .sub{{display:block;font-size:14px;font-weight:400;color:#5f6065;letter-spacing:0;margin-top:5px}}
  .grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:24px 34px;margin-top:22px}}
  .k{{font-size:12px;letter-spacing:.03em;color:#5f6065;text-transform:uppercase;font-weight:600}}
  .v{{font-size:30px;font-weight:640;letter-spacing:-.02em;margin:1px 0 0;line-height:1.15;color:#17181a}}
  .d{{font-family:ui-monospace,Menlo,monospace;font-size:11.5px;color:#8a4b1f;line-height:1.4;margin-top:2px}}
  .o{{font-size:12px;color:#5f6065;margin:4px 0 5px;line-height:1.38;min-height:34px}}
  .spark{{color:#8a4b1f;display:block}}
  .strip{{position:absolute;bottom:30px;left:52px;right:52px;display:flex;justify-content:space-between;
         font-family:ui-monospace,Menlo,monospace;font-size:13px;color:#4a4b50}}
  .nw{{white-space:nowrap}}
</style>
<div class="top">
  <h1>The week in six numbers<span class="sub">as published, not forecast</span></h1>
  <div class="meta">{note['asof'].isoformat()} · {week.year}-W{week.week:02d}<br>data as of {note['dataset_as_of']}</div>
</div>
<div class="grid">{cells}</div>
<div class="strip">
  <span>{c.get('good',0)} in range · {c.get('watch',0)} to watch · {c.get('bad',0)} in stress, of 38 tracked{f" · USD/INR {note['fx_cell']['value']}" if note.get('fx_cell') else ""}</span>
  <span>RBI DBIE · mayankmohan1992.github.io/india-macro-war-room</span>
</div>"""



NOTE_CSS = """
  :root{--bg:#f7f5f1;--ink:#17181a;--muted:#5f6065;--rule:#d9d4cb;--accent:#8a4b1f}
  @media (prefers-color-scheme:dark){:root{--bg:#121312;--ink:#ece9e3;--muted:#b6b7ba;--rule:#3b3d3b;--accent:#e0a377}}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,
       "Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;line-height:1.62;font-size:17px}
  .wrap{max-width:42rem;margin:0 auto;padding:3.5rem 1.5rem 5rem}
  h1{font-size:1.9rem;letter-spacing:-.02em;line-height:1.15;margin:0 0 .5rem;text-wrap:balance}
  .sub{color:var(--muted);font-size:.95rem;margin:0 0 2rem}
  .counts{font-size:.95rem;border-left:2px solid var(--rule);padding-left:1rem;color:var(--muted);margin:0 0 2.2rem}
  ol{padding:0;margin:0;list-style:none;counter-reset:n}
  li{counter-increment:n;padding:1.05rem 0;border-top:1px solid var(--rule)}
  li:last-child{border-bottom:1px solid var(--rule)}
  li.aside{counter-increment:none}
  li.aside .lbl::before{content:""}
  .lbl{font-family:ui-monospace,Menlo,monospace;font-size:.72rem;letter-spacing:.08em;
       text-transform:uppercase;color:var(--muted);display:block;margin-bottom:.15rem}
  .lbl::before{content:counter(n) ". ";color:var(--accent)}
  li.aside .lbl{letter-spacing:.12em}
  .val{font-size:1.45rem;font-weight:640;letter-spacing:-.015em}
  .dlt{font-family:ui-monospace,Menlo,monospace;font-size:.82rem;color:var(--accent);margin-left:.5rem}
  .note{display:block;font-size:.9rem;color:var(--muted);margin-top:.2rem}
  p.fx,p.fresh{font-size:.95rem;color:var(--muted);text-wrap:pretty}
  .fine{font-size:.88rem;line-height:1.5;display:inline-block;margin-top:.5rem;text-wrap:pretty}
  a.src{color:var(--muted);text-decoration:none;border-bottom:1px dotted var(--rule)}
  a.src:hover{color:var(--accent);border-bottom-color:var(--accent)}
  li.aside .lbl{color:var(--muted)}
  footer{margin-top:2.6rem;padding-top:1.2rem;border-top:1px solid var(--rule);
         font-family:ui-monospace,Menlo,monospace;font-size:.82rem;color:var(--muted);line-height:1.6}
  footer a{color:var(--accent);text-underline-offset:3px}
"""


def tie_units(text: str) -> str:
    """Keep a number with its unit, and short phrases unbroken, when a line wraps.

    The card and the note are read in a feed, where an orphaned "pp" or a dangling "in" is the
    difference between looking generated and looking written.
    """
    nbsp = "\u00a0"
    out = esc(text)
    out = re.sub(r"(\d[\d.,]*|−₹\d[\d.,]*)\s(lakh crore|pp|bp|points|%|days)",
                 lambda m: m.group(1) + nbsp + m.group(2), out)
    out = re.sub(r"\b(in|over|on)\s(\d+\u00a0days)", lambda m: m.group(1) + nbsp + m.group(2), out)
    out = re.sub(r"\b(down|up)\s(\d[\d.]*\u00a0pp)", lambda m: m.group(1) + nbsp + m.group(2), out)
    return out


def render_note_html(note: dict) -> str:
    week = note["asof"].isocalendar()
    c = note["counts"]
    items = "".join(
        f'<li><span class="lbl">{tie_units(cell["label"])}</span>'
        f'<span class="val">{tie_units(cell["value"])}</span>'
        f'<span class="dlt">{tie_units(cell["delta"])}</span>'
        f'<span class="note"><a class="src" href="../api/v1/series/'
        f'{cell["id"].split("_")[0]}.csv" title="the series behind this number">'
        f'{tie_units(cell["obs"])}</a> · {tie_units(cell["clause"])}</span></li>'
        for cell in note["cells"])
    fx = note.get("fx_cell")
    fx_row = (f'<li class="aside"><span class="lbl">{tie_units(fx["label"])}</span>'
              f'<span class="val">{tie_units(fx["value"])}</span>'
              f'<span class="dlt">{tie_units(fx["delta"])}</span>'
              f'<span class="note">{tie_units(fx["obs"])} · {tie_units(fx["clause"])}</span></li>'
              if fx else "")
    counts = (f'{c.get("good", 0)} in range · {c.get("watch", 0)} to watch · '
              f'{c.get("bad", 0)} in stress, of 38 tracked') if c else ""
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The week in six numbers — {week.year}-W{week.week:02d}</title>
<meta name="description" content="Six Indian macro numbers as published, with the date of each print and what it moved by.">
<style>{NOTE_CSS}</style></head><body><div class="wrap">
<h1>The week in six numbers</h1>
<p class="sub">{week.year}-W{week.week:02d} · compiled {note['asof'].isoformat()} · data as of {esc(note['dataset_as_of'])}</p>
<p class="counts">{counts}<br><span class="fine">"In range", "to watch" and "in stress" follow rules
published with the data, not a judgement made here. Each figure below is the latest <em>published</em>
print of that indicator, not one week's worth of it — the dates differ because the sources do.</span></p>
<ol>{items}{fx_row}</ol>

{f'<p class="fresh">{esc(note["fresh"])}</p>' if note['fresh'] else ''}
<p class="fresh">A negative net LAF figure means the RBI is <em>absorbing</em> liquidity from the banking
system; the sign carries the direction. Definitions for every term are in the
<a href="https://github.com/mayankmohan1992/india-macro-war-room/blob/main/docs/DATA_DICTIONARY.md">data
dictionary</a>.</p>
<footer>
  Every figure above is traceable to an RBI table: the
  <a href="../">dashboard</a> draws the series, the <a href="../api/v1/">API</a> serves it, and the
  build fails rather than publish a short table.<br>
  <code>dataset_sha256 {note['sha']}…</code> · source: RBI DBIE · MIT
</footer>
</div></body></html>"""


def esc(s) -> str:
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))

def update_index(note_files: list[pathlib.Path], where: pathlib.Path = NOTES) -> None:
    rows = ["# Notes", "",
            "One note a week: the six numbers that describe the Indian macro picture, generated from "
            "the same API the dashboard serves, each figure carrying its publication date.", ""]
    for p in sorted(note_files, reverse=True):
        first = p.read_text(encoding="utf-8").splitlines()[0]
        rows.append(f"- [{first.lstrip('# ').strip()}]({p.name})")
    rows += ["", "Machine-readable copy of each note sits beside its page (`YYYY-Www.md`), and the "
                 "social card (`YYYY-Www.png`) is the same six numbers for posting."]
    (where / "index.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    items = "".join(
        f'<li><a href="{p.stem}.html">{esc(p.read_text(encoding="utf-8").splitlines()[0].lstrip("# ").strip())}</a>'
        f' · <a href="{p.stem}.png">card</a></li>'
        for p in sorted(note_files, reverse=True))
    (where / "index.html").write_text(f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Notes · India Macro War Room</title><style>{NOTE_CSS}</style></head><body><div class="wrap">
<h1>Notes</h1>
<p class="sub">One note a week: six numbers that describe the Indian macro picture, generated from the
same API the dashboard serves, each figure carrying the date it was published.</p>
<ol>{items}</ol>
<footer><a href="../">Dashboard</a> · <a href="../api/v1/">API</a> · source: RBI DBIE · MIT</footer>
</div></body></html>""", encoding="utf-8")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Write the week-in-six-numbers note from api/v1")
    ap.add_argument("--date", help="label the note with this date (default: today)")
    ap.add_argument("--card", action="store_true", help="also write the social card HTML")
    ap.add_argument("--png", action="store_true", help="screenshot the card (implies --card)")
    ap.add_argument("--out", default=str(NOTES), help="directory to write into (default: notes/)")
    args = ap.parse_args(argv[1:])

    asof = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    note = build(asof)
    if not note["cells"]:
        print("[ERROR] [Note] no series readable from api/v1 - refusing to write an empty note",
              file=sys.stderr)
        return 1

    week = asof.isocalendar()
    stem = f"{week.year}-W{week.week:02d}"
    md = out_dir / f"{stem}.md"
    md.write_text(render_md(note), encoding="utf-8")
    print(f"[INFO] [Note] wrote {md} ({len(note['cells'])} of {len(SLOT_ORDER)} slots)")
    page = out_dir / f"{stem}.html"
    page.write_text(render_note_html(note), encoding="utf-8")
    print(f"[INFO] [Note] wrote {page}")

    if args.png:
        args.card = True
    if args.card:
        html = out_dir / f"{stem}.card.html"
        html.write_text(render_card_html(note), encoding="utf-8")
        print(f"[INFO] [Note] wrote {html}")
        if args.png:
            try:
                from playwright.sync_api import sync_playwright
                png = out_dir / f"{stem}.png"
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    page = browser.new_page(viewport={"width": 1200, "height": 675}, device_scale_factor=2)
                    page.goto(html.resolve().as_uri())
                    page.screenshot(path=str(png))
                    browser.close()
                print(f"[INFO] [Note] wrote {png} ({png.stat().st_size // 1024} KB)")
            except Exception as exc:                     # a missing browser must not fail the refresh
                print(f"[WARN] [Note] card screenshot skipped: {exc}", file=sys.stderr)

    update_index(list(out_dir.glob("20??-W??.md")), out_dir)
    print(f"[INFO] [Note] notes/index.md updated ({len(list(out_dir.glob('20??-W??.md')))} note(s))")
    print("\n" + render_md(note))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
