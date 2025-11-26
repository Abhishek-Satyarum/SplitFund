# backend/app.py
import sys
import os
import logging
from flask import Flask, request, jsonify
from sqlalchemy import func
from flask_cors import CORS
import ast


# add backend folder to path (if needed)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# import your models/logic (ensure these modules exist)
from models.database import Base, engine, SessionLocal
from models.users import User
from models.wallet import Wallet
from models.transactions import Transaction
from Logic.splitter import equal_split, ratio_split

# -----------------------
# Setup
# -----------------------
app = Flask(__name__)

# Development-friendly CORS: allow frontend origins. For production, lock this down.
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

# logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("splitfund")

# create tables if not created
Base.metadata.create_all(bind=engine)


def make_error(message, code=400, extra=None):
    payload = {"error": str(message)}
    if extra and isinstance(extra, dict):
        payload.update(extra)
    return jsonify(payload), code


def parse_int(val, default=None):
    try:
        return int(val)
    except Exception:
        return default


# -----------------------
# Root
# -----------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "message": "SplitFund API is running!",
        "endpoints": {
            "create_group": "POST /group/create",
            "add_money": "POST /wallet/add",
            "split_expense": "POST /expense/split",
            "group_summary": "GET /group/summary/<group_id>"
        }
    }), 200


# -----------------------
# CREATE GROUP
# Accepts members as a list of either strings or objects
# object format: { name: "Alice", type: "single|couple|family", head_count: <int> }
# -----------------------
@app.route("/group/create", methods=["POST", "OPTIONS"])
def create_group():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(force=True, silent=True) or {}
    group_id_raw = data.get("group_id")
    members = data.get("members")

    if group_id_raw is None or not members:
        return make_error("group_id and members required", 400)

    group_id = parse_int(group_id_raw)
    if group_id is None:
        return make_error("invalid group_id (must be integer)", 400)

    db = SessionLocal()
    try:
        for m in members:
            # support both object and string member entries
            name = None
            head_count = 1

            if isinstance(m, dict):
                name = (m.get("name") or "").strip()
                m_type = (m.get("type") or "single").lower()
                if m_type == "single":
                    head_count = 1
                elif m_type == "couple":
                    head_count = 2
                elif m_type == "family":
                    # family should supply head_count explicitly
                    heads = m.get("head_count")
                    try:
                        head_count = int(heads)
                        if head_count < 1:
                            head_count = 1
                    except Exception:
                        db.rollback()
                        return make_error(f"family type requires valid head_count for member '{name}'", 400)
                else:
                    db.rollback()
                    return make_error(f"Invalid member type '{m_type}' for member '{name}'", 400)
            else:
                name = str(m).strip()
                head_count = 1

            if not name:
                # skip empty names
                continue

            # reuse existing user if present (case-insensitive)
            user = db.query(User).filter(func.lower(User.name) == name.lower()).first()
            if not user:
                user = User(name=name)
                db.add(user)
                db.commit()
                db.refresh(user)

            # check for existing wallet in this group
            # existing_wallet = db.query(Wallet).filter(Wallet.user_id == user.id, Wallet.group_id == group_id).first()
            # if existing_wallet:
            #     # update head_count if changed
            #     if getattr(existing_wallet, "head_count", 1) != head_count:
            #         existing_wallet.head_count = head_count
            #         db.commit()
            #     continue

            # # create new wallet
            # wallet = Wallet(user_id=user.id, group_id=group_id, balance=0.0, head_count=head_count)
            # db.add(wallet)
            # db.commit()

        return jsonify({"message": "Group created successfully!"}), 200

    except Exception as e:
        logger.exception("Error in create_group")
        db.rollback()
        return make_error("Internal server error while creating group", 500, {"details": str(e)})
    finally:
        db.close()


