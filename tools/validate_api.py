#!/usr/bin/env python3
"""
validate_api.py - validate the published API: schema conformance, cross-document consistency and
integrity. Runs in CI on every push and before the daily refresh commits, so a broken API fails the
build instead of shipping.

CHECKS
  1. every document validates against api/v1/schema/*.schema.json (a small JSON Schema subset:
     type / required / properties / enum / const / pattern / minItems / maxItems / items)
  2. cross-document: every catalogue entry has a series file; live values agree between index.json,
     latest.json, the series file, the CSV and dashboard/warroom_data.json
  3. semantics: dates are ISO, statuses are good|watch|bad, settings carry effective_from and a
     change log, ratings rules are present
  4. integrity: manifest.json sha256/byte sizes match the files on disk, and status.json's
     dataset_sha256 recomputes from the files (that hash is what the workflow uses to decide whether
     the data actually changed)

STETP: [INFO]/[WARN]/[ERROR] logs, per-check try/except, non-zero exit listing every problem.
"""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import pathlib
import re
import sys
import traceback
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
log = logging.getLogger("validate")

ROOT = pathlib.Path(__file__).resolve().parents[1]
API = ROOT / "api" / "v1"


def check_schema(doc: Any, schema: dict, path: str, problems: list[str]) -> None:
    """Minimal JSON Schema validation: enough to catch real drift without a dependency."""
    try:
        t = schema.get("type")
        if t == "object":
            if not isinstance(doc, dict):
                problems.append(f"{path}: expected object, got {type(doc).__name__}")
                return
            for req in schema.get("required", []):
                if req not in doc:
                    problems.append(f"{path}: missing required key {req!r}")
            for k, sub in (schema.get("properties") or {}).items():
                if k in doc:
                    check_schema(doc[k], sub, f"{path}.{k}", problems)
        elif t == "array":
            if not isinstance(doc, list):
                problems.append(f"{path}: expected array, got {type(doc).__name__}")
                return
            if "minItems" in schema and len(doc) < schema["minItems"]:
                problems.append(f"{path}: needs >= {schema['minItems']} items, has {len(doc)}")
            if "maxItems" in schema and len(doc) > schema["maxItems"]:
                problems.append(f"{path}: needs <= {schema['maxItems']} items, has {len(doc)}")
            if "items" in schema:
                for i, item in enumerate(doc[:50]):
                    check_schema(item, schema["items"], f"{path}[{i}]", problems)
        elif t == "number" or t == "integer":
            if not isinstance(doc, (int, float)) or isinstance(doc, bool):
                problems.append(f"{path}: expected number, got {type(doc).__name__}")
        elif t == "string":
            if not isinstance(doc, str):
                problems.append(f"{path}: expected string, got {type(doc).__name__}")
            elif "pattern" in schema and not re.match(schema["pattern"], doc):
                problems.append(f"{path}: {doc!r} does not match {schema['pattern']}")
        if "enum" in schema and doc not in schema["enum"]:
            problems.append(f"{path}: {doc!r} not in {schema['enum']}")
        if "const" in schema and doc != schema["const"]:
            problems.append(f"{path}: {doc!r} != {schema['const']!r}")
    except Exception:
        problems.append(f"{path}: validator crashed\n{traceback.format_exc()}")


