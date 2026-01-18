from __future__ import annotations

import os
import secrets
from typing import Dict, List, Optional

from flask import Flask, render_template_string, request, url_for

from amazon import scrape_amazon
from bulk_parser import _parse_specifics_line, parse_bulk_items
from ebay import list_on_ebay
from ui_bridge import IOBridge

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY") or secrets.token_hex(32)


class MissingPrompt(Exception):
    """Raised when backend logic requests interactive input that was not supplied."""

    def __init__(self, prompt: str):
        super().__init__(prompt)
        self.prompt = prompt


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
        if default:
            self.log(f"{prompt} (using default)")
            return default
        raise MissingPrompt(prompt)

    def prompt_choice(self, prompt: str, options: List[str]) -> Optional[str]:
        key = self._norm_key(prompt)
        if key in self.prompt_answers and self.prompt_answers[key] in options:
            return self.prompt_answers[key]
        if options:
            self.log(f"{prompt} (auto-selected {options[0]})")
            return options[0]
        raise MissingPrompt(prompt)

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
    body { font-family: Arial, sans-serif; margin: 0 auto; max-width: 960px; padding: 24px; background: #f7f7f7; }
    h1 { margin-top: 0; }
    section { background: #fff; padding: 16px; margin-bottom: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    label { display: block; margin: 8px 0 4px; font-weight: bold; }
    input[type="text"], input[type="number"], textarea { width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px; }
    textarea { min-height: 120px; }
    .actions { margin-top: 12px; }
    button { padding: 10px 16px; border: none; background: #0b5ed7; color: #fff; border-radius: 4px; cursor: pointer; }
    button:hover { background: #0a53be; }
    .result { background: #e9f5ff; padding: 12px; border-radius: 6px; margin-top: 8px; }
    .error { background: #ffe5e5; color: #8b0000; padding: 12px; border-radius: 6px; }
    pre { background: #111; color: #0f0; padding: 12px; border-radius: 6px; overflow-x: auto; }
    ul { padding-left: 20px; }
    .small { color: #555; font-size: 0.9em; }
  </style>
</head>
<body>
  <h1>Amazon → eBay Bot (Web)</h1>
  <p class="small">This page runs the existing Python backend through a browser-based UI.</p>

  <section>
    <h2>Single Item</h2>
    <form method="post" action="{{ url_for('handle_single') }}">
      <label for="amazon_url">Amazon URL *</label>
      <input id="amazon_url" name="amazon_url" type="text" required value="{{ single_form.amazon_url }}">

      <label for="quantity">Quantity</label>
      <input id="quantity" name="quantity" type="number" min="1" value="{{ single_form.quantity }}">

      <label for="note">Seller note (optional)</label>
      <input id="note" name="note" type="text" value="{{ single_form.note }}">

      <label for="custom_specifics">Custom specifics (e.g., Size: XL | Colour: Black)</label>
      <input id="custom_specifics" name="custom_specifics" type="text" value="{{ single_form.custom_specifics }}">

      <label for="title_override">Fallback title (used if scraping returns none)</label>
      <input id="title_override" name="title_override" type="text" value="{{ single_form.title_override }}">

      <label for="price_override">Fallback price (used if scraping returns none)</label>
      <input id="price_override" name="price_override" type="text" value="{{ single_form.price_override }}">

      <div class="actions">
        <label><input type="checkbox" name="list_on_ebay" {% if single_form.list_on_ebay %}checked{% endif %}> List on eBay after scrape</label>
        <button type="submit">Run</button>
      </div>
    </form>
  </section>

  <section>
    <h2>Bulk Items</h2>
    <form method="post" action="{{ url_for('handle_bulk') }}">
      <label for="bulk_text">Bulk text</label>
      <textarea id="bulk_text" name="bulk_text">{{ bulk_form.bulk_text }}</textarea>
      <div class="actions">
        <label><input type="checkbox" name="bulk_list_on_ebay" {% if bulk_form.bulk_list_on_ebay %}checked{% endif %}> List on eBay after scrape</label>
        <button type="submit">Process Bulk</button>
      </div>
    </form>
  </section>

  {% if error %}
    <section class="error">
      <strong>Error:</strong> {{ error }}
    </section>
  {% endif %}

  {% if single_result %}
    <section>
      <h3>Single Item Result</h3>
      <div class="result">
        <div><strong>Title:</strong> {{ single_result.title }}</div>
        <div><strong>Price:</strong> {{ single_result.price }}</div>
        <div><strong>URL:</strong> <a href="{{ single_result.url }}" target="_blank">{{ single_result.url }}</a></div>
        <div><strong>Listed on eBay:</strong> {{ "Yes" if single_result.listed else "No" }}</div>
        {% if single_result.item_id %}
          <div><strong>Item ID:</strong> {{ single_result.item_id }}</div>
        {% endif %}
      </div>
    </section>
  {% endif %}

  {% if bulk_results %}
    <section>
      <h3>Bulk Results</h3>
      <ul>
        {% for res in bulk_results %}
          <li>
            <div><strong>{{ loop.index }}.</strong> {{ res.url }} — {{ res.title or "Title pending" }} (Listed: {{ "Yes" if res.listed else "No" }})</div>
            {% if res.item_id %}
              <div class="small">Item ID: {{ res.item_id }}</div>
            {% endif %}
            {% if res.error %}
              <div class="error">Error: {{ res.error }}</div>
            {% endif %}
            {% if res.logs %}
              <details>
                <summary>Logs</summary>
                <pre>{{ res.logs|join("\n") }}</pre>
              </details>
            {% endif %}
          </li>
        {% endfor %}
      </ul>
    </section>
  {% endif %}

  {% if opened_urls %}
    <section>
      <h3>Action Needed</h3>
      <ul>
        {% for u in opened_urls %}
          <li><a href="{{ u }}" target="_blank">{{ u }}</a></li>
        {% endfor %}
      </ul>
    </section>
  {% endif %}

  {% if logs %}
    <section>
      <h3>Backend Logs</h3>
      <pre>{{ logs|join("\n") }}</pre>
    </section>
  {% endif %}
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


def _build_prompt_answers(form) -> Dict[str, str]:
    answers = {}
    if form.get("title_override"):
        answers["what is the title:"] = form["title_override"]
    if form.get("price_override"):
        answers["what is the price:"] = form["price_override"]
    if form.get("quantity"):
        answers["what is the quantity:"] = form["quantity"]
    return answers


@app.route("/", methods=["GET"])
def index():
    return render_template_string(
        TEMPLATE,
        single_form={"amazon_url": "", "quantity": 1, "note": "", "custom_specifics": "", "title_override": "", "price_override": "", "list_on_ebay": False},
        bulk_form={"bulk_text": "", "bulk_list_on_ebay": False},
        single_result=None,
        bulk_results=None,
        logs=[],
        error=None,
        opened_urls=[],
    )


@app.route("/single", methods=["POST"])
def handle_single():
    form = request.form
    url = (form.get("amazon_url") or "").strip()
    quantity = form.get("quantity") or "1"
    note = form.get("note") or ""
    custom_specifics = _parse_custom_specifics(form.get("custom_specifics", ""))
    prompt_answers = _build_prompt_answers(form)
    io = WebIOBridge(prompt_answers=prompt_answers)

    error = None
    product = {}
    listing = None

    if not url:
        error = "Amazon URL is required."
    else:
        try:
            product = scrape_amazon(url, note, quantity, custom_specifics, io)
            if form.get("list_on_ebay"):
                listing = list_on_ebay(product, io)
        except MissingPrompt as mp:
            error = f"Additional input required: {mp.prompt}"
        except Exception:
            app.logger.exception("Single item processing failed")
            error = "An unexpected error occurred. Please verify the Amazon URL and try again, or check server logs."

    single_result = None
    if product:
        single_result = {
            "title": product.get("Title"),
            "price": product.get("Price"),
            "url": product.get("URL"),
            "listed": bool(listing and listing.get("ok")),
            "item_id": listing.get("item_id") if listing else None,
        }

    return render_template_string(
        TEMPLATE,
        single_form={
            "amazon_url": url,
            "quantity": quantity,
            "note": note,
            "custom_specifics": form.get("custom_specifics", ""),
            "title_override": form.get("title_override", ""),
            "price_override": form.get("price_override", ""),
            "list_on_ebay": bool(form.get("list_on_ebay")),
        },
        bulk_form={"bulk_text": "", "bulk_list_on_ebay": False},
        single_result=single_result,
        bulk_results=None,
        logs=io.logs,
        error=error,
        opened_urls=io.opened_urls,
    )


@app.route("/bulk", methods=["POST"])
def handle_bulk():
    form = request.form
    bulk_text = form.get("bulk_text", "")
    list_on_ebay_flag = bool(form.get("bulk_list_on_ebay"))
    bulk_results = []
    opened_urls: List[str] = []

    try:
        for item in parse_bulk_items(bulk_text):
            io = WebIOBridge()
            try:
                product = scrape_amazon(
                    item.get("url", ""),
                    item.get("note", ""),
                    item.get("quantity", 1),
                    item.get("custom_specifics", {}),
                    io,
                )
                listing = list_on_ebay(product, io) if list_on_ebay_flag else None
                bulk_results.append(
                    {
                        "url": item.get("url"),
                        "title": product.get("Title"),
                        "listed": bool(listing and listing.get("ok")),
                        "item_id": listing.get("item_id") if listing else None,
                        "logs": io.logs,
                        "error": None,
                    }
                )
            except MissingPrompt as mp:
                bulk_results.append(
                    {
                        "url": item.get("url"),
                        "title": None,
                        "listed": False,
                        "item_id": None,
                        "logs": io.logs,
                        "error": f"Additional input required: {mp.prompt}",
                    }
                )
            except Exception:
                app.logger.exception("Bulk item processing failed")
                bulk_results.append(
                    {
                        "url": item.get("url"),
                        "title": None,
                        "listed": False,
                        "item_id": None,
                        "logs": io.logs,
                        "error": "Unexpected error for this item. Verify the Amazon URL/quantity and retry. See server logs for details.",
                    }
                )
            opened_urls.extend(io.opened_urls)
    except Exception:
        app.logger.exception("Bulk text parsing failed")
        return render_template_string(
            TEMPLATE,
            single_form={"amazon_url": "", "quantity": 1, "note": "", "custom_specifics": "", "title_override": "", "price_override": "", "list_on_ebay": False},
            bulk_form={"bulk_text": bulk_text, "bulk_list_on_ebay": list_on_ebay_flag},
            single_result=None,
            bulk_results=None,
            logs=[],
            error="Bulk processing failed. Ensure the bulk text follows the documented format and check server logs.",
            opened_urls=opened_urls,
        )

    return render_template_string(
        TEMPLATE,
        single_form={"amazon_url": "", "quantity": 1, "note": "", "custom_specifics": "", "title_override": "", "price_override": "", "list_on_ebay": False},
        bulk_form={"bulk_text": bulk_text, "bulk_list_on_ebay": list_on_ebay_flag},
        single_result=None,
        bulk_results=bulk_results,
        logs=[],
        error=None,
        opened_urls=opened_urls,
    )


def run():
    host = os.getenv("HOST", "127.0.0.1")
    app.logger.warning("Running built-in Flask development server; use a production WSGI server (e.g., gunicorn) for deployment.")
    if host == "0.0.0.0":
        app.logger.warning("HOST=0.0.0.0 will expose the app on all interfaces; ensure this is intentional and secured.")
    app.run(host=host, port=int(os.getenv("PORT", 5000)), debug=False)


if __name__ == "__main__":
    run()
