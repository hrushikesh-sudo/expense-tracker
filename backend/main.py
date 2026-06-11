"""
main.py — Flask REST API Server for FlashSpend
"""

import os
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

# NOTE: renamed to csv_parser to avoid shadowing Python's built-in 'parser' module
from csv_parser import parse_csv, to_categorised_csv, ParseError
from categories import category_store
from state import app_state
import csv
import json
from datetime import datetime

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────

# Serve the frontend (index.html / style.css / app.js) from the parent folder
FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def ok(data: dict | list, status: int = 200):
    return jsonify({"ok": True, "data": data}), status


def err(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status

# Path for the persistent local JSON
LOCAL_JSON_PATH = os.path.join(os.path.dirname(__file__), "total_expenses.json")
SETTINGS_JSON_PATH = os.path.join(os.path.dirname(__file__), "settings.json")

def read_local_totals():
    totals = []
    if os.path.exists(LOCAL_JSON_PATH):
        try:
            with open(LOCAL_JSON_PATH, "r", encoding="utf-8") as f:
                totals = json.load(f)
                if not isinstance(totals, list):
                    totals = []
        except json.JSONDecodeError:
            pass
    return totals

def write_local_totals(totals):
    with open(LOCAL_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(totals, f, indent=4)


def read_settings():
    if not os.path.exists(SETTINGS_JSON_PATH):
        return {}

    try:
        with open(SETTINGS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def write_settings(settings):
    with open(SETTINGS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)


def parse_transaction_date(date_value):
    if not date_value:
        return None

    date_str = str(date_value).strip()
    formats = [
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%Y/%m/%d",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        return None


def read_last_transaction_date():
    settings = read_settings()
    date_value = settings.get("last_transaction_date")
    parsed_date = parse_transaction_date(date_value)
    return parsed_date.strftime("%Y-%m-%d") if parsed_date else None


def write_last_transaction_date(date_value):
    parsed_date = parse_transaction_date(date_value)
    if not parsed_date:
        return None

    normalized = parsed_date.strftime("%Y-%m-%d")
    settings = read_settings()
    current_value = read_last_transaction_date()

    if current_value and current_value > normalized:
        normalized = current_value

    settings["last_transaction_date"] = normalized
    write_settings(settings)
    return normalized


def sync_last_transaction_date(transactions):
    latest_date = read_last_transaction_date()

    for tx in transactions:
        tx_date = getattr(tx, "date", None) if not isinstance(tx, dict) else tx.get("date")
        normalized = write_last_transaction_date(tx_date)
        if normalized:
            latest_date = normalized

    return latest_date


def get_latest_transaction_date():
    return read_last_transaction_date()


def get_credit_card_month_override():
    settings = read_settings()
    month_value = settings.get("credit_card_month")
    if not month_value:
        return None

    try:
        datetime.strptime(month_value, "%Y-%m")
    except ValueError:
        return None

    return month_value


def get_credit_card_name():
    settings = read_settings()
    name = settings.get("credit_card_name")
    return str(name).strip() if name else ""


def get_latest_saved_month():
    override_month = get_credit_card_month_override()
    if override_month:
        return override_month

    totals = read_local_totals()
    latest_entry = None

    for entry in totals:
        expenses = entry.get("expenses", {})
        month = entry.get("month")
        year = entry.get("year")
        if not month or not year:
            continue

        total_amount = sum(
            float(value or 0)
            for value in expenses.values()
            if isinstance(value, (int, float))
        )

        if total_amount <= 0:
            continue

        try:
            entry_date = datetime.strptime(f"{month} {year}", "%B %Y")
        except ValueError:
            continue

        if latest_entry is None or entry_date > latest_entry:
            latest_entry = entry_date

    return latest_entry.strftime("%Y-%m") if latest_entry else None


# ================================================================
# 1. CSV Upload & Parsing
# ================================================================

@app.route("/api/upload", methods=["POST"])
def upload_csv():
    """
    Upload a bank statement CSV and initialise the triage session.

    Request: multipart/form-data with field 'file' (CSV)
    Response: session summary + first transaction card
    """
    if "file" not in request.files:
        return err("No file provided. Send a multipart/form-data request with field 'file'.")

    file = request.files["file"]
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return err("Only .csv files are accepted.")

    try:
        content = file.read()
        result = parse_csv(content)
    except ParseError as exc:
        return err(str(exc))
    except Exception as exc:
        return err(f"Unexpected parse error: {exc}")

    # Load parsed data into session state
    app_state.load(
        transactions=result["transactions"],
        raw_headers=result["headers"],
        raw_rows=result["raw_rows"],
        filename=file.filename,
    )
    sync_last_transaction_date(result["transactions"])

    return ok({
        "session":     app_state.summary(),
        "current":     app_state.current_transaction.to_dict() if app_state.current_transaction else None,
    }, 201)


@app.route("/api/parse-text", methods=["POST"])
def parse_text():
    """
    Parse raw CSV text (for testing / sample data).

    Request body (JSON): { "csv": "<csv text>" }
    """
    body = request.get_json(silent=True) or {}
    csv_text = body.get("csv", "")
    if not csv_text:
        return err("Provide { \"csv\": \"<csv text>\" } in the JSON body.")

    try:
        result = parse_csv(csv_text)
    except ParseError as exc:
        return err(str(exc))

    app_state.load(
        transactions=result["transactions"],
        raw_headers=result["headers"],
        raw_rows=result["raw_rows"],
        filename="manual_input.csv",
    )
    sync_last_transaction_date(result["transactions"])

    return ok({
        "session": app_state.summary(),
        "current": app_state.current_transaction.to_dict() if app_state.current_transaction else None,
    }, 201)


# ================================================================
# 2. Session / Triage Actions
# ================================================================

@app.route("/api/session", methods=["GET"])
def get_session():
    """Return the current session summary and active flashcard."""
    return ok({
        "session": app_state.summary(),
        "current": app_state.current_transaction.to_dict() if app_state.current_transaction else None,
    })


@app.route("/api/session/reset", methods=["POST"])
def reset_session():
    """Wipe the current session and start fresh."""
    app_state.reset()
    return ok({"message": "Session reset."})


@app.route("/api/categorise", methods=["POST"])
def categorise():
    """
    Categorise the current flashcard transaction.

    Request body (JSON): { "category": "Groceries" }
    """
    if app_state.is_complete or app_state.current_transaction is None:
        return err("No active transaction. All cards have been categorised.", 409)

    body = request.get_json(silent=True) or {}
    category = body.get("category", "").strip()

    if not category:
        return err("Provide { \"category\": \"<name>\" } in the JSON body.")

    valid_names = category_store.names(active_only=False)
    if category not in valid_names:
        return err(f"Unknown category '{category}'. Valid options: {valid_names}")

    tx = app_state.categorise(category)

    return ok({
        "categorised": tx.to_dict(),
        "session":     app_state.summary(),
        "current":     app_state.current_transaction.to_dict() if app_state.current_transaction else None,
    })


@app.route("/api/skip", methods=["POST"])
def skip():
    """
    Skip the current card (tags it as Miscellaneous).

    Optionally override: { "category": "OtherFallback" }
    """
    if app_state.is_complete or app_state.current_transaction is None:
        return err("No active transaction.", 409)

    body = request.get_json(silent=True) or {}
    fallback = body.get("category", "Miscellaneous").strip()

    tx = app_state.skip(fallback)

    return ok({
        "skipped": tx.to_dict(),
        "session": app_state.summary(),
        "current": app_state.current_transaction.to_dict() if app_state.current_transaction else None,
    })


@app.route("/api/undo", methods=["POST"])
def undo():
    """Undo the last categorisation and go back one card."""
    if not app_state.history:
        return err("Nothing to undo.", 409)

    tx = app_state.undo()

    return ok({
        "restored": tx.to_dict() if tx else None,
        "session":  app_state.summary(),
        "current":  app_state.current_transaction.to_dict() if app_state.current_transaction else None,
    })


@app.route("/api/transactions", methods=["POST"])
def add_transaction():
    """
    Manually add a new transaction to the triage queue.
    """
    body = request.get_json(silent=True) or {}
    
    amount = body.get("amount", 0)
    try:
        amount = float(amount)
    except ValueError:
        return err("Amount must be a number.", 400)

    # If it's explicitly marked as debit, ensure it's negative
    if not body.get("is_credit", True) and amount > 0:
        amount = -amount

    data = {
        "date": body.get("date", ""),
        "description": body.get("description", "Manual Transaction"),
        "amount": amount,
        "is_credit": amount >= 0,
        "sent_to": body.get("description") if amount < 0 else None,
        "receive_from": body.get("description") if amount >= 0 else None,
    }

    app_state.add_manual_transaction(data)
    write_last_transaction_date(data.get("date"))

    return ok({
        "message": "Transaction added to queue.",
        "session": app_state.summary(),
        "current": app_state.current_transaction.to_dict() if app_state.current_transaction else None,
    })


# ================================================================
# 3. Results & Export
# ================================================================

@app.route("/api/results", methods=["GET"])
def get_results():
    """Return all categorised transactions and per-category totals."""
    return ok({
        "transactions": [t.to_dict() for t in app_state.categorised],
        "totals":       app_state.category_totals(),
        "session":      app_state.summary(),
    })


@app.route("/api/total_expenses", methods=["GET"])
def get_total_expenses():
    """Return the accumulated monthly totals from the local JSON."""
    totals = read_local_totals()
    return ok({"totals": totals})


@app.route("/api/header_summary", methods=["GET"])
def get_header_summary():
    """Return compact summary data for the triage header."""
    return ok({
        "last_transaction_date": get_latest_transaction_date(),
        "credit_card_name": get_credit_card_name(),
        "last_saved_month": get_latest_saved_month(),
    })


@app.route("/api/header_summary", methods=["POST"])
def update_header_summary():
    """Update editable header summary preferences."""
    body = request.get_json(silent=True) or {}
    credit_card_month = (body.get("credit_card_month") or "").strip()
    credit_card_name = (body.get("credit_card_name") or "").strip()

    if not credit_card_month:
        return err("'credit_card_month' is required.")

    try:
        datetime.strptime(credit_card_month, "%Y-%m")
    except ValueError:
        return err("credit_card_month must be in YYYY-MM format.")

    settings = read_settings()
    settings["credit_card_month"] = credit_card_month
    settings["credit_card_name"] = credit_card_name
    write_settings(settings)

    return ok({
        "last_transaction_date": get_latest_transaction_date(),
        "credit_card_name": credit_card_name,
        "last_saved_month": credit_card_month,
    })


@app.route("/api/export", methods=["GET"])
def export_csv():
    """
    Download the categorised CSV file.

    Returns the original CSV with an appended 'Category' column.
    """
    if not app_state.categorised:
        return err("No categorised transactions to export yet.", 409)

    csv_content = to_categorised_csv(
        headers=app_state.raw_headers,
        raw_rows=app_state.raw_rows,
        categorised=[t.to_dict() for t in app_state.categorised],
    )

    filename = (app_state.filename or "export").replace(".csv", "_categorised.csv")

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route("/api/save_totals", methods=["POST"])
def save_totals():
    """Accumulate current session category totals into the local JSON grouped by month."""
    if not app_state.categorised:
        return err("No categorised transactions to save yet.", 409)

    current_totals = read_local_totals()
    active_cats = category_store.names(active_only=False)
    override_month = get_credit_card_month_override()
    override_dt = None

    if override_month:
        try:
            override_dt = datetime.strptime(override_month, "%Y-%m")
        except ValueError:
            override_dt = None

    for tx in app_state.categorised:
        cat = tx.category or "Miscellaneous"
        amt = tx.amount

        if override_dt:
            month_name = override_dt.strftime("%B")
            year = override_dt.year
        else:
            parsed_dt = parse_transaction_date(tx.date)
            if parsed_dt:
                month_name = parsed_dt.strftime("%B")
                year = parsed_dt.year
            else:
                dt = datetime.now()
                month_name = dt.strftime("%B")
                year = dt.year

        entry = next((e for e in current_totals if e.get("month") == month_name and e.get("year") == year), None)
        if not entry:
            entry = {
                "month": month_name,
                "year": year,
                "expenses": {c: 0.0 for c in active_cats}
            }
            current_totals.append(entry)
            
        if cat not in entry["expenses"]:
            entry["expenses"][cat] = 0.0
            
        entry["expenses"][cat] = round(entry["expenses"][cat] + amt, 2)

    write_local_totals(current_totals)

    return ok({"message": "Local JSON updated successfully.", "totals": current_totals})


@app.route("/api/reset_totals", methods=["POST"])
def reset_totals():
    """Backup the local JSON and create a new one with all 12 months for 2026 set to 0."""
    body = request.get_json(silent=True) or {}
    backup_name = body.get("backup_name", "").strip()

    if os.path.exists(LOCAL_JSON_PATH):
        if backup_name:
            if not backup_name.endswith(".json"):
                backup_name += ".json"
            backup_path = os.path.join(os.path.dirname(__file__), backup_name)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = LOCAL_JSON_PATH.replace(".json", f"_backup_{timestamp}.json")
            
        os.rename(LOCAL_JSON_PATH, backup_path)
    
    # Initialize with 0 for all active categories
    zero_cats = {c: 0.0 for c in category_store.names(active_only=False)}
    months = ["January", "February", "March", "April", "May", "June", 
              "July", "August", "September", "October", "November", "December"]
              
    zero_totals = []
    for m in months:
        zero_totals.append({
            "month": m,
            "year": 2026,
            "expenses": zero_cats.copy()
        })
        
    write_local_totals(zero_totals)
    
    return ok({"message": "Local JSON reset successfully.", "totals": zero_totals})


# ================================================================
# 4. Category Management
# ================================================================

@app.route("/api/categories", methods=["GET"])
def list_categories():
    """
    List categories.

    Query params:
        active_only=true  — return only active categories (default: false)
    """
    active_only = request.args.get("active_only", "false").lower() == "true"
    return ok(category_store.to_list(active_only=active_only))


@app.route("/api/categories", methods=["POST"])
def add_category():
    """
    Add a new custom category.

    Request body (JSON):
        { "name": "Travel", "icon": "✈️", "color": "#0ea5e9", "key": "" }
    """
    body = request.get_json(silent=True) or {}
    name = body.get("name", "").strip()
    if not name:
        return err("'name' is required.")

    try:
        cat = category_store.add(
            name=name,
            icon=body.get("icon", "📦"),
            color=body.get("color", "#94a3b8"),
            key=body.get("key", ""),
            active=bool(body.get("active", True)),
        )
    except ValueError as exc:
        return err(str(exc))

    return ok(cat.to_dict(), 201)


@app.route("/api/categories/<name>", methods=["PATCH"])
def update_category(name: str):
    """
    Update an existing category's fields.

    Request body (JSON): any subset of { icon, color, key, active, order }
    """
    body = request.get_json(silent=True) or {}
    cat = category_store.update(name, **body)
    if cat is None:
        return err(f"Category '{name}' not found.", 404)
    return ok(cat.to_dict())


@app.route("/api/categories/<name>", methods=["DELETE"])
def delete_category(name: str):
    """Delete a category by name."""
    removed = category_store.remove(name)
    if not removed:
        return err(f"Category '{name}' not found.", 404)
    return ok({"message": f"Category '{name}' deleted."})


@app.route("/api/categories/reorder", methods=["POST"])
def reorder_categories():
    """
    Set the display order of categories.

    Request body (JSON): { "order": ["Groceries", "Dining Out", ...] }
    """
    body = request.get_json(silent=True) or {}
    order = body.get("order", [])
    if not isinstance(order, list):
        return err("'order' must be a list of category names.")
    category_store.reorder(order)
    return ok(category_store.to_list())


@app.route("/api/categories/reset", methods=["POST"])
def reset_categories():
    """Reset categories to the built-in defaults."""
    category_store.reset()
    return ok(category_store.to_list())


# ================================================================
# Frontend catch-all  (must come AFTER all /api routes)
# ================================================================

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    """
    Serve the frontend SPA.
    - Known static files (css, js, images) are served directly.
    - Everything else falls back to index.html.
    """
    target = os.path.join(FRONTEND_DIR, path)
    if path and os.path.isfile(target):
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


# ================================================================
# Health check
# ================================================================

@app.route("/api/health", methods=["GET"])
def health():
    return ok({"status": "ok", "service": "FlashSpend API"})


# ──────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