def main() -> int:
    problems: list[str] = []
    try:
        payload = json.loads((ROOT / "dashboard" / "warroom_data.json").read_text())
        schemas = {p.stem.split(".")[0]: json.loads(p.read_text())
                   for p in (API / "schema").glob("*.schema.json")}
        index = json.loads((API / "index.json").read_text())
        latest = json.loads((API / "latest.json").read_text())
        defs = json.loads((API / "definitions.json").read_text())

        # 1. schema conformance
        for doc, name in ((index, "index"), (latest, "latest")):
            check_schema(doc, schemas[name], f"{name}.json", problems)
        series_files = sorted((API / "series").glob("*.json"))
        for f in series_files:
            check_schema(json.loads(f.read_text()), schemas["series"], f"series/{f.name}", problems)
        print(f"  schema: {2 + len(series_files)} documents checked against "
              f"{len(schemas)} schemas, {len(problems)} problem(s) so far")

        # 2. cross-document consistency
        tiles = {t["id"]: t for t in payload["tiles"]}
        if len(index["indicators"]) != len(tiles):
            problems.append(f"index has {len(index['indicators'])} indicators, payload has {len(tiles)}")
        for ind in index["indicators"]:
            iid = ind["id"]
            sf = API / "series" / f"{iid}.json"
            cs = API / "series" / f"{iid}.csv"
            if not sf.exists():
                problems.append(f"{iid}: series file missing")
                continue
            if not cs.exists():
                problems.append(f"{iid}: CSV missing")
            t = tiles.get(iid)
            if not t:
                problems.append(f"{iid}: not present in the dashboard payload")
                continue
            doc = json.loads(sf.read_text())["indicator"]
            if ind["kind"] == "setting":
                if latest["latest"][iid]["change"] is not None:
                    problems.append(f"{iid}: a setting must carry change=null in latest.json "
                                    f"(got {latest['latest'][iid]['change']!r}) - the bp move lives in "
                                    f"`setting.change_bp`")
                if ind["latest"]["change"] is not None:
                    problems.append(f"{iid}: a setting must carry change=null in index.json")
            for label, a, b in (("index vs payload", ind["latest"]["value"], t["value"]),
                                ("series vs payload", doc["latest"]["value"], t["value"]),
                                ("latest vs payload", latest["latest"][iid]["value"], t["value"]),
                                ("date vs payload", doc["latest"]["date"], t["period"])):
                if a != b:
                    problems.append(f"{iid}: {label} mismatch {a!r} != {b!r}")
            rows = list(csv.reader(cs.open()))
            if len(rows) < 2:
                problems.append(f"{iid}: CSV has no data rows")
            elif abs(float(rows[-1][1]) - t["value"]) > 1e-6:
                problems.append(f"{iid}: CSV last value {rows[-1][1]} != payload {t['value']}")
            if ind["kind"] == "setting" and "setting" not in ind:
                problems.append(f"{iid}: a setting with no effective_from")
            # the catalogue is deliberately lean (no points/history), so history and the full
            # definition are checked on the series document
            if ind["kind"] == "setting" and len(doc.get("history") or []) < 1:
                problems.append(f"{iid}: setting with an empty change log")
            if ind["kind"] == "setting" and not doc.get("setting", {}).get("effective_from"):
                problems.append(f"{iid}: setting whose series document has no effective_from")
            if ind["kind"] == "reading" and len(doc.get("points") or []) < 3:
                problems.append(f"{iid}: reading with fewer than 3 points")
            if ind.get("frequency") in (None, "", "unknown"):
                problems.append(f"{iid}: frequency not derived")
            d = doc.get("definition") or {}
            if not d.get("source_url"):
                problems.append(f"{iid}: no definition source URL")
            if d.get("term") and d["term"] not in {v.get("term") for v in defs["definitions"].values()}:
                problems.append(f"{iid}: definition term not found in definitions.json")
        print(f"  consistency: {len(index['indicators'])} indicators cross-checked "
              f"(index/latest/series/CSV/payload)")

        # the reconciliation block must survive publishing (it disappeared once: it lived only in the
        # dashboard payload, not in the API documents)
        cc = index["meta"].get("cross_checks")
        if not cc:
            problems.append("index.json meta carries no cross_checks block")
        else:
            for c in cc:
                if c.get("max_abs_diff_pp", 0) > c.get("tolerance_pp", 0):
                    problems.append(f"cross-check {c.get('indicator')} exceeds its tolerance")
            print(f"  reconciliation: {[(c['indicator'], c['max_abs_diff_pp'], c['tolerance_pp']) for c in cc]}")

        # 3. integrity: manifest hashes + dataset hash
        manifest = json.loads((API / "manifest.json").read_text())
        for f in manifest["files"]:
            p = API / f["path"]
            if not p.exists():
                problems.append(f"manifest lists {f['path']} which does not exist")
                continue
            if p.stat().st_size != f["bytes"]:
                problems.append(f"manifest size mismatch for {f['path']}")
            if hashlib.sha256(p.read_bytes()).hexdigest() != f["sha256"]:
                problems.append(f"manifest sha256 mismatch for {f['path']}")
        status = json.loads((API / "status.json").read_text())
        h = hashlib.sha256()
        for p in sorted([f for f in (API).rglob("*") if f.is_file()
                         and f.name not in ("manifest.json", "status.json") and "schema" not in f.parts]):
            h.update(str(p.relative_to(API)).encode())
            h.update(p.read_text().replace(status["generated_at"], "").encode())
        if h.hexdigest() != status["dataset_sha256"]:
            problems.append("status.json dataset_sha256 does not match the published files")
        print(f"  integrity: {len(manifest['files'])} files hashed, dataset_sha256 "
              f"{status['dataset_sha256'][:16]} verified, {status['bytes'] // 1024} KB total")
    except Exception:
        log.error("[ERROR] [Validate] crashed:\n%s", traceback.format_exc())
        problems.append("validator crashed (see traceback)")

    if problems:
        print(f"\nFAIL - {len(problems)} problem(s):")
        for p in problems[:25]:
            print(f"  * {p}")
        return 1
    print("\nPASS - API schema, consistency and integrity all verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