# -----------------------
# ADD MONEY
# Payload options:
#  - { wallet_id: <int>, amount: <num> }
#  - { name: <str>, group_id: <int>, amount: <num> }
# -----------------------
@app.route("/wallet/add", methods=["POST", "OPTIONS"])
def add_money():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(force=True, silent=True) or {}
    wallet_id = data.get("wallet_id")
    amount_raw = data.get("amount")

    if amount_raw is None:
        return make_error("amount required", 400)

    try:
        amount = float(amount_raw)
    except Exception:
        return make_error("invalid amount; must be numeric", 400)

    db = SessionLocal()
    try:
        wallet = None
        if wallet_id is not None:
            wid = parse_int(wallet_id)
            if wid is None:
                return make_error("invalid wallet_id", 400)
            wallet = db.query(Wallet).filter(Wallet.id == wid).first()
            if not wallet:
                return make_error("Wallet not found", 404)
        else:
            name = data.get("name")
            group_id_raw = data.get("group_id")
            if not name or group_id_raw is None:
                return make_error("name and group_id required when wallet_id not provided", 400)

            gid = parse_int(group_id_raw)
            if gid is None:
                return make_error("invalid group_id", 400)

            # try exact name first then case-insensitive trimmed name
            wallet = (
                db.query(Wallet)
                .join(User, Wallet.user_id == User.id)
                .filter(User.name == name, Wallet.group_id == gid)
                .first()
            )
            if not wallet:
                wallet = (
                    db.query(Wallet)
                    .join(User, Wallet.user_id == User.id)
                    .filter(func.lower(User.name) == name.strip().lower(), Wallet.group_id == gid)
                    .first()
                )
            if not wallet:
                existing = (
                    db.query(User.name)
                    .join(Wallet, Wallet.user_id == User.id)
                    .filter(Wallet.group_id == gid)
                    .all()
                )
                existing_names = [e[0] for e in existing]
                return make_error("Wallet not found", 404, {
                    "hint": f"No wallet found for user '{name}' in group {gid}",
                    "existing_members_in_group": existing_names
                })

        # update balance
        wallet.balance = (wallet.balance or 0) + amount
        db.commit()
        return jsonify({"message": "Balance added successfully!"}), 200

    except Exception as e:
        logger.exception("Error in add_money")
        db.rollback()
        return make_error("Internal server error while adding money", 500, {"details": str(e)})
    finally:
        db.close()


# -----------------------
# SPLIT EXPENSE
# -----------------------
@app.route("/expense/split", methods=["POST", "OPTIONS"])
def split_expense():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(force=True, silent=True) or {}
    group_id_raw = data.get("group_id")
    payer = data.get("payer")
    participants = data.get("participants")
    amount_raw = data.get("amount")
    split_type = data.get("split_type")
    category = data.get("category")
    ratio = data.get("ratio")

    # normalize participants if string -> list
    if isinstance(participants, str):
        participants = [p.strip() for p in participants.split(",") if p.strip()]

    if group_id_raw is None or not payer or not participants or amount_raw is None or not split_type:
        return make_error("Missing fields. Required: group_id, payer, participants, amount, split_type", 400)

    group_id = parse_int(group_id_raw)
    if group_id is None:
        return make_error("invalid group_id", 400)

    try:
        amount = float(amount_raw)
    except Exception:
        return make_error("invalid amount", 400)

    # convert ratio string -> dict if necessary
    if split_type == "ratio" and isinstance(ratio, str):
        try:
            ratio = ast.literal_eval(ratio)
        except Exception:
            return make_error("Invalid ratio format", 400)

    db = SessionLocal()
    try:
        if split_type == "equal":
            split_result = equal_split(amount, participants)
        elif split_type == "ratio":
            split_result = ratio_split(amount, ratio)
        else:
            return make_error("Invalid split_type", 400)

        # Deduct from each participant wallet
        for name, deduction in split_result.items():
            wallet = (
                db.query(Wallet)
                .join(User, Wallet.user_id == User.id)
                .filter(func.lower(User.name) == name.lower(), Wallet.group_id == group_id)
                .first()
            )
            if not wallet:
                db.rollback()
                return make_error(f"Wallet for user '{name}' not found in group {group_id}", 404)

            wallet.balance = (wallet.balance or 0) - float(deduction)

        # Safe transaction record
        transaction = Transaction(
            group_id=group_id,
            payer=payer,
            participants=",".join([str(p) for p in participants]),
            total_amount=amount,
            split_type=split_type,
            details=str(split_result),
            category=category,
        )
        db.add(transaction)
        db.commit()
        return jsonify({"message": "Expense split successfully!"}), 200

    except Exception as e:
        logger.exception("Error in split_expense")
        db.rollback()
        return make_error("Internal server error while splitting expense", 500, {"details": str(e)})
    finally:
        db.close()


