#!/usr/bin/env python3
"""
dbie_client.py - Browserless client for the RBI "Database on Indian Economy" (DBIE) portal.

WHY THIS EXISTS
---------------
https://data.rbi.org.in is an Angular SPA whose data traffic goes to JSON gateways
(`/CIMS_Gateway_*/GATEWAY/SERVICES/<action>`). This module replays those calls over plain
HTTP with `requests`, so no browser/Playwright is needed for extraction.

AUTH MODEL (reverse-engineered from main.*.js, verified live)
-------------------------------------------------------------
1. GET https://data.rbi.org.in/  -> sets the sticky-session cookie `TS01eeff17=...`.
   The cookie IS required: without it every data call answers 4311.
2. POST /CIMS_Gateway_DBIE/GATEWAY/SERVICES/security_generateSessionToken with
   headers {channelkey: key2, datatype: application/json} and body {"body":{}}.
   The session token comes back in the RESPONSE HEADER `authorization`
   (NOT in the body). channelkey MUST be key2 - minting with key1 returns a token
   that the gateway rejects with errorCode 4311 "Current session is unauthorized".
3. Every later call sends headers {authorization: <token>, channelkey: key2,
   datatype: application/json, Content-Type: application/json}.
4. Response bodies are HTML-entity-encoded JSON (`&#x7b;` == `{`); they must be
   html.unescape()-d the decoded string is plain JSON.

STETP: Strict Telemetry / Exception-Trapping Protocol
- LAW1: narrow try/except everywhere, never a bare `except: pass`, full traceback to stderr.
- LAW2: [INFO]/[WARN]/[ERROR] [Component] lifecycle logging on stderr.
- LAW3: dense inline comments (what / why / IO).
- LAW4: verified by live runs; see the `--selftest` flag.

USAGE
-----
  python3 dbie_client.py <action> ['{"body":{}}'] [--gateway DBIE|REPORTS|RBIDATA|LOGIN] [--raw]
  python3 dbie_client.py --selftest
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import os
import sys
import time
import traceback
from typing import Any

import requests

# --------------------------------------------------------------------------- #
# Constants - one place to change if RBI ships a new bundle
# --------------------------------------------------------------------------- #
HOST = "https://data.rbi.org.in"
GATEWAYS = {
    "DBIE": "/CIMS_Gateway_DBIE/GATEWAY/SERVICES",       # main portal: menus, counts, publications, BSR
    "LOGIN": "/CIMS_Gateway_LOGIN/GATEWAY/SERVICES",     # audit/login helpers, sap token
    "SAARC": "/CIMS_Gateway_SAARC/GATEWAY/SERVICES",     # SAARC mirror portal
    "RBIDATA": "/CIMS_Gateway_RBIDATA/GATEWAY/SERVICES",  # mobile-app (RBIDATA) actions - incl. dbie_getWSSReport
    "FRBS": "/CIMS_Gateway_FRBS/GATEWAY/SERVICES",       # financial reporting (banks) data
    "REPORTS": "/CIMS_Gateway_REPORTS/GATEWAY/SERVICES",  # time-series report builder (Impala-backed)
}
# A desktop Chrome UA is sent because the gateway's WAF fingerprints lib user-agents.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/141.0.0.0 Safari/537.36")

log = logging.getLogger("dbie")

# --------------------------------------------------------------------------- #
# Field-level crypto
# --------------------------------------------------------------------------- #
# Some DBIE fields are AES-CBC encrypted (response fields like FROM_DATE/REPORT_FREQUENCY,
# and request params for a few actions: dbie_getEcoSubHeader, dbie_getReportsDbie,
# dbie_getElementDetailsAction, dbie_getCodeListAction, dbie_getApiResponse, ...).
# The key material is HARDCODED in main.*.js (class `zr` / encrypt pipe), i.e. it is not a
# secret the client is meant to protect - it is an obfuscation layer:
#   key = PBKDF2(password = TOKEN, salt = hex(TOKEN_STATUS), keySize = 8 words (256 bit),
#                iterations = 1000, PRF = SHA1)
#   iv  = hex(TOKEN_RESPONSE)            cipher = AES-256-CBC, ciphertext = Base64
# VERIFIED LIVE: decrypting `gFlctjwO2VrMgIC3C9JS8g==` yields `31-MAR-2009`.
# These are client-side obfuscation constants published by the portal, not
# account credentials. They can be overridden via environment variables if RBI
# rotates its bundle, without editing this file.
AES_TOKEN = os.environ.get(
    "DBIE_AES_TOKEN",
    "48d6b976d7135745b47b407cd8e659a45d8ebaca4ee95f87d5d939604f472268",  # gitleaks:allow
)
AES_TOKEN_STATUS = os.environ.get(
    "DBIE_AES_TOKEN_STATUS",
    "577bd45a17977269694908d80905c32a",  # gitleaks:allow
)
AES_TOKEN_RESPONSE = os.environ.get(
    "DBIE_AES_TOKEN_RESPONSE",
    "dc0da04af8fee58593442bf834b30739",  # gitleaks:allow
)


def _aes_key() -> bytes:
    """Derive the 32-byte AES key exactly as the SPA's PBKDF2 call does."""
    import hashlib
    return hashlib.pbkdf2_hmac("sha1", AES_TOKEN.encode(), bytes.fromhex(AES_TOKEN_STATUS), 1000, 32)


