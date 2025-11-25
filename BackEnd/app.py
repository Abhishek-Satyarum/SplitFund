# backend/app.py

from flask import Flask, request, jsonify
from models.database import Base, engine, SessionLocal
from models.users import User
from models.wallet import Wallet
from models.transactions import Transaction
from logic.splitter import equal_split, ratio_split

app = Flask(__name__)

# Create all tables
Base.metadata.create_all(bind=engine)

# Helper: create DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ----------------------------------------------------
# 1. CREATE GROUP
# ----------------------------------------------------
@app.route("/group/create", methods=["POST"])
def create_group():
    data = request.json
    group_id = data.get("group_id")
    members = data.get("members")

    if not group_id or not members:
        return jsonify({"error": "group_id and members required"}), 400

    db = SessionLocal()

    for m in members:
        # Create user
        user = User(name=m)
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create wallet entry
        wallet = Wallet(user_id=user.id, group_id=group_id, balance=0)
        db.add(wallet)
        db.commit()

    db.close()

    return jsonify({"message": "Group created successfully!"}), 200


# ----------------------------------------------------
# 2. ADD MONEY TO WALLET
# ----------------------------------------------------
@app.route("/wallet/add", methods=["POST"])
def add_money():
    data = request.json

    name = data.get("name")
    group_id = data.get("group_id")
    amount = data.get("amount")

    if not name or not group_id or amount is None:
        return jsonify({"error": "name, group_id, amount required"}), 400

    db = SessionLocal()

    user = db.query(User).filter(User.name == name).first()
    if not user:
        db.close()
        return jsonify({"error": "User not found"}), 404

    wallet = (
        db.query(Wallet)
        .filter(Wallet.group_id == group_id, Wallet.user_id == user.id)
        .first()
    )

    if not wallet:
        db.close()
        return jsonify({"error": "Wallet not found"}), 404

    wallet.balance += amount
    db.commit()
    db.close()

    return jsonify({"message": "Balance added successfully!"}), 200


# ----------------------------------------------------
# 3. ADD EXPENSE & SPLIT
# ----------------------------------------------------
@app.route("/expense/split", methods=["POST"])
def split_expense():
    data = request.json

    group_id = data.get("group_id")
    payer = data.get("payer")
    participants = data.get("participants")
    amount = data.get("amount")
    split_type = data.get("split_type")

    if not all([group_id, payer, participants, amount, split_type]):
        return jsonify({"error": "Missing fields"}), 400

    db = SessionLocal()

    # Perform split calculation
    if split_type == "equal":
        split_result = equal_split(amount, participants)
    elif split_type == "ratio":
        split_result = ratio_split(amount, data.get("ratio"))
    else:
        db.close()
        return jsonify({"error": "Invalid split_type"}), 400

    # Deduct from each participant wallet
    for name, deduction in split_result.items():
        user = db.query(User).filter(User.name == name).first()
        wallet = db.query(Wallet).filter(
            Wallet.user_id == user.id, Wallet.group_id == group_id
        ).first()

        wallet.balance -= deduction

    # Add transaction record
    transaction = Transaction(
        group_id=group_id,
        payer=payer,
        participants=",".join(participants),
        total_amount=amount,
        split_type=split_type,
        details=str(split_result),
    )

    db.add(transaction)
    db.commit()
    db.close()

    return jsonify({"message": "Expense split successfully!"}), 200


# ----------------------------------------------------
# 4. GROUP SUMMARY (Balance of Each Member)
# ----------------------------------------------------
@app.route("/group/summary/<int:group_id>", methods=["GET"])
def group_summary(group_id):
    db = SessionLocal()

    wallets = db.query(Wallet).filter(Wallet.group_id == group_id).all()
    summary = {}

    for wallet in wallets:
        user = db.query(User).filter(User.id == wallet.user_id).first()
        summary[user.name] = wallet.balance

    db.close()

    return jsonify(summary), 200


# ----------------------------------------------------
# RUN SERVER
# ----------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