# -----------------------
# GROUP SUMMARY
# -----------------------
@app.route("/group/summary/<int:group_id>", methods=["GET"])
def group_summary(group_id):
    db = SessionLocal()
    try:
        wallets = db.query(Wallet).filter(Wallet.group_id == group_id).all()
        summary = {}
        members = []
        for wallet in wallets:
            user = db.query(User).filter(User.id == wallet.user_id).first()
            if not user:
                continue
            summary[user.name] = wallet.balance
            members.append({
                "user_id": user.id,
                "wallet_id": wallet.id,
                "name": user.name,
                "balance": wallet.balance,
                "head_count": getattr(wallet, "head_count", 1),
            })
        return jsonify({"summary": summary, "members": members}), 200
    except Exception as e:
        logger.exception("Error in group_summary")
        return make_error("Internal server error while fetching group summary", 500, {"details": str(e)})
    finally:
        db.close()


# -----------------------
# DETAILED GROUP SUMMARY
# -----------------------
@app.route("/group/summary/detailed/<int:group_id>", methods=["GET"])
def group_summary_detailed(group_id):
    db = SessionLocal()
    try:
        wallets = db.query(Wallet).filter(Wallet.group_id == group_id).all()
        transactions = db.query(Transaction).filter(Transaction.group_id == group_id).all()

        result = {}
        for wallet in wallets:
            user = db.query(User).filter(User.id == wallet.user_id).first()
            if not user:
                continue
            result[user.name] = {
                "present_balance": wallet.balance,
                "total_spent": 0.0,
                "spent_where": [],
                "paid_for": [],
            }

        for tx in transactions:
            try:
                details_map = ast.literal_eval(tx.details) if tx.details else {}
            except Exception:
                details_map = {}

            for name, deduction in details_map.items():
                if name in result:
                    result[name]["total_spent"] += float(deduction)
                    result[name]["spent_where"].append({
                        "payer": tx.payer,
                        "total_amount": tx.total_amount,
                        "category": tx.category,
                        "split_type": tx.split_type,
                        "deduction": deduction,
                        "participants": tx.participants,
                        "details": tx.details,
                    })
            if tx.payer in result:
                result[tx.payer]["paid_for"].append({
                    "total_amount": tx.total_amount,
                    "category": tx.category,
                    "participants": tx.participants,
                    "details": tx.details,
                })

        for name, info in result.items():
            info["initial_balance_estimate"] = float(info["present_balance"]) + float(info["total_spent"])

        return jsonify(result), 200

    except Exception as e:
        logger.exception("Error in group_summary_detailed")
        return make_error("Internal server error while fetching detailed summary", 500, {"details": str(e)})
    finally:
        db.close()


# -----------------------
# Global error handler (optional, useful for debugging)
# -----------------------
@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled 500")
    return make_error("Internal server error", 500, {"details": str(e)})


# -----------------------
# Run server
# -----------------------
if __name__ == "__main__":
    # DEFAULT PORT: 5500 to match your frontend requests (change if needed)
    app.run(debug=False, host="0.0.0.0", port=5500, use_reloader=False, threaded=True)