def dbie_encrypt(plain: str) -> str:
    """Encrypt a string the way the portal expects it in an encrypted request field."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        import base64
        from cryptography.hazmat.primitives import padding
        padder = padding.PKCS7(128).padder()
        data = padder.update(plain.encode()) + padder.finalize()
        enc = Cipher(algorithms.AES(_aes_key()), modes.CBC(bytes.fromhex(AES_TOKEN_RESPONSE))).encryptor()
        return base64.b64encode(enc.update(data) + enc.finalize()).decode()
    except Exception:
        log.error("[ERROR] [Crypto] encrypt failed:\n%s", traceback.format_exc())
        raise


def dbie_decrypt(cipher_b64: str) -> str:
    """Decrypt a portal-encrypted field back to plain text (dates, frequencies, names)."""
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        import base64
        from cryptography.hazmat.primitives import padding
        dec = Cipher(algorithms.AES(_aes_key()), modes.CBC(bytes.fromhex(AES_TOKEN_RESPONSE))).decryptor()
        raw = dec.update(base64.b64decode(cipher_b64)) + dec.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return (unpadder.update(raw) + unpadder.finalize()).decode("utf-8", "replace")
    except Exception:
        # Not every field is encrypted; returning the input is the honest fallback.
        log.info("[INFO] [Crypto] value not decryptable, left as-is")
        return cipher_b64


def decrypt_walk(obj: Any) -> Any:
    """Recursively decrypt every Base64-looking string in a payload (portal encrypts field-by-field)."""
    import re
    pat = re.compile(r"^[A-Za-z0-9+/]{15,}={0,2}$")
    if isinstance(obj, dict):
        return {k: decrypt_walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [decrypt_walk(v) for v in obj]
    if isinstance(obj, str) and pat.match(obj):
        return dbie_decrypt(obj)
    return obj


# --------------------------------------------------------------------------- #
# Session / token plumbing
# --------------------------------------------------------------------------- #
class DBieClient:
    """Stateful client: keeps the sticky cookie + session token, re-mints on 4311."""

    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout                      # per-request network timeout (s)
        self.token: str | None = None               # current `authorization` token
        self.token_ts: float = 0.0                  # when it was minted (for age logging)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": UA,
            "Origin": HOST,
            "Referer": HOST + "/",
            "Accept": "application/json, text/plain, */*",
        })

    # -- step 1: sticky cookie -------------------------------------------------
    def warm_up(self) -> None:
        """GET the SPA index so the WAF issues the TS01eeff17 sticky cookie."""
        try:
            r = self.session.get(HOST + "/", timeout=self.timeout)
            log.info("[INFO] [Session] warm-up %s cookies=%s", r.status_code, list(self.session.cookies))
        except requests.RequestException:
            log.error("[ERROR] [Session] warm-up failed:\n%s", traceback.format_exc())
            raise

    # -- step 2: mint token ----------------------------------------------------
    def mint(self) -> str:
        """POST security_generateSessionToken; token arrives in the `authorization` response header."""
        url = HOST + GATEWAYS["DBIE"] + "/security_generateSessionToken"
        try:
            r = self.session.post(
                url,
                json={"body": {}},
                headers={"Content-Type": "application/json",
                         "channelkey": "key2",           # key1 => token rejected with 4311
                         "datatype": "application/json"},
                timeout=self.timeout,
            )
            token = r.headers.get("authorization") or r.headers.get("Authorization")
            if not token:
                # Server answered but without a token: surface the raw body, it carries the reason.
                raise RuntimeError(f"no authorization header; body={html.unescape(r.text)[:200]}")
            self.token, self.token_ts = token, time.time()
            log.info("[INFO] [Auth] minted token %s (http %s)", token, r.status_code)
            return token
        except Exception:
            log.error("[ERROR] [Auth] mint failed:\n%s", traceback.format_exc())
            raise

    def ensure_token(self) -> str:
        """Lazily mint; also re-mint when the token is older than 20 min (server TTL is minutes-ish)."""
        if not self.token or (time.time() - self.token_ts) > 1200:
            self.mint()
        return self.token  # type: ignore[return-value]

    # -- step 3: data calls ----------------------------------------------------
    def call(self, action: str, body: dict | None = None, gateway: str = "DBIE",
             retries: int = 3, raw: bool = False) -> Any:
        """POST one gateway action and return parsed JSON (or the decoded text when raw=True)."""
        if gateway not in GATEWAYS:
            raise ValueError(f"unknown gateway {gateway!r}; expected one of {list(GATEWAYS)}")
        url = f"{HOST}{GATEWAYS[gateway]}/{action}"
        payload = body if body is not None else {"body": {}}
        last_err: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                token = self.ensure_token()
                r = self.session.post(
                    url, json=payload,
                    headers={"Content-Type": "application/json",
                             "channelkey": "key2",
                             "datatype": "application/json",
                             "authorization": token},
                    timeout=self.timeout,
                )
                decoded = html.unescape(r.text)             # un-entity the JSON payload
                if raw:
                    return decoded
                try:
                    parsed = json.loads(decoded)
                except json.JSONDecodeError:
                    # Non-JSON (usually an HTML error page) - keep the head for diagnosis.
                    raise RuntimeError(f"non-JSON response http={r.status_code}: {decoded[:300]}")
                status = (parsed.get("header") or {}).get("status")
                code = (parsed.get("header") or {}).get("errorCode")
                if status == "error" and code == "4311":
                    if attempt >= retries:
                        # Report the real cause instead of looping to exhaustion and then raising the
                        # generic "unknown call failure".
                        last_err = RuntimeError(f"{gateway}/{action}: 4311 unauthorized after "
                                                f"{retries} attempt(s)")
                        break
                    # Session died or token stale: re-mint once and retry the same call.
                    log.warning("[WARN] [Call] %s/%s -> 4311 unauthorized, re-minting (attempt %s)",
                             gateway, action, attempt)
                    self.token = None
                    self.mint()
                    continue
                if status == "error":
                    # A gateway error is NOT a result. Returning it as data made callers treat it as a
                    # real payload - a 0-point series or a 0-row table - and burned no retry on a
                    # transient failure. Raising lets the retry loop below do its job.
                    raise RuntimeError(f"{gateway}/{action} gateway error code={code}: "
                                       f"{(parsed.get('header') or {}).get('errorMessage')!r}")
                log.info("[INFO] [Call] %s/%s ok bytes=%s", gateway, action, len(r.text))
                return parsed
            except Exception as exc:                        # network / parse failure
                last_err = exc
                log.warning("[WARN] [Call] %s/%s attempt %s failed: %s", gateway, action, attempt, exc)
                time.sleep(min(2 ** attempt, 10))           # exponential backoff, capped
        log.error("[ERROR] [Call] %s/%s gave up after %s attempts", gateway, action, retries)
        raise last_err if last_err else RuntimeError("unknown call failure")

    # -- convenience wrappers for the catalogue actions -------------------------
    def reports_all(self) -> Any:
        """Every DBIE report entry (id, name, frequency, publication link)."""
        return self.call("dbie_GetPopularReportsPortalNew", {"body": {"portal": "DBIE", "limit": "all"}})

    def menu(self) -> Any:
        """Full portal menu mapping = the dataset hierarchy (Department > Menu > Function)."""
        return self.call("dbie_menuMappingList", {"body": {}})

    def wss_report(self, request_vo: dict) -> Any:
        """Time-series rows: request_vo carries reportName + item/level codes + date window."""
        return self.call("dbie_getWSSReport", {"body": {"requestVO": request_vo}}, gateway="RBIDATA")

    def report_tabs(self, report_id: str) -> Any:
        return self.call("REPORTS_getReportTabs", {"body": {"reportId": report_id}}, gateway="REPORTS")

    def report_filters(self, report_id: str, tabname: str) -> Any:
        return self.call("REPORTS_getAllFilters",
                         {"body": {"reportId": report_id, "tabname": tabname}}, gateway="REPORTS")

    def report_data(self, report_id: str, tabname: str, page_size: int = 0, page_number: int = 0) -> Any:
        return self.call("REPORTS_getWSSReport",
                         {"body": {"reportId": report_id, "pageSize": page_size,
                                   "pageNumber": page_number, "tabname": tabname}},
                         gateway="REPORTS")

    def report_page(self, report_id: str, tabname: str, page_size: int = 100,
                    page_number: int = 1) -> Any:
        """One page of a report table.

        TRAP: the tabName inside a REPORTS_getReportTabs response contains NON-BREAKING
        SPACES (\\xa0). Posting that string back returns an EMPTY table with status
        "success" and no error - always normalise NBSP -> space before sending it.
        """
        clean = tabname.replace("\xa0", " ").strip()
        if clean != tabname:
            log.info("[INFO] [Report] normalised NBSP in tabname %r -> %r", tabname, clean)
        return self.report_data(report_id, clean, page_size, page_number)

    def solr(self, solr_path: str) -> Any:
        """Run a Solr query through the portal proxy (dbiecollec / dbiePro collections).

        `solr_path` is the RAW relative query, e.g.
            'dbiecollec/select?q=*:*&rows=1443'
            'dbiecollec/select?defType=edismax&q=CPI&qf=COLLECTOR&stopwords=true&rows=100'
            'dbiecollec/select?fq=(FUNCTION:Publication)%20AND%20(REPORT_FREQUENCY:Monthly)&q=COLLECTOR:*&rows=1000000'
        The proxy takes the path AES-encrypted, and the JSON it returns is padded with
        NBSP characters, so it must be normalised before json.loads().
        """
        payload = self.call("dbie_getApiResponse", {"body": {"url": dbie_encrypt(solr_path)}})
        try:
            inner = payload["body"]["Result"][0]["respStatus"].replace("\xa0", " ")
            return json.loads(inner)
        except Exception:
            log.error("[ERROR] [Solr] cannot parse proxy response:\n%s", traceback.format_exc())
            raise


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _selftest() -> int:
    """LAW4: prove the whole chain (cookie -> token -> data) against the live portal."""
    c = DBieClient()
    c.warm_up()
    c.mint()
    menu = c.menu()
    ok_menu = bool(menu.get("body", {}).get("menuList"))
    print("menu list:", "OK" if ok_menu else "FAIL")
    rep = c.call("dbie_getPublicationDataImpala", {"body": {}})
    rows = rep.get("body", {}).get("result", [])
    print("publication data rows:", len(rows))
    print("sample:", json.dumps(rows[:2])[:300])
    return 0 if ok_menu else 1


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    ap = argparse.ArgumentParser(description="Call an RBI DBIE gateway action over plain HTTP.")
    ap.add_argument("action", nargs="?", help="gateway action, e.g. dbie_mainMenuList")
    ap.add_argument("body", nargs="?", default='{"body":{}}', help="JSON body (default {\"body\":{}})")
    ap.add_argument("--gateway", default="DBIE", choices=list(GATEWAYS))
    ap.add_argument("--raw", action="store_true", help="print decoded text instead of re-parsed JSON")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if not args.action:
        ap.error("action is required (or use --selftest)")

    try:
        body = json.loads(args.body)                 # fail fast on a malformed literal
    except json.JSONDecodeError as exc:
        log.error("[ERROR] [CLI] body is not valid JSON: %s", exc)
        return 2

    try:
        client = DBieClient()
        client.warm_up()
        out = client.call(args.action, body, gateway=args.gateway, raw=args.raw)
    except Exception:
        log.error("[ERROR] [CLI] call failed:\n%s", traceback.format_exc())
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1) if not args.raw else out)  # stdout = payload
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
