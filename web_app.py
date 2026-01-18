from __future__ import annotations

import os
import secrets
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template_string, request

from amazon import scrape_amazon
from bulk_parser import _parse_specifics_line, parse_bulk_items
from ebay import list_on_ebay
from ui_bridge import IOBridge

def _load_secret_key() -> str:
    env_key = os.getenv("SECRET_KEY")
    if env_key:
        return env_key
    key_path = os.path.join(os.path.dirname(__file__), ".flask_secret_key")
    if os.path.exists(key_path):
        with open(key_path, "r", encoding="utf-8") as fh:
            existing = fh.read().strip()
            if existing:
                return existing
    generated = secrets.token_hex(32)
    with open(key_path, "w", encoding="utf-8") as fh:
        fh.write(generated)
    return generated


app = Flask(__name__)
app.config["SECRET_KEY"] = _load_secret_key()


class MissingPrompt(Exception):
    """Raised when backend logic requests interactive input that was not supplied."""

    def __init__(self, prompt: str, options: Optional[List[str]] = None, default: str = ""):
        super().__init__(prompt)
        self.prompt = prompt
        self.options = options or []
        self.default = default


class WebIOBridge(IOBridge):
    """
    IO bridge that captures logs and consumes pre-supplied prompt answers so core
    logic can run without a desktop UI.
    """

    def __init__(self, prompt_answers: Optional[Dict[str, str]] = None):
        super().__init__()
        prompt_answers = prompt_answers or {}
        self.prompt_answers = {self._norm_key(k): v for k, v in prompt_answers.items()}
        self.logs: List[str] = []
        self.opened_urls: List[str] = []

    @staticmethod
    def _norm_key(prompt: str) -> str:
        return prompt.strip().lower()

    def log(self, msg: str):
        self.logs.append(str(msg))

    def prompt_text(self, prompt: str, default: str = "") -> str:
        key = self._norm_key(prompt)
        if key in self.prompt_answers:
            return str(self.prompt_answers[key])
        raise MissingPrompt(prompt, default=default)

    def prompt_choice(self, prompt: str, options: List[str]) -> Optional[str]:
        key = self._norm_key(prompt)
        if key in self.prompt_answers and self.prompt_answers[key] in options:
            return self.prompt_answers[key]
        raise MissingPrompt(prompt, options=options)

    def open_url(self, url: str):
        self.opened_urls.append(url)
        self.log(f"Open in browser: {url}")


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Amazon → eBay Bot (Web)</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0 auto; max-width: 1040px; padding: 24px; background: #f7f7f7; }
    h1 { margin-top: 0; }
    section { background: #fff; padding: 16px; margin-bottom: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    label { display: block; margin: 8px 0 4px; font-weight: bold; }
    input[type="text"], input[type="number"], textarea, select { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
    textarea { min-height: 120px; }
    .actions { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
    button { padding: 10px 16px; border: none; background: #0b5ed7; color: #fff; border-radius: 4px; cursor: pointer; }
    button:hover { background: #0a53be; }
    .panel { background: #fff; padding: 12px; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.08); margin-bottom: 12px; }
    .result { background: #e9f5ff; padding: 12px; border-radius: 6px; margin-top: 8px; }
    .error { background: #ffe5e5; color: #8b0000; padding: 12px; border-radius: 6px; }
    pre { background: #111; color: #0f0; padding: 12px; border-radius: 6px; overflow-x: auto; }
    ul { padding-left: 20px; }
    .small { color: #555; font-size: 0.9em; }
    .hidden { display: none; }
    #prompt-panel { border: 1px dashed #0b5ed7; }
    #status-text { font-weight: bold; }
  </style>
</head>
<body>
  <h1>Amazon → eBay Bot (Web)</h1>
  <p class="small">This page runs the existing Python backend through a browser-based UI with live prompts and logs.</p>

  <section>
    <h2>Single Item</h2>
    <form id="single-form">
      <label for="amazon_url">Amazon URL *</label>
      <input id="amazon_url" name="amazon_url" type="text" required>

      <label for="quantity">Quantity</label>
      <input id="quantity" name="quantity" type="number" min="1" value="1">

      <label for="note">Seller note (optional)</label>
      <input id="note" name="note" type="text">

      <label for="custom_specifics">Custom specifics (e.g., Size: XL | Colour: Black)</label>
      <input id="custom_specifics" name="custom_specifics" type="text">

      <label for="title_override">Fallback title (used if scraping returns none)</label>
      <input id="title_override" name="title_override" type="text">

      <label for="price_override">Fallback price (used if scraping returns none)</label>
      <input id="price_override" name="price_override" type="text">

      <div class="actions">
        <label><input type="checkbox" id="list_on_ebay"> List on eBay after scrape</label>
        <button type="submit" id="single-run">Run</button>
      </div>
    </form>
    <div id="single-result" class="panel hidden"></div>
  </section>

  <section>
    <h2>Bulk Items</h2>
    <form id="bulk-form">
      <label for="bulk_text">Bulk text</label>
      <textarea id="bulk_text" name="bulk_text"></textarea>
      <div class="actions">
        <label><input type="checkbox" id="bulk_list_on_ebay"> List on eBay after scrape</label>
        <button type="submit" id="bulk-run">Process Bulk</button>
      </div>
    </form>
    <div id="bulk-results" class="panel hidden"></div>
  </section>

  <section id="prompt-panel" class="panel hidden">
    <h3>Input Required</h3>
    <div id="prompt-text"></div>
    <div id="prompt-input-wrapper">
      <input type="text" id="prompt-input">
      <select id="prompt-select" class="hidden"></select>
    </div>
    <div class="actions">
      <button id="prompt-submit" type="button">Submit</button>
    </div>
  </section>

  <section class="panel">
    <div id="status-text"></div>
    <div id="error-box" class="error hidden"></div>
    <div id="opened-wrapper" class="hidden">
      <h3>Action Needed</h3>
      <ul id="opened-urls"></ul>
    </div>
    <div>
      <h3>Backend Logs</h3>
      <pre id="logs"></pre>
    </div>
  </section>

  <script>
    const singleState = { promptAnswers: {} };
    const bulkState = { promptAnswers: {}, results: [], nextIndex: 0 };

    const statusText = document.getElementById('status-text');
    const errorBox = document.getElementById('error-box');
    const logsEl = document.getElementById('logs');
    const openedWrapper = document.getElementById('opened-wrapper');
    const openedUrlsEl = document.getElementById('opened-urls');

    const promptPanel = document.getElementById('prompt-panel');
    const promptText = document.getElementById('prompt-text');
    const promptInput = document.getElementById('prompt-input');
    const promptSelect = document.getElementById('prompt-select');
    const promptSubmit = document.getElementById('prompt-submit');

    function setStatus(msg) {
      statusText.textContent = msg || '';
    }

    function setError(msg) {
      if (msg) {
        errorBox.textContent = msg;
        errorBox.classList.remove('hidden');
      } else {
        errorBox.textContent = '';
        errorBox.classList.add('hidden');
      }
    }

    function renderLogs(logs) {
      logsEl.textContent = (logs || []).join('\\n');
    }

    function renderOpened(urls) {
      if (urls && urls.length) {
        openedWrapper.classList.remove('hidden');
        openedUrlsEl.innerHTML = '';
        urls.forEach(u => {
          const li = document.createElement('li');
          const a = document.createElement('a');
          a.href = u;
          a.textContent = u;
          a.target = '_blank';
          li.appendChild(a);
          openedUrlsEl.appendChild(li);
        });
      } else {
        openedWrapper.classList.add('hidden');
        openedUrlsEl.innerHTML = '';
      }
    }

    function renderSingleResult(res) {
      const container = document.getElementById('single-result');
      if (!res) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
      }
      container.classList.remove('hidden');
      container.innerHTML = `
        <h3>Single Item Result</h3>
        <div class="result">
          <div><strong>Title:</strong> ${res.product?.Title || ''}</div>
          <div><strong>Price:</strong> ${res.product?.Price || ''}</div>
          <div><strong>URL:</strong> ${res.product?.URL ? `<a href="${res.product.URL}" target="_blank">${res.product.URL}</a>` : ''}</div>
          <div><strong>Listed on eBay:</strong> ${res.listing && res.listing.ok ? 'Yes' : 'No'}</div>
          ${res.listing?.item_id ? `<div><strong>Item ID:</strong> ${res.listing.item_id}</div>` : ''}
        </div>
      `;
    }

    function renderBulkResults(results) {
      const container = document.getElementById('bulk-results');
      if (!results || !results.length) {
        container.classList.add('hidden');
        container.innerHTML = '';
        return;
      }
      container.classList.remove('hidden');
      const items = results.map((r, idx) => {
        const logsBlock = r.logs?.length ? `<details><summary>Logs</summary><pre>${r.logs.join('\\n')}</pre></details>` : '';
        const errorBlock = r.error ? `<div class="error">Error: ${r.error}</div>` : '';
        const listed = r.listing && r.listing.ok ? 'Yes' : 'No';
        const itemId = r.listing?.item_id ? `<div class="small">Item ID: ${r.listing.item_id}</div>` : '';
        const status = r.status ? `<div class="small"><strong>Status:</strong> ${r.status}</div>` : '';
        return `<li>
            <div><strong>${idx + 1}.</strong> ${r.url || ''} — ${r.product?.Title || 'Title pending'} (Listed: ${listed})</div>
            ${status}
            ${itemId}
            ${errorBlock}
            ${logsBlock}
          </li>`;
      }).join('');
      container.innerHTML = `<h3>Bulk Results</h3><ul>${items}</ul>`;
    }

    function showPrompt(prompt, options = [], defaultVal = '') {
      return new Promise(resolve => {
        promptText.textContent = prompt;
        promptInput.value = defaultVal || '';
        promptSelect.innerHTML = '';
        if (options && options.length) {
          promptSelect.classList.remove('hidden');
          promptInput.classList.add('hidden');
          options.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt;
            o.textContent = opt;
            promptSelect.appendChild(o);
          });
        } else {
          promptSelect.classList.add('hidden');
          promptInput.classList.remove('hidden');
        }
        promptPanel.classList.remove('hidden');
        promptInput.focus();
        promptSubmit.onclick = () => {
          const val = options && options.length ? promptSelect.value : promptInput.value;
          promptPanel.classList.add('hidden');
          resolve(val);
        };
      });
    }

    async function callApi(path, payload) {
      const res = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {})
      });
      return res.json();
    }

    async function submitSingle(ev) {
      ev.preventDefault();
      setError('');
      setStatus('Running single item...');
      renderOpened([]);
      renderLogs([]);
      renderSingleResult(null);
      const payload = {
        amazon_url: document.getElementById('amazon_url').value.trim(),
        quantity: document.getElementById('quantity').value || '1',
        note: document.getElementById('note').value,
        custom_specifics: document.getElementById('custom_specifics').value,
        title_override: document.getElementById('title_override').value,
        price_override: document.getElementById('price_override').value,
        list_on_ebay: document.getElementById('list_on_ebay').checked,
        prompt_answers: singleState.promptAnswers
      };

      while (true) {
        const data = await callApi('/api/single', payload);
        renderLogs(data.logs);
        renderOpened(data.opened_urls);
        if (data.status === 'prompt') {
          const answer = await showPrompt(data.prompt, data.options, data.default);
          singleState.promptAnswers[data.prompt] = answer;
          payload.prompt_answers = singleState.promptAnswers;
          continue;
        }
        if (data.status === 'error') {
          setError(data.error);
          setStatus('Single item failed.');
          break;
        }
        if (data.status === 'ok') {
          setError('');
          renderSingleResult({ product: data.product, listing: data.listing });
          setStatus('Single item completed.');
          break;
        }
        break;
      }
    }

    async function submitBulk(ev) {
      ev.preventDefault();
      setError('');
      setStatus('Running bulk...');
      renderOpened([]);
      renderLogs([]);
      bulkState.results = [];
      bulkState.nextIndex = 0;
      const basePayload = {
        bulk_text: document.getElementById('bulk_text').value,
        list_on_ebay: document.getElementById('bulk_list_on_ebay').checked
      };

      while (true) {
        const payload = {
          ...basePayload,
          prompt_answers: bulkState.promptAnswers,
          start_index: bulkState.nextIndex
        };
        const data = await callApi('/api/bulk', payload);
        if (data.results && data.results.length) {
          bulkState.results.push(...data.results);
        }
        renderLogs(data.logs);
        renderOpened(data.opened_urls);
        renderBulkResults(bulkState.results);
        if (data.status === 'prompt') {
          const answer = await showPrompt(data.prompt, data.options, data.default);
          bulkState.promptAnswers[data.prompt] = answer;
          bulkState.nextIndex = data.next_index || 0;
          continue;
        }
        if (data.status === 'error') {
          setError(data.error);
          setStatus('Bulk failed.');
          break;
        }
        if (data.status === 'ok') {
          setError('');
          setStatus('Bulk completed.');
          bulkState.nextIndex = 0;
          break;
        }
        break;
      }
    }

    document.getElementById('single-form').addEventListener('submit', submitSingle);
    document.getElementById('bulk-form').addEventListener('submit', submitBulk);
  </script>
</body>
</html>
"""


def _parse_custom_specifics(text: str) -> Dict[str, str]:
    specifics = {}
    if not text:
        return specifics
    parsed = _parse_specifics_line(text)
    if parsed:
        specifics.update(parsed)
    return specifics


@app.route("/", methods=["GET"])
def index():
    return render_template_string(TEMPLATE)


@app.post("/api/single")
def api_single():
    payload = request.get_json(force=True, silent=True) or {}
    prompt_answers = payload.get("prompt_answers") or {}
    io = WebIOBridge(prompt_answers=prompt_answers)

    url = (payload.get("amazon_url") or "").strip()
    if not url:
        return jsonify({"status": "error", "error": "Amazon URL is required.", "logs": io.logs, "opened_urls": []})

    quantity = payload.get("quantity") or "1"
    note = payload.get("note") or ""
    custom_specifics = _parse_custom_specifics(payload.get("custom_specifics", ""))
    title_override = payload.get("title_override")
    price_override = payload.get("price_override")
    if title_override:
        prompt_answers["what is the title:"] = title_override
    if price_override:
        prompt_answers["what is the price:"] = price_override

    try:
        product = scrape_amazon(url, note, quantity, custom_specifics, io)
        listing = None
        if payload.get("list_on_ebay"):
            listing = list_on_ebay(product, io)
        return jsonify({"status": "ok", "product": product, "listing": listing, "logs": io.logs, "opened_urls": io.opened_urls})
    except MissingPrompt as mp:
        app.logger.info("Additional input required: %s", mp.prompt)
        return jsonify(
            {
                "status": "prompt",
                "prompt": mp.prompt,
                "options": mp.options,
                "default": mp.default,
                "logs": io.logs,
                "opened_urls": io.opened_urls,
            }
        )
    except Exception:
        app.logger.exception("Single item processing failed")
        return jsonify(
            {
                "status": "error",
                "error": "An unexpected error occurred. Please verify the Amazon URL and try again, or check server logs.",
                "logs": io.logs,
                "opened_urls": io.opened_urls,
            }
        )


@app.post("/api/bulk")
def api_bulk():
    payload = request.get_json(force=True, silent=True) or {}
    bulk_text = payload.get("bulk_text", "")
    list_on_ebay_flag = bool(payload.get("list_on_ebay"))
    prompt_answers = payload.get("prompt_answers") or {}
    start_index = int(payload.get("start_index") or 0)

    results = []
    opened_urls: List[str] = []
    combined_logs: List[str] = []

    try:
        items = parse_bulk_items(bulk_text)
        for idx, item in enumerate(items[start_index:], start_index):
            io = WebIOBridge(prompt_answers=prompt_answers)
            try:
                product = scrape_amazon(
                    item.get("url", ""),
                    item.get("note", ""),
                    item.get("quantity", 1),
                    item.get("custom_specifics", {}),
                    io,
                )
                listing = list_on_ebay(product, io) if list_on_ebay_flag else None
                results.append(
                    {
                        "url": item.get("url"),
                        "product": product,
                        "listing": listing,
                        "logs": io.logs,
                        "status": "ok",
                        "error": None,
                    }
                )
            except MissingPrompt as mp:
                app.logger.info("Bulk item additional input required: %s", mp.prompt)
                results.append(
                    {
                        "url": item.get("url"),
                        "product": None,
                        "listing": None,
                        "logs": io.logs,
                        "status": "prompt",
                        "error": "Additional input required to continue. Please provide the missing configuration.",
                    }
                )
                opened_urls.extend(io.opened_urls)
                combined_logs.extend(io.logs)
                return jsonify(
                    {
                        "status": "prompt",
                        "prompt": mp.prompt,
                        "options": mp.options,
                        "default": mp.default,
                        "results": results,
                        "next_index": idx,
                        "opened_urls": opened_urls,
                        "logs": combined_logs,
                        "current_item_url": item.get("url"),
                    }
                )
            except Exception:
                app.logger.exception("Bulk item processing failed")
                results.append(
                    {
                        "url": item.get("url"),
                        "product": None,
                        "listing": None,
                        "logs": io.logs,
                        "status": "error",
                        "error": "Unexpected error for this item. Verify the Amazon URL/quantity and retry. See server logs for details.",
                    }
                )
            opened_urls.extend(io.opened_urls)
            combined_logs.extend(io.logs)
        return jsonify({"status": "ok", "results": results, "opened_urls": opened_urls, "logs": combined_logs})
    except Exception:
        app.logger.exception("Bulk text parsing failed")
        return jsonify(
            {
                "status": "error",
                "error": "Bulk processing failed. Ensure the bulk text follows the documented format and check server logs.",
                "results": results,
                "opened_urls": opened_urls,
                "logs": combined_logs,
            }
        )


def run():
    host = os.getenv("HOST", "127.0.0.1")
    app.logger.warning("Running built-in Flask development server; use a production WSGI server (e.g., gunicorn) for deployment.")
    if host == "0.0.0.0":
        if os.getenv("ALLOW_BIND_ALL", "").lower() != "true":
            raise RuntimeError("Binding to 0.0.0.0 requires ALLOW_BIND_ALL=true to acknowledge exposure.")
        app.logger.warning("HOST=0.0.0.0 will expose the app on all interfaces; ensure this is intentional and secured.")
    app.run(host=host, port=int(os.getenv("PORT", 5000)), debug=False)


if __name__ == "__main__":
    run()
