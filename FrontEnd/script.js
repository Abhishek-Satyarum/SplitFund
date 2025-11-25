const BASE_URL = "http://127.0.0.1:5000";

// ---------------------------
// CREATE GROUP
// ---------------------------
async function createGroup() {
    let group_id = document.getElementById("group_id").value;
    let members = document.getElementById("members").value.split(",").map(m => m.trim());

    let res = await fetch(`${BASE_URL}/group/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_id, members })
    });

    alert("Group created successfully!");
}


// ---------------------------
// ADD MONEY
// ---------------------------
async function addMoney() {
    let name = document.getElementById("w_name").value;
    let group_id = document.getElementById("w_group").value;
    let amount = document.getElementById("w_amount").value;

    let res = await fetch(`${BASE_URL}/wallet/add`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, group_id, amount })
    });

    alert("Wallet updated!");
}


// ---------------------------
// GET SUMMARY
// ---------------------------
async function getSummary() {
    let group = document.getElementById("sum_group").value;

    let res = await fetch(`${BASE_URL}/group/summary/${group}`);
    let data = await res.json();

    document.getElementById("summary_output").innerText =
        JSON.stringify(data, null, 4);
}


// ---------------------------
// ADD EXPENSE
// ---------------------------
async function addExpense() {
    let group_id = document.getElementById("e_group").value;
    let payer = document.getElementById("e_payer").value;
    let participants = document.getElementById("e_participants").value.split(",").map(m=>m.trim());
    let amount = document.getElementById("e_amount").value;
    let split_type = document.getElementById("e_split").value;

    let payload = {
        group_id,
        payer,
        participants,
        amount,
        split_type
    };

    if (split_type === "ratio") {
        payload.ratio = JSON.parse(document.getElementById("e_ratio").value);
    }

    let res = await fetch(`${BASE_URL}/expense/split`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });

    alert("Expense added!");
}
