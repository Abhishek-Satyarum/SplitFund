# backend/app.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from models.database import Base, engine, SessionLocal
from services.splitter import compute_splits
import os

app = Flask(__name__)
CORS(app)
init_db()

DB = None

def get_db():
    return get_db_connection()

# ----------------------------
# Helper DB functions
# ----------------------------
def fetchone_dict(cur):
    row = cur.fetchone()
    return dict(row) if row else None

def fetchall_dicts(cur):
    rows = cur.fetchall()
    return [dict(r) for r in rows]

# ----------------------------
# 1. create group + users
# ----------------------------
@app.route("/api/create_group", methods=["POST"])
def create_group():
    payload = request.json
    group_name = payload.get("group_name")
    members = payload.get("members", [])  # list of {name,type,size}
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO groups (group_name) VALUES (?)", (group_name,))
    group_id = cur.lastrowid
    for m in members:
        cur.execute("INSERT INTO users (group_id,name,type,family_size) VALUES (?,?,?,?)",
                    (group_id, m.get("name"), m.get("type","single"), m.get("size",1)))
        user_id = cur.lastrowid
        # create wallet_member record
        weight = 1.0
        t = m.get("type","single")
        if t == "single":
            weight = 1.0
        elif t == "couple":
            weight = 2.0
        elif t == "family":
            weight = m.get("size",4)
        cur.execute("INSERT INTO wallet_members (group_id,user_id,virtual_balance,owed_balance,weight) VALUES (?,?,?,?,?)",
                    (group_id, user_id, 0.0, 0.0, weight))
    db.commit()
    return jsonify({"ok": True, "group_id": group_id})

# ----------------------------
# create user (join existing group)
# ----------------------------
@app.route("/api/create_user", methods=["POST"])
def create_user():
    p = request.json
    group_id = p["group_id"]
    name = p["name"]
    t = p.get("type","single")
    size = p.get("size",1)
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO users (group_id,name,type,family_size) VALUES (?,?,?,?)", (group_id,name,t,size))
    uid = cur.lastrowid
    weight = 1 if t=="single" else (2 if t=="couple" else size)
    cur.execute("INSERT INTO wallet_members (group_id,user_id,virtual_balance,owed_balance,weight) VALUES (?,?,?,?,?)", (group_id, uid, 0.0, 0.0, weight))
    db.commit()
    return jsonify({"ok":True, "user_id": uid})

# ----------------------------
# add funds (contribution)
# ----------------------------
@app.route("/api/add_funds", methods=["POST"])
def add_funds():
    p = request.json
    group_id = p["group_id"]
    user_id = p["user_id"]
    amount = float(p["amount"])
    db = get_db()
    cur = db.cursor()
    # record transaction
    cur.execute("INSERT INTO transactions (group_id, actor_user_id, type, amount, meta) VALUES (?,?,?,?,?)",
                (group_id, user_id, "contribution", amount, p.get("meta","")))
    txid = cur.lastrowid
    # update wallet_members balance
    cur.execute("UPDATE wallet_members SET virtual_balance = virtual_balance + ? WHERE group_id = ? AND user_id = ?", (amount, group_id, user_id))
    db.commit()
    return jsonify({"ok": True, "txid": txid})

# ----------------------------
# record expense (initial) -> returns expense_id
# ----------------------------
@app.route("/api/record_expense", methods=["POST"])
def record_expense():
    p = request.json
    group_id = p["group_id"]
    paid_by = p["paid_by"]
    amount = float(p["amount"])
    desc = p.get("description","")
    db = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO transactions (group_id, actor_user_id, type, amount, meta) VALUES (?,?,?,?,?)",
                (group_id, paid_by, "payment", amount, desc))
    txid = cur.lastrowid
    db.commit()
    return jsonify({"ok": True, "expense_id": txid})

