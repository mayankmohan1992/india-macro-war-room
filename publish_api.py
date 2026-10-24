#!/usr/bin/env python3
"""
publish_api.py - publish the built dataset as a versioned, static, CORS-friendly JSON/CSV API.

WHY A STATIC API: the project must run on the free tier with no server. GitHub serves these files with
`access-control-allow-origin: *` from raw.githubusercontent.com (and via any CDN that mirrors the repo),
so a browser app or a spreadsheet can consume them directly:

    curl https://raw.githubusercontent.com/<owner>/<repo>/main/api/v1/latest.json

WHAT IT WRITES (all under api/v1/)
    index.json        catalogue: one entry per indicator + links (the entry point)
    latest.json/.csv  every indicator's latest value in one request
    series/<id>.json  full history of one indicator: metadata + definition + points + history
    series/<id>.csv   the same history as CSV, for spreadsheets and pandas
    settings.json     policy settings (CRR, SLR, repo) with effective-from dates and change logs
    snapshot.json     point-in-time key rates, each dated with its own source
    definitions.json  the sourced official definitions (RBI / MoSPI / FBIL)
    dataset.json      everything in one document, for consumers who prefer a single fetch
    schema/*.json     JSON Schema for index / latest / series documents
    manifest.json     every published file with its sha256 and byte size (integrity)
    status.json       generated_at + dataset_sha256 + counts (freshness / change detection)

EVERY document carries the same `meta` block: dataset as-of date, retrieval date, the source (RBI DBIE),
a provenance note and the API version. A consumer never has to guess where a number came from.

STETP: [INFO]/[WARN]/[ERROR] logs, granular try/except, non-zero exit on any failure, `--check` mode for
CI (rebuild to a temp dir and fail if the committed artefacts would change).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import logging
import pathlib
import sys
import tempfile
import traceback
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
log = logging.getLogger("api")

# The project version, published in status.json so a deployment can be identified at runtime
# (`curl .../status.json | jq .project_version`). Kept in sync with CHANGELOG.md and the git tag.
# status.json is excluded from dataset_sha256, so bumping this does not look like a data change.
PROJECT_VERSION = "1.0.6"

ROOT = pathlib.Path(__file__).resolve().parent
API_VERSION = "v1"
SOURCE_NAME = "Reserve Bank of India — Database on Indian Economy (DBIE)"
SOURCE_URL = "https://data.rbi.org.in/"
PROVENANCE = ("Compiled from RBI public publications. Not an official RBI product: verify anything "
              "critical at the source. Figures may be revised by the publisher without notice.")

# files whose CONTENT (not the generated timestamp) decides whether the dataset actually changed
DATA_FILES = ["index.json", "latest.json", "latest.csv", "settings.json", "snapshot.json",
              "definitions.json", "dataset.json", "series"]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def freq_of(points: list[list[Any]]) -> str:
    """Label the publication frequency from the median gap between observations."""
    try:
        ds = sorted(dt.date.fromisoformat(p[0]) for p in points)
        if len(ds) < 3:
            return "unknown"
        gaps = sorted((ds[i + 1] - ds[i]).days for i in range(len(ds) - 1))
        med = gaps[len(gaps) // 2]
        return ("daily" if med <= 3 else "weekly" if med <= 9 else "fortnightly" if med <= 20
                else "monthly" if med <= 45 else "quarterly" if med <= 120 else "irregular")
    except Exception:
        log.warning("[WARN] [Freq] could not derive frequency:\n%s", traceback.format_exc())
        return "unknown"


def write_json(path: pathlib.Path, doc: Any) -> int:
    """Write a document deterministically (sorted keys, indented) and return its byte size."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        path.write_text(text)
        return len(text.encode())
    except Exception:
        log.error("[ERROR] [Write] %s failed:\n%s", path, traceback.format_exc())
        raise


