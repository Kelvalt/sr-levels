from flask import Flask, request, jsonify, Response
import csv
import os
import json
import sqlite3
import git
from datetime import datetime
from contextlib import contextmanager

app = Flask(__name__)

REPO_PATH = os.path.expanduser("~/sr-levels")
DATA_PATH = os.path.join(REPO_PATH, "data")
DB_PATH   = os.path.join(REPO_PATH, "levels.db")
PINE_PATH = os.path.join(REPO_PATH, "universal_levels.pine")


# ---------- DATABASE ----------
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                ticker TEXT PRIMARY KEY,
                current_price REAL,
                levels_below TEXT,
                levels_above TEXT,
                updated_at TEXT
            )
        """)

@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def save_ticker(ticker, current_price, levels_below, levels_above):
    with db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO tickers
            (ticker, current_price, levels_below, levels_above, updated_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ticker, current_price,
            json.dumps(levels_below), json.dumps(levels_above),
            datetime.now().isoformat()
        ))
        conn.commit()

def get_ticker(ticker):
    with db() as conn:
        row = conn.execute("SELECT * FROM tickers WHERE ticker = ?", (ticker,)).fetchone()
        if not row:
            return None
        return {
            "ticker":        row["ticker"],
            "current_price": row["current_price"],
            "levels_below":  json.loads(row["levels_below"]),
            "levels_above":  json.loads(row["levels_above"]),
            "updated_at":    row["updated_at"],
        }

def all_tickers():
    with db() as conn:
        rows = conn.execute("SELECT * FROM tickers ORDER BY ticker").fetchall()
        return [{
            "ticker":        r["ticker"],
            "current_price": r["current_price"],
            "levels_below":  json.loads(r["levels_below"]),
            "levels_above":  json.loads(r["levels_above"]),
            "updated_at":    r["updated_at"],
        } for r in rows]


# ---------- CSV (GitHub backup) ----------
def write_csv(ticker, current_price, levels_below, levels_above):
    filepath = os.path.join(DATA_PATH, f"{ticker}.csv")
    with open(filepath, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "current_price", "level", "type"])
        for lvl in levels_below:
            w.writerow([ticker, current_price, lvl, "support"])
        for lvl in levels_above:
            w.writerow([ticker, current_price, lvl, "resistance"])
    print(f"[{datetime.now()}] Wrote CSV: {filepath}")


# ---------- UNIVERSAL PINE SCRIPT GENERATOR ----------
def generate_pine():
    tickers = all_tickers()

    max_below = max((len(t["levels_below"]) for t in tickers), default=0) or 5
    max_above = max((len(t["levels_above"]) for t in tickers), default=0) or 5

    header = '''//@version=6
indicator("Universal S/R Levels", overlay=true, max_labels_count=500)

supportColor    = input.color(color.green, "Support")
resistanceColor = input.color(color.red,   "Resistance")
lineWidth       = input.int(1, "Line width", minval=1)

ticker = syminfo.ticker

'''

    var_decls = ""
    for i in range(max_below):
        var_decls += f"float b{i+1} = na\n"
    for i in range(max_above):
        var_decls += f"float a{i+1} = na\n"
    var_decls += "\n"

    body = ""
    if not tickers:
        body = "// No tickers loaded yet\n"
    for i, t in enumerate(tickers):
        kw = "if" if i == 0 else "else if"
        body += f'{kw} ticker == "{t["ticker"]}"\n'
        assigned_any = False
        for j, lvl in enumerate(t["levels_below"]):
            body += f'    b{j+1} := {lvl}\n'
            assigned_any = True
        for j, lvl in enumerate(t["levels_above"]):
            body += f'    a{j+1} := {lvl}\n'
            assigned_any = True
        if not assigned_any:
            body += '    na\n'

    plots = "\n"
    for i in range(max_below):
        plots += f'plot(b{i+1}, color=supportColor, linewidth=lineWidth, title="Support {i+1}", style=plot.style_line)\n'
    for i in range(max_above):
        plots += f'plot(a{i+1}, color=resistanceColor, linewidth=lineWidth, title="Resistance {i+1}", style=plot.style_line)\n'

    labels = '\nif barstate.islast\n'
    for i in range(max_below):
        labels += f'    if not na(b{i+1})\n'
        labels += f'        label.new(bar_index, b{i+1}, str.tostring(b{i+1}), style=label.style_label_left, textcolor=supportColor, color=color.new(color.white, 100), size=size.small)\n'
    for i in range(max_above):
        labels += f'    if not na(a{i+1})\n'
        labels += f'        label.new(bar_index, a{i+1}, str.tostring(a{i+1}), style=label.style_label_left, textcolor=resistanceColor, color=color.new(color.white, 100), size=size.small)\n'

    return header + var_decls + body + plots + labels

def write_pine():
    script = generate_pine()
    with open(PINE_PATH, "w") as f:
        f.write(script)
    print(f"[{datetime.now()}] Wrote Pine Script: {PINE_PATH}")


# ---------- GIT ----------
def git_push(ticker):
    try:
        repo = git.Repo(REPO_PATH)
        repo.git.add(A=True)
        repo.index.commit(f"update {ticker} {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        repo.remote(name="origin").push()
        print(f"[{datetime.now()}] Pushed to GitHub")
    except Exception as e:
        print(f"Git push error: {e}")


# ---------- ENDPOINTS ----------
@app.route("/levels", methods=["POST"])
def receive_levels():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data"}), 400

    ticker        = (data.get("ticker") or "").strip().upper()
    current_price = data.get("current_price")
    levels_below  = data.get("levels_below", []) or []
    levels_above  = data.get("levels_above", []) or []

    if not ticker or current_price is None:
        return jsonify({"error": "Missing ticker or current_price"}), 400
    if not isinstance(levels_below, list) or not isinstance(levels_above, list):
        return jsonify({"error": "levels_below and levels_above must be arrays"}), 400

    save_ticker(ticker, current_price, levels_below, levels_above)
    write_csv(ticker, current_price, levels_below, levels_above)
    write_pine()
    git_push(ticker)
    return jsonify({"status": "success", "ticker": ticker}), 200

@app.route("/levels/<ticker>", methods=["GET"])
def get_levels(ticker):
    data = get_ticker(ticker.upper())
    if not data:
        return jsonify({"error": "Ticker not found"}), 404
    return jsonify(data)

@app.route("/levels", methods=["GET"])
def list_levels():
    return jsonify(all_tickers())

@app.route("/pine", methods=["GET"])
def get_pine():
    return Response(generate_pine(), mimetype="text/plain")

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status":       "running",
        "timestamp":    datetime.now().isoformat(),
        "ticker_count": len(all_tickers()),
    }), 200


# ---------- CORS ----------
@app.after_request
def cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


if __name__ == "__main__":
    init_db()
    write_pine()
    app.run(host="0.0.0.0", port=5000, debug=True)