# ----------------------------
# add participants to expense
# ----------------------------
@app.route("/api/select_participants", methods=["POST"])
def select_participants():
    p = request.json
    expense_id = p["expense_id"]
    participants = p["participants"]  # list of dicts {user_id, share_type, weight, family_id, deferred}
    db = get_db()
    cur = db.cursor()
    # store participants in participation_records with amount_due NULL for now
    for part in participants:
        cur.execute("""INSERT INTO participation_records (transaction_id, member_user_id, amount_due, amount_deducted, share_type, weight, deferred)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (expense_id, part["user_id"], 0.0, 0.0, part.get("share_type","per_head"), part.get("weight",1.0), 1 if part.get("deferred") else 0))
    db.commit()
    return jsonify({"ok": True})

# ----------------------------
# simulate split -> compute based on participants for a given expense
# ----------------------------
@app.route("/api/simulate_split", methods=["POST"])
def simulate_split():
    p = request.json
    expense_id = p["expense_id"]
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT amount, group_id FROM transactions WHERE id = ?", (expense_id,))
    tx = cur.fetchone()
    if not tx:
        return jsonify({"ok": False, "error": "expense not found"}), 404
    amount = tx["amount"]
    # read participants we previously stored (or receive directly via payload)
    cur.execute("SELECT member_user_id, share_type, weight, deferred FROM participation_records WHERE transaction_id = ?", (expense_id,))
    parts = cur.fetchall()
    participants = []
    for r in parts:
        participants.append({
            "user_id": r["member_user_id"],
            "share_type": r["share_type"],
            "weight": r["weight"],
            "deferred": bool(r["deferred"]),
            "family_id": None
        })
    splits, deferred = compute_splits(amount, participants)
    return jsonify({"ok": True, "splits": splits, "deferred": deferred})

# ----------------------------
# commit payment: apply split and update balances
# ----------------------------
@app.route("/api/commit_payment", methods=["POST"])
def commit_payment():
    p = request.json
    expense_id = p["expense_id"]
    db = get_db()
    cur = db.cursor()
    # fetch tx
    cur.execute("SELECT amount, group_id, actor_user_id FROM transactions WHERE id = ?", (expense_id,))
    tx = cur.fetchone()
    if not tx:
        return jsonify({"ok": False, "error": "expense not found"}), 404
    amount = tx["amount"]
    group_id = tx["group_id"]
    actor_user_id = tx["actor_user_id"]
    # fetch participants records
    cur.execute("SELECT id, member_user_id, share_type, weight, deferred FROM participation_records WHERE transaction_id = ?", (expense_id,))
    rows = cur.fetchall()
    participants = []
    for r in rows:
        participants.append({
            "user_id": r["member_user_id"],
            "share_type": r["share_type"],
            "weight": r["weight"],
            "deferred": bool(r["deferred"])
        })
    splits, deferred_list = compute_splits(amount, participants)

    # Begin atomic updates
    try:
        # For simplicity: actor paid outside app; we deduct owed amounts from each participant's virtual_balance.
        # If deferred -> increment owed_balance for that member but do NOT deduct virtual_balance.
        for r in rows:
            uid = r["member_user_id"]
            due = float(splits.get(uid, 0.0))
            is_deferred = bool(r["deferred"])
            if is_deferred:
                # add to owed_balance; participation record: amount_due=due, amount_deducted=0
                cur.execute("UPDATE wallet_members SET owed_balance = owed_balance + ? WHERE group_id = ? AND user_id = ?", (due, group_id, uid))
                cur.execute("UPDATE participation_records SET amount_due = ?, amount_deducted = ? WHERE transaction_id = ? AND member_user_id = ?",
                            (due, 0.0, expense_id, uid))
            else:
                # deduct from virtual_balance (may go negative if insufficient)
                cur.execute("UPDATE wallet_members SET virtual_balance = virtual_balance - ? WHERE group_id = ? AND user_id = ?", (due, group_id, uid))
                cur.execute("UPDATE participation_records SET amount_due = ?, amount_deducted = ? WHERE transaction_id = ? AND member_user_id = ?",
                            (due, due, expense_id, uid))
        db.commit()
    except Exception as e:
        db.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True, "splits": splits})

# ----------------------------
# repay debt (simple)
# ----------------------------
@app.route("/api/repay", methods=["POST"])
def repay():
    p = request.json
    group_id = p["group_id"]
    user_id = p["user_id"]
    amount = float(p["amount"])
    db = get_db()
    cur = db.cursor()
    # record repayment transaction
    cur.execute("INSERT INTO transactions (group_id, actor_user_id, type, amount, meta) VALUES (?, ?, ?, ?, ?)",
                (group_id, user_id, "repayment", amount, p.get("meta","repay")))
    txid = cur.lastrowid
    # reduce owed_balance and increase virtual_balance (we credit the wallet or user's virtual balance)
    cur.execute("UPDATE wallet_members SET owed_balance = owed_balance - ?, virtual_balance = virtual_balance + ? WHERE group_id = ? AND user_id = ?",
                (amount, amount, group_id, user_id))
    db.commit()
    return jsonify({"ok": True, "txid": txid})

# ----------------------------
# group summary
# ----------------------------
@app.route("/api/group_summary", methods=["GET"])
def group_summary():
    group_id = request.args.get("group_id")
    db = get_db()
    cur = db.cursor()
    cur.execute("""
        SELECT u.id user_id, u.name, wm.virtual_balance, wm.owed_balance, wm.weight
        FROM users u JOIN wallet_members wm ON u.id = wm.user_id
        WHERE wm.group_id = ?
    """, (group_id,))
    rows = cur.fetchall()
    return jsonify([dict(r) for r in rows])

# ----------------------------
# transactions list for group
# ----------------------------
@app.route("/api/transactions", methods=["GET"])
def transactions():
    group_id = request.args.get("group_id")
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM transactions WHERE group_id = ? ORDER BY created_at DESC", (group_id,))
    return jsonify([dict(r) for r in cur.fetchall()])

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))

