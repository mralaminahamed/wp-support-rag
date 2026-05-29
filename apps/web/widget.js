/*
 * WP Plugin Support Desk RAG — embeddable widget (FR-DL-2/3).
 * Author: Al Amin Ahamed.
 *
 * Single-file, build-free web component. Embed with one script tag:
 *
 *   <script src="https://your-host/widget.js"
 *           data-plugin-slug="swift-menu-duplicator"
 *           data-api-base="https://your-api-host"></script>
 *
 * It posts questions to {api-base}/api/v1/query, renders the cited answer, and
 * posts helpful/not-helpful feedback to {api-base}/api/v1/feedback. When the
 * provider is down the API returns a degraded answer with links, which the
 * widget shows as-is (fail-open, FR-GN-6).
 */
(function () {
  "use strict";

  var script = document.currentScript;
  var PLUGIN_SLUG = script ? script.getAttribute("data-plugin-slug") : null;
  var API_BASE = (script && script.getAttribute("data-api-base")) || "";

  var STYLE = "\
:host{all:initial;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;display:block}\
.box{max-width:640px;border:1px solid #d9dce1;border-radius:12px;padding:16px;background:#fff}\
.row{display:flex;gap:8px}\
input{flex:1;padding:10px 12px;border:1px solid #c4c8ce;border-radius:8px;font-size:14px}\
button{padding:10px 14px;border:0;border-radius:8px;background:#2563eb;color:#fff;font-size:14px;cursor:pointer}\
button[disabled]{opacity:.6;cursor:default}\
.answer{margin-top:14px;white-space:pre-wrap;line-height:1.5;font-size:14px;color:#1f2937}\
.notice{margin-top:14px;padding:10px 12px;border-radius:8px;background:#fef3c7;color:#92400e;font-size:13px}\
.sources{margin-top:10px;font-size:13px}\
.sources a{display:block;color:#2563eb;text-decoration:none;margin:2px 0}\
.cited::before{content:'\\2713 ';color:#16a34a}\
.fb{margin-top:12px;display:flex;gap:8px;align-items:center;font-size:13px;color:#6b7280}\
.fb button{background:#f3f4f6;color:#374151}\
.muted{color:#6b7280;font-size:12px;margin-top:8px}";

  var TEMPLATE = "\
<div class='box'>\
  <div class='row'>\
    <input type='text' part='input' placeholder='Ask a question about this plugin…' />\
    <button class='ask'>Ask</button>\
  </div>\
  <div class='out' aria-live='polite'></div>\
  <div class='muted'>Answers are generated from documentation and may be imperfect.</div>\
</div>";

  function el(html) {
    var t = document.createElement("template");
    t.innerHTML = html;
    return t.content.firstElementChild;
  }

  class WPSupportWidget extends HTMLElement {
    connectedCallback() {
      if (this._mounted) return;
      this._mounted = true;
      this.pluginSlug = this.getAttribute("data-plugin-slug") || PLUGIN_SLUG;
      this.apiBase = this.getAttribute("data-api-base") || API_BASE;

      var root = this.attachShadow({ mode: "open" });
      var style = document.createElement("style");
      style.textContent = STYLE;
      root.appendChild(style);
      root.appendChild(el(TEMPLATE));

      this.input = root.querySelector("input");
      this.askButton = root.querySelector(".ask");
      this.out = root.querySelector(".out");

      this.askButton.addEventListener("click", this.ask.bind(this));
      this.input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") this.ask();
      }.bind(this));
    }

    async ask() {
      var question = this.input.value.trim();
      if (!question) return;
      this.askButton.disabled = true;
      this.out.innerHTML = "<div class='muted'>Searching the docs…</div>";
      try {
        var streamed = await this.streamAsk(question);
        if (!streamed) await this.fetchAsk(question);
      } catch (err) {
        this.out.innerHTML = "<div class='notice'>Could not reach the support service. Please try again.</div>";
      } finally {
        this.askButton.disabled = false;
      }
    }

    async fetchAsk(question) {
      var res = await fetch(this.apiBase + "/api/v1/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question, plugin_slug: this.pluginSlug }),
      });
      if (!res.ok) throw new Error("HTTP " + res.status);
      this.render(await res.json());
    }

    // Stream tokens via SSE; returns false to signal fallback to fetchAsk.
    async streamAsk(question) {
      var res;
      try {
        res = await fetch(this.apiBase + "/api/v1/query/stream", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: question, plugin_slug: this.pluginSlug }),
        });
      } catch (e) {
        return false;
      }
      if (!res.ok || !res.body) return false;

      this.out.innerHTML = "";
      var answer = el("<div class='answer'></div>");
      this.out.appendChild(answer);

      var reader = res.body.getReader();
      var decoder = new TextDecoder();
      var buffer = "";
      var live = "";
      while (true) {
        var step = await reader.read();
        if (step.done) break;
        buffer += decoder.decode(step.value, { stream: true });
        var frames = buffer.split("\n\n");
        buffer = frames.pop();
        for (var i = 0; i < frames.length; i++) {
          var parsed = parseSSE(frames[i]);
          if (!parsed) continue;
          if (parsed.event === "token") {
            live += parsed.data.text || "";
            answer.textContent = live; // provisional render
          } else if (parsed.event === "done") {
            this.render(parsed.data); // replace with citation-validated answer
          }
        }
      }
      return true;
    }

    render(data) {
      this.out.innerHTML = "";
      if (data.degraded) {
        this.out.appendChild(el("<div class='notice'>" + escapeHtml(data.answer) + "</div>"));
      } else {
        this.out.appendChild(el("<div class='answer'>" + escapeHtml(data.answer) + "</div>"));
      }
      if (data.sources && data.sources.length) {
        var sources = el("<div class='sources'></div>");
        data.sources.forEach(function (s) {
          var a = document.createElement("a");
          a.href = s.url;
          a.target = "_blank";
          a.rel = "noopener noreferrer";
          a.textContent = s.heading_path ? s.heading_path + " — " + s.url : s.url;
          if (s.cited) a.className = "cited";
          sources.appendChild(a);
        });
        this.out.appendChild(sources);
      }
      if (!data.declined && data.query_id) this.renderFeedback(data.query_id);
    }

    renderFeedback(queryId) {
      var self = this;
      var fb = el("<div class='fb'><span>Was this helpful?</span></div>");
      [["helpful", "Yes"], ["not_helpful", "No"]].forEach(function (pair) {
        var b = document.createElement("button");
        b.textContent = pair[1];
        b.addEventListener("click", function () {
          self.sendFeedback(queryId, pair[0], fb);
        });
        fb.appendChild(b);
      });
      this.out.appendChild(fb);
    }

    async sendFeedback(queryId, rating, container) {
      try {
        await fetch(this.apiBase + "/api/v1/feedback", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query_id: queryId, rating: rating }),
        });
        container.innerHTML = "<span>Thanks for the feedback.</span>";
      } catch (err) {
        container.innerHTML = "<span>Could not record feedback.</span>";
      }
    }
  }

  function parseSSE(frame) {
    var event = "message";
    var data = "";
    frame.split("\n").forEach(function (line) {
      if (line.indexOf("event:") === 0) event = line.slice(6).trim();
      else if (line.indexOf("data:") === 0) data += line.slice(5).trim();
    });
    if (!data) return null;
    try {
      return { event: event, data: JSON.parse(data) };
    } catch (e) {
      return null;
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  if (!customElements.get("wp-support-widget")) {
    customElements.define("wp-support-widget", WPSupportWidget);
  }

  // Auto-mount one instance from the script tag's attributes (single-tag embed).
  if (script && PLUGIN_SLUG && !script.hasAttribute("data-no-autoload")) {
    var mount = document.createElement("wp-support-widget");
    mount.setAttribute("data-plugin-slug", PLUGIN_SLUG);
    if (API_BASE) mount.setAttribute("data-api-base", API_BASE);
    script.parentNode.insertBefore(mount, script.nextSibling);
  }
})();