def write_csv(path: pathlib.Path, header: list[str], rows: list[list[Any]]) -> int:
    """Write a small CSV (used for series history and the latest-value table)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        return path.stat().st_size
    except Exception:
        log.error("[ERROR] [Write] %s failed:\n%s", path, traceback.format_exc())
        raise


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build_api(out: pathlib.Path, generated: str) -> dict:
    """Render every published document from the built dashboard payload. Returns a summary."""
    payload = json.loads((ROOT / "dashboard" / "warroom_data.json").read_text())
    series = payload["series"]
    defs = payload.get("definitions") or {}
    as_of = payload["as_of"]

    meta = {
        "api_version": API_VERSION,
        "dataset_as_of": as_of,
        "dataset_as_of_by_frequency": payload.get("as_of_by_frequency", {}),
        "retrieved_at": generated,
        "indicators": len(payload["tiles"]),
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "provenance": PROVENANCE,
        "docs": "docs/API.md",
        "license": "Code: MIT. Data: compiled from RBI public publications, with attribution.",
        # reconciliation between a headline derived here and the publisher's own series, so a consumer
        # can see that the published figure is quoted and how far the derived one sits from it
        "cross_checks": payload.get("cross_checks", []),
    }

    # ---- per-indicator documents -------------------------------------------------------------
    catalogue, latest_rows, latest_map = [], [], {}
    for t in payload["tiles"]:
        key = t["series_key"]
        pts = series[key]["points"]
        indicator: dict[str, Any] = {
            "id": t["id"],
            "label": t["label"],
            "unit": t["unit"],
            "group": t["group"],
            "kind": "setting" if t.get("step") else "reading",
            "frequency": t.get("freq") or freq_of(pts),
            "status": t["status"],
            "status_reason": t["reason"],
            "scoring_rule": t["rule"],
            "series": key,
            "source": series[key].get("source", ""),
            "latest": {"date": t["period"], "value": t["value"], "change": t["change"]},
            "stale_days": t.get("stale_days"),
            "stale": bool(t.get("stale")),
            "definition": defs.get(t["def_key"]),
            "links": {"self": f"series/{t['id']}.json", "csv": f"series/{t['id']}.csv"},
        }
        if t.get("effective_from"):
            indicator["setting"] = {"effective_from": t["effective_from"], "previous": t.get("prev"),
                                    "change_bp": t.get("bp"),
                                    "unchanged_in_window": bool(t.get("unchanged_in_window"))}
        # a setting's week-on-week change is noise; the meaningful datum is the bp move, which is
        # carried in `setting`. Leave `change` null so nobody reads "0.0" as an event - and do it BEFORE
        # the document is written. This used to run after write_json(), so series/<id>.json shipped the
        # raw tile change (repo: +0.25, crr/slr: 0.0) while index.json and latest.json shipped null:
        # the same field, four files, two answers.
        if indicator["kind"] == "setting":
            indicator["latest"]["change"] = None
        indicator["points"] = pts
        indicator["history"] = t.get("history", [])
        indicator["history_kind"] = t.get("history_kind")
        indicator["history_note"] = t.get("history_note")
        write_json(out / "series" / f"{t['id']}.json", {"meta": meta, "indicator": indicator})
        write_csv(out / "series" / f"{t['id']}.csv", ["date", "value"], pts)
        cat = {k: v for k, v in indicator.items() if k not in ("points", "history", "definition")}
        cat["definition"] = {"term": (indicator.get("definition") or {}).get("term"),
                             "source_url": (indicator.get("definition") or {}).get("source_url")}
        catalogue.append(cat)
        # same source as latest.json: the indicator document, where a setting's change is null.
        # status is not duplicated inside `latest`, so it stays the tile's own field.
        chg = indicator["latest"]["change"]
        latest_rows.append([t["id"], t["label"], indicator["latest"]["value"], t["unit"],
                            indicator["latest"]["date"], t["status"],
                            chg if chg is not None else ""])
        latest_map[t["id"]] = {"value": indicator["latest"]["value"], "unit": t["unit"],
                               "date": indicator["latest"]["date"], "status": t["status"],
                               "change": indicator["latest"]["change"],
                               "kind": indicator["kind"], "label": t["label"]}

    write_json(out / "index.json", {"meta": meta, "indicators": catalogue})
    write_json(out / "latest.json", {"meta": meta, "latest": latest_map})
    write_csv(out / "latest.csv", ["id", "label", "value", "unit", "date", "status", "change"],
              latest_rows)

    # ---- policy settings, with the dates they took effect -------------------------------------
    # settings need effective_from / previous / change_bp (nested under `setting` in the catalogue) and
    # the change log (which lives in the series document, kept out of the lean catalogue)
    settings = []
    for ind in catalogue:
        if ind["kind"] != "setting":
            continue
        doc = json.loads((out / "series" / f"{ind['id']}.json").read_text())["indicator"]
        settings.append({
            "id": ind["id"], "label": ind["label"], "unit": ind["unit"],
            "value": ind["latest"]["value"], "as_published": ind["latest"]["date"],
            "effective_from": (ind.get("setting") or {}).get("effective_from"),
            "previous": (ind.get("setting") or {}).get("previous"),
            "change_bp": (ind.get("setting") or {}).get("change_bp"),
            "unchanged_in_window": (ind.get("setting") or {}).get("unchanged_in_window"),
            "history": doc.get("history", []), "history_note": ind.get("history_note"),
            "source": ind.get("source", ""),
        })
    settings.sort(key=lambda x: x["id"])
    write_json(out / "settings.json", {"meta": meta, "settings": settings})
    write_json(out / "snapshot.json", {"meta": meta, "snapshot": payload.get("snapshot", [])})
    write_json(out / "definitions.json", {"meta": meta, "definitions": defs})

    # ---- one-document dataset for single-fetch consumers --------------------------------------
    dataset = {
        "meta": meta,
        "indicators": catalogue,
        "series": {i["id"]: {"points": i["points"], "history": i["history"]} for i in
                   [{**t, "id": t["id"], "points": series[t["series_key"]]["points"],
                     "history": t.get("history", [])} for t in payload["tiles"]]},
        "snapshot": payload.get("snapshot", []),
        "definitions": defs,
        "cross_checks": payload.get("cross_checks", []),
    }
    write_json(out / "dataset.json", dataset)

    # ---- schemas ------------------------------------------------------------------------------
    unit_meta = {"type": "object", "required": ["api_version", "dataset_as_of", "source"],
                 "properties": {"api_version": {"const": API_VERSION},
                                "dataset_as_of": {"type": "string"},
                                "retrieved_at": {"type": "string"},
                                "source": {"type": "string"},
                                "provenance": {"type": "string"}}}
    series_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                     "title": "Indicator series (API v1)", "type": "object",
                     "required": ["meta", "indicator"],
                     "properties": {
                         "meta": unit_meta,
                         "indicator": {"type": "object",
                                       "required": ["id", "label", "unit", "kind", "frequency",
                                                    "series", "latest", "points"],
                                       "properties": {
                                           "id": {"type": "string"},
                                           "label": {"type": "string"},
                                           "unit": {"type": "string"},
                                           "kind": {"enum": ["setting", "reading"]},
                                           "frequency": {"type": "string"},
                                           "status": {"enum": ["good", "watch", "bad"]},
                                           "latest": {"type": "object",
                                                      "required": ["date", "value"],
                                                      "properties": {"date": {"type": "string",
                                                                              "pattern": "^\\d{4}-\\d{2}-\\d{2}$"},
                                                                     "value": {"type": "number"}}},
                                           "points": {"type": "array", "minItems": 1,
                                                      "items": {"type": "array", "minItems": 2,
                                                                "maxItems": 2}},
                                           "history": {"type": "array"}}}}}
    index_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                    "title": "Indicator catalogue (API v1)", "type": "object",
                    "required": ["meta", "indicators"],
                    "properties": {"meta": unit_meta,
                                   "indicators": {"type": "array", "minItems": 1,
                                                  "items": {"type": "object",
                                                            "required": ["id", "label", "links"]}}}}
    latest_schema = {"$schema": "https://json-schema.org/draft/2020-12/schema",
                     "title": "Latest values (API v1)", "type": "object",
                     "required": ["meta", "latest"],
                     "properties": {"meta": unit_meta,
                                    "latest": {"type": "object",
                                               "additionalProperties": {
                                                   "type": "object",
                                                   "required": ["value", "unit", "date", "status",
                                                                "change", "kind", "label"]}}}}
    for name, doc in (("series", series_schema), ("index", index_schema), ("latest", latest_schema)):
        write_json(out / "schema" / f"{name}.schema.json", doc)

    # The provenance verdict is produced from raw/ by tools/verify_provenance.py. Carry it into every
    # output directory, so a rebuild into a temp dir (CI's --out /tmp/api_rebuild) hashes exactly the
    # same set of files as the committed API - otherwise the reproducibility check compares like with
    # unlike and fails for the wrong reason.
    vpath = ROOT / "api" / API_VERSION / "verification.json"
    if vpath.exists() and vpath.resolve() != (out / "verification.json").resolve():
        (out / "verification.json").write_text(vpath.read_text())

    # ---- prune stale series files ---------------------------------------------------------------
    # Anything in series/ that the current payload no longer produces must go: a dropped indicator
    # used to keep being served (and hashed, and CDN-cached) forever, and any stray file - a .bak, an
    # editor temp - silently became part of the published manifest and the dataset hash.
    series_dir = out / "series"
    if series_dir.exists():
        expected = {f"{t['id']}.json" for t in payload["tiles"]} | \
                   {f"{t['id']}.csv" for t in payload["tiles"]}
        for p in sorted(series_dir.glob("*")):
            if p.is_file() and p.name not in expected:
                log.warning("[WARN] [API] removing stale %s", p.name)
                p.unlink()

    # ---- manifest + status --------------------------------------------------------------------
    files = sorted(p for p in out.rglob("*") if p.is_file()
                   and p.name not in ("manifest.json", "status.json"))
    manifest = {"meta": meta,
                "files": [{"path": str(p.relative_to(out)), "bytes": p.stat().st_size,
                           "sha256": sha256_of(p)} for p in files]}
    write_json(out / "manifest.json", manifest)

    # dataset hash: everything data-bearing, excluding volatile timestamps -> lets CI and the daily
    # workflow decide whether the DATA changed, so a no-op run does not create commit noise
    h = hashlib.sha256()
    # Compare the path RELATIVE to `out`. Testing `"schema" not in f.parts` looked at the ABSOLUTE
    # path, so checking out the repo under any directory named `schema` filtered out every file and
    # produced the hash of nothing - which the daily workflow reads as "nothing changed".
    for p in sorted([f for f in files
                     if f.relative_to(out).parts[0] != "schema" and f.name != "manifest.json"]):
        h.update(str(p.relative_to(out)).encode())
        body = p.read_text() if p.suffix == ".json" else p.read_text()
        body = body.replace(generated, "")           # drop the retrieval timestamp
        h.update(body.encode())
    dataset_sha = h.hexdigest()
    status = {"meta": meta, "generated_at": generated, "dataset_sha256": dataset_sha,
              "project_version": PROJECT_VERSION,
              "files": len(manifest["files"]),
              "bytes": sum(f["bytes"] for f in manifest["files"]),
              "series_points": sum(len(series[t["series_key"]]["points"]) for t in payload["tiles"]),
              "counts": payload["counts"], "verdict": payload["verdict"]}
    write_json(out / "status.json", status)
    return {"dataset_sha256": dataset_sha, "files": len(manifest["files"]),
            "bytes": status["bytes"], "indicators": len(catalogue),
            "points": status["series_points"], "project_version": PROJECT_VERSION}


def main() -> int:
    ap = argparse.ArgumentParser(description="Publish the built dataset as a static JSON/CSV API.")
    ap.add_argument("--out", default=str(ROOT / "api" / API_VERSION), help="output directory")
    ap.add_argument("--check", action="store_true",
                    help="verify the committed API matches a fresh build (used by CI)")
    args = ap.parse_args()
    out = pathlib.Path(args.out)
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        if args.check:
            # --check must VERIFY, not write. The previous implementation built into `out` first and
            # then re-read out/status.json, so it compared the fresh hash with itself, always claimed
            # they matched, and overwrote the very artefacts it was supposed to be checking. Build
            # into a throwaway directory and compare against what is committed.
            committed = out / "status.json"
            if not committed.exists():
                log.error("[ERROR] [API] --check: no committed status.json at %s", committed)
                return 1
            old = json.loads(committed.read_text())["dataset_sha256"]
            with tempfile.TemporaryDirectory() as tmp:
                summary = build_api(pathlib.Path(tmp), generated)
            if summary["dataset_sha256"] != old:
                log.error("[ERROR] [API] --check: committed %s != rebuilt %s - the committed API does "
                          "not reproduce from the committed raw tables",
                          old[:16], summary["dataset_sha256"][:16])
                return 1
            log.info("[INFO] [API] --check: committed artefacts reproduce exactly (%s)", old[:16])
            print(json.dumps(summary, indent=1))
            return 0

        summary = build_api(out, generated)
        log.info("[INFO] [API] wrote %s files (%s KB) for %s indicators / %s points -> %s",
                 summary["files"], round(summary["bytes"] / 1024), summary["indicators"],
                 summary["points"], out)
        log.info("[INFO] [API] dataset_sha256=%s", summary["dataset_sha256"][:16])
        print(json.dumps(summary, indent=1))
        return 0
    except Exception:
        log.error("[ERROR] [API] publishing failed:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
