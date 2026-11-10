/*!
 * India Macro War Room — embeddable chart
 * https://mayankmohan1992.github.io/india-macro-war-room/
 *
 * Draws one indicator from the War Room's static API into any page, with no dependencies, no key and
 * no build step:
 *
 *   <div data-imwr-series="cpi" data-imwr-height="220"></div>
 *   <script src="https://mayankmohan1992.github.io/india-macro-war-room/embed.js" async></script>
 *
 * The chart is rendered inside a shadow root, so the host page's CSS cannot break it and it cannot
 * break the host page. Colours follow the host page's light/dark preference and can be overridden
 * with the --imwr-* custom properties (see docs/EMBED.md).
 *
 * Licence: MIT, same as the dataset. Attribution is a condition of that licence: the credit line is
 * rendered by default and `data-imwr-credit="off"` is deliberately not supported — the numbers come
 * from RBI's publications, and the chart should say so.
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var BASE = (script && script.src ? script.src.replace(/\/embed\.js(\?.*)?$/, "") : "") + "/api/v1/";
  var FALLBACK_ORIGIN = "https://mayankmohan1992.github.io/india-macro-war-room/";

  var cache = new Map();          // series id -> Promise<indicator>
  var HOST_CSS = [
    ":host { all: initial; display: block; contain: layout style;",
    "  --ink: var(--imwr-ink, #17181a); --muted: var(--imwr-muted, #6a6b70);",
    "  --rule: var(--imwr-rule, #ded9d1); --accent: var(--imwr-accent, #8a4b1f);",
    "  --fill: var(--imwr-fill, rgba(138,75,31,.08)); }",
    ":host([hidden]) { display: none; }",
    "@media (prefers-color-scheme: dark) {",
    "  :host { --ink: var(--imwr-ink, #ece9e3); --muted: var(--imwr-muted, #b6b7ba);",
    "    --rule: var(--imwr-rule, #3b3d3b); --accent: var(--imwr-accent, #e0a377);",
    "    --fill: var(--imwr-fill, rgba(224,163,119,.12)); }",
    "}"
  ].join("\n");

  function css(el, name, fallback) {
    var v = getComputedStyle(el).getPropertyValue(name).trim();
    return v || fallback;
  }

  // -- data ------------------------------------------------------------------ //
  function load(id) {
    if (!cache.has(id)) {
      var url = BASE + "series/" + encodeURIComponent(id) + ".json";
      cache.set(id, fetch(url, { mode: "cors", credentials: "omit" }).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status + " for " + url);
        return r.json();
      }).then(function (payload) {
        var ind = payload.indicator || payload;
        if (!ind || !Array.isArray(ind.points)) throw new Error("no points in " + url);
        return ind;
      }));
    }
    return cache.get(id);
  }

  function cut(points, range) {
    if (!points.length) return points;
    var years = { "1y": 1, "3y": 3, "5y": 5, "10y": 10 }[range];
    if (!years) return points;                                   // "all" or unknown -> everything
    var end = new Date(points[points.length - 1][0] + "T00:00:00Z");
    var from = new Date(Date.UTC(end.getUTCFullYear() - years, end.getUTCMonth(), end.getUTCDate()));
    return points.filter(function (p) { return new Date(p[0] + "T00:00:00Z") >= from; });
  }

  // -- formatting ------------------------------------------------------------ //
  function fmt(v) {
    if (v === null || v === undefined || !isFinite(v)) return "—";
    var a = Math.abs(v);
    var dp = a >= 1000 ? 0 : a >= 100 ? 1 : 2;
    return v.toLocaleString(undefined, { minimumFractionDigits: dp, maximumFractionDigits: dp });
  }

  function shortDate(iso) {
    var d = new Date(iso + "T00:00:00Z");
    return d.toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
  }

  // -- drawing --------------------------------------------------------------- //
  function draw(host, ind, opts) {
    var points = cut(ind.points, opts.range);
    var W = Math.max(240, host.clientWidth || 480);
    var H = opts.height;
    var pad = { t: 26, r: 12, b: 22, l: 44 };
    var innerW = W - pad.l - pad.r;
    var innerH = H - pad.t - pad.b;

    if (points.length < 2) throw new Error("only " + points.length + " point(s) in range; widen data-imwr-range");

    var values = points.map(function (p) { return p[1]; }).filter(function (v) { return typeof v === "number"; });
    var lo = Math.min.apply(null, values), hi = Math.max.apply(null, values);
    if (!isFinite(lo) || !isFinite(hi)) throw new Error("no numeric points");
    if (hi === lo) { hi += Math.abs(hi || 1) * 0.05; lo -= Math.abs(lo || 1) * 0.05; }
    var span = hi - lo, y0 = lo - span * 0.08, y1 = hi + span * 0.08;

    var t0 = new Date(points[0][0] + "T00:00:00Z").getTime();
    var t1 = new Date(points[points.length - 1][0] + "T00:00:00Z").getTime();
    var xOf = function (iso) {
      var t = new Date(iso + "T00:00:00Z").getTime();
      return pad.l + (t1 === t0 ? innerW : ((t - t0) / (t1 - t0)) * innerW);
    };
    var yOf = function (v) { return pad.t + innerH - ((v - y0) / (y1 - y0)) * innerH; };

    var d = "", pen = false;
    points.forEach(function (p) {
      if (typeof p[1] !== "number" || !isFinite(p[1])) { pen = false; return; }
      d += (pen ? "L" : "M") + xOf(p[0]).toFixed(1) + " " + yOf(p[1]).toFixed(1) + " ";
      pen = true;
    });

    var last = points.filter(function (p) { return typeof p[1] === "number"; }).slice(-1)[0];
    var lastX = xOf(last[0]).toFixed(1), lastY = yOf(last[1]).toFixed(1);

    var zero = (y0 < 0 && y1 > 0)
      ? '<line class="zero" x1="' + pad.l + '" y1="' + yOf(0).toFixed(1) + '" x2="' + (W - pad.r) +
        '" y2="' + yOf(0).toFixed(1) + '"/>'
      : "";

    var label = opts.title || ind.label || ind.id;
    var unit = (ind.definition && ind.definition.unit) ? ind.definition.unit : "";
    var asOf = ind.latest && ind.latest.date ? ind.latest.date : last[0];

    var root = host.shadowRoot || host.attachShadow({ mode: "open" });
    root.innerHTML =
      "<style>" + HOST_CSS + STYLE + "</style>" +
      '<div class="card' + (opts.frame ? " framed" : "") + '">' +
        '<div class="head">' +
          '<span class="label">' + esc(label) + '</span>' +
          '<span class="value">' + fmt(ind.latest ? ind.latest.value : last[1]) + (unit ? '<span class="unit"> ' + esc(unit) + "</span>" : "") + '</span>' +
        "</div>" +
        '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '" role="img" aria-label="' +
          esc(label + ", latest " + fmt(ind.latest ? ind.latest.value : last[1]) + (unit ? " " + unit : "") + ", " + asOf) + '">' +
          zero +
          '<path class="area" d="' + d + "L" + (W - pad.r) + " " + (pad.t + innerH) + " L" + pad.l + " " + (pad.t + innerH) + ' Z"/>' +
          '<path class="line" d="' + d.trim() + '"/>' +
          '<circle class="dot" cx="' + lastX + '" cy="' + lastY + '" r="3"/>' +
          '<text class="axis" x="' + (pad.l - 7) + '" y="' + (yOf(hi) + 4).toFixed(1) + '" text-anchor="end">' + fmt(hi) + "</text>" +
          '<text class="axis" x="' + (pad.l - 7) + '" y="' + (yOf(lo) + 4).toFixed(1) + '" text-anchor="end">' + fmt(lo) + "</text>" +
          '<text class="axis x" x="' + pad.l + '" y="' + (H - 6) + '">' + esc(shortDate(points[0][0])) + "</text>" +
          '<text class="axis x" x="' + (W - pad.r) + '" y="' + (H - 6) + '" text-anchor="end">' + esc(shortDate(points[points.length - 1][0])) + "</text>" +
        "</svg>" +
        '<div class="foot">' +
          "<span>RBI DBIE</span>" +
          (ind.frequency ? '<span>· ' + esc(ind.frequency) + "</span>" : "") +
          '<span>· as of ' + esc(asOf) + "</span>" +
          '<a href="' + (ind.links && ind.links.self ? BASE + ind.links.self : FALLBACK_ORIGIN) +
            '" target="_blank" rel="noopener">data</a>' +
          '<a href="' + FALLBACK_ORIGIN + '" target="_blank" rel="noopener">India Macro War Room</a>' +
        "</div>" +
      "</div>";
  }

  var STYLE = [
    ".card { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif;",
    "  color: var(--ink); background: transparent; }",
    ".card.framed { border: 1px solid var(--rule); border-radius: 10px; padding: 12px 14px 8px; }",
    ".head { display:flex; align-items:baseline; justify-content:space-between; gap:1rem; margin:0 0 2px; }",
    ".label { font-size:13px; font-weight:600; letter-spacing:-.005em; }",
    ".value { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:15px; font-variant-numeric: tabular-nums; }",
    ".unit { font-size:11px; color: var(--muted); font-weight:400; }",
    "svg { display:block; overflow:visible; }",
    ".line { fill:none; stroke: var(--accent); stroke-width:1.6; stroke-linejoin:round; stroke-linecap:round; }",
    ".area { fill: var(--fill); stroke:none; }",
    ".dot { fill: var(--accent); }",
    ".zero { stroke: var(--rule); stroke-width:1; stroke-dasharray:3 3; }",
    ".axis { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:10.5px; fill: var(--muted); }",
    ".foot { display:flex; flex-wrap:wrap; align-items:baseline; gap:0 .42rem; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size:10px; line-height:1.55; color: var(--muted); margin-top:3px; }",
    ".foot > span, .foot > a { white-space: nowrap; }",
    ".foot a { color: inherit; text-decoration: underline; text-underline-offset:2px; }",
    ".err { font-family: ui-monospace, Menlo, monospace; font-size:12px; color: var(--muted); }",
    '@media (prefers-reduced-motion: no-preference) { .dot { transition: r .2s ease; } }'
  ].join("\n");

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // -- public API ------------------------------------------------------------ //
  function embed(host, overrides) {
    var o = overrides || {};
    var id = o.series || host.getAttribute("data-imwr-series");
    if (!id) return Promise.reject(new Error("missing data-imwr-series"));
    var opts = {
      range: o.range || host.getAttribute("data-imwr-range") || "5y",
      height: parseInt(o.height || host.getAttribute("data-imwr-height") || "200", 10),
      title: o.title || host.getAttribute("data-imwr-title") || "",
      frame: (o.frame !== undefined ? o.frame : host.getAttribute("data-imwr-frame") === "on")
    };
    host.setAttribute("data-imwr-state", "loading");
    return load(id).then(function (ind) {
      var paint = function () {
        try { draw(host, ind, opts); host.setAttribute("data-imwr-state", "ready"); }
        catch (e) { fail(host, id, e); }
      };
      paint();
      if (window.ResizeObserver && !host.__imwrRO) {
        var w = 0;
        host.__imwrRO = new ResizeObserver(function (entries) {
          var cw = Math.round(entries[0].contentRect.width);
          if (Math.abs(cw - w) > 8) { w = cw; paint(); }
        });
        host.__imwrRO.observe(host);
      }
      return ind;
    }).catch(function (e) { fail(host, id, e); });
  }

  function fail(host, id, err) {
    host.setAttribute("data-imwr-state", "error");
    var root = host.shadowRoot || host.attachShadow({ mode: "open" });
    root.innerHTML = "<style>" + HOST_CSS + STYLE + "</style>" +
      '<div class="card"><div class="err">' + esc(id) + ": could not load the series (" + esc(err.message) +
      '). <a href="' + FALLBACK_ORIGIN + '">Open the dashboard</a>.</div></div>';
    if (window.console) console.warn("[imwr] " + id + ":", err);
  }

  function renderAll(scope) {
    var nodes = (scope || document).querySelectorAll("[data-imwr-series]");
    return Array.prototype.map.call(nodes, function (el) {
      if (el.getAttribute("data-imwr-state") === "ready") return null;
      return embed(el);
    });
  }

  window.IMWR = { embed: embed, render: renderAll, base: BASE };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { renderAll(document); });
  } else {
    renderAll(document);
  }
})();
