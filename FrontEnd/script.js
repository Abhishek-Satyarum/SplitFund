// Ensure this matches the backend server port (BackEnd/app.py runs on port 5500)
const BASE_URL = "http://127.0.0.1:5500";
const DEBUG = false; // set true during local debugging
const log = (...a) => { if (DEBUG) console.log(...a); };
const err = (...a) => { if (DEBUG) console.error(...a); };

// Safe fetch helper: returns an object { ok, status, body }
// body is parsed JSON when possible, otherwise raw text


async function fetchJsonSafe(url, opts) {
    const res = await fetch(url, opts);
    const status = res.status;
    const ok = res.ok;

    // always try to read as text first
    const text = await res.text();
    let body = null;
    try {
        body = JSON.parse(text);
    } catch (e) {
        // not JSON — return raw text so callers can display helpful debug info
        body = text;
    }

    return { res, ok, status, body };
}

// ---------------------------
// CREATE GROUP
// ---------------------------
async function createGroup() {
    let group_id = document.getElementById("group_id").value;
    // support new UI where members are added individually into groupMembers array
    let members = [];
    if (Array.isArray(window.groupMembers) && window.groupMembers.length > 0) {
        members = window.groupMembers.map(m => (typeof m === 'string') ? m : (m.name || '')).filter(Boolean);
    } else {
        // backward compatibility: parse comma-separated names
        members = document.getElementById("members") ? document.getElementById("members").value.split(",").map(m => m.trim()).filter(Boolean) : [];
    }

    if (!group_id || members.length === 0) {
        alert("Please enter group ID and members!");
        return;
    }

    // perform create-group request
    try {
        const { res, ok, status, body } = await fetchJsonSafe(`${BASE_URL}/group/create`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ group_id, members })
        });

        if (ok) {
            alert("Group created successfully!");
            try { sessionStorage.setItem('current_group', String(group_id)); } catch(e) {}
            log("Response:", body);
        } else {
            const msg = (typeof body === 'object' && body.error) ? body.error : (typeof body === 'string' ? body : 'Failed to create group');
            alert("Error: " + msg);
            err("Error response:", body);
        }
    } catch (error) {
        alert("Error: " + error.message);
        err("Fetch error:", error);
    }
}
// Group member helper UI was removed to keep frontend minimal.


// ---------------------------
// ADD MONEY
// ---------------------------
async function addMoney() {
    let name = document.getElementById("w_name").value;
    let group_id = document.getElementById("w_group").value;
    let amount = document.getElementById("w_amount").value;

    if (!name || !group_id) {
        alert("Please fill name and group id!");
        return;
    }

    // allow zero amounts; make sure amount is numeric and non-negative
    amount = parseFloat(amount);
    if (isNaN(amount) || amount < 0) {
        alert('Please enter a non-negative amount (0 allowed)');
        return;
    }

    try {
        const { res, ok, status, body } = await fetchJsonSafe(`${BASE_URL}/wallet/add`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, group_id: parseInt(group_id, 10), amount: amount })
        });

        // manual add does not have per-row status; any responses are shown via debug panel

        let data = body;

        // surface response in the on-page debug panel
        showLastResponse({ status: status, ok: ok, body: data });

        if (ok) {
            alert("Wallet updated!");
            log("Response:", data);
        } else {
            let msg = (typeof data === 'object' && data.error) ? data.error : (typeof data === 'string' ? data : 'Failed to add money');
            if (status === 404) {
                if (typeof data === 'object' && data.hint) msg += '\n' + data.hint;
                if (typeof data === 'object' && Array.isArray(data.existing_members_in_group)) msg += '\nMembers in group: ' + data.existing_members_in_group.join(', ');
            }
            alert('Error: ' + msg);
            err("Error response:", data);
        }
    } catch (error) {
        alert("Error: " + error.message);
        err("Fetch error:", error);
    }
}


// ---------------------------
// GET SUMMARY
// ---------------------------
async function getSummary() {
    let group = document.getElementById("sum_group").value;

    if (!group) {
        alert("Please enter group ID!");
        return;
    }

    try {
        // Call the new detailed summary endpoint
        const { res, ok, status, body } = await fetchJsonSafe(`${BASE_URL}/group/summary/detailed/${group}`);
        let data = body;

        if (ok) {
            let html = '';
            
            for (let user in data) {
                let u = data[user];
                
                // Balance info cards
                html += `<div class="user-section">`;
                html += `<div class="user-title">👤 ${user}</div>`;
                html += `<div class="balance-info">`;
                html += `<div class="balance-card"><label>Initial Balance</label><div class="value">₹${parseFloat(u.initial_balance_estimate).toFixed(2)}</div></div>`;
                html += `<div class="balance-card"><label>Total Spent</label><div class="value">₹${parseFloat(u.total_spent).toFixed(2)}</div></div>`;
                html += `<div class="balance-card"><label>Present Balance</label><div class="value">₹${parseFloat(u.present_balance).toFixed(2)}</div></div>`;
                html += `</div>`;
                
                // Spent Where Table
                if (u.spent_where && u.spent_where.length > 0) {
                    html += `<h4 style="margin-top: 15px; margin-bottom: 8px;">💸 Expenses Incurred</h4>`;
                    html += `<table><thead><tr><th>Payer</th><th>Category</th><th>Your Share</th><th>Total Amount</th><th>Participants</th></tr></thead><tbody>`;
                    u.spent_where.forEach(s => {
                        html += `<tr><td>${s.payer}</td><td>${s.category || 'N/A'}</td><td>₹${parseFloat(s.deduction).toFixed(2)}</td><td>₹${parseFloat(s.total_amount).toFixed(2)}</td><td>${s.participants}</td></tr>`;
                    });
                    html += `</tbody></table>`;
                } else {
                    html += `<h4 style="margin-top: 15px; color: #999;">💸 Expenses Incurred</h4><p style="color: #999;">No expenses recorded</p>`;
                }
                
                // Paid For Table
                if (u.paid_for && u.paid_for.length > 0) {
                    html += `<h4 style="margin-top: 15px; margin-bottom: 8px;">💰 Payments Made</h4>`;
                    html += `<table><thead><tr><th>Category</th><th>Total Amount</th><th>Participants</th></tr></thead><tbody>`;
                    u.paid_for.forEach(p => {
                        html += `<tr><td>${p.category || 'N/A'}</td><td>₹${parseFloat(p.total_amount).toFixed(2)}</td><td>${p.participants}</td></tr>`;
                    });
                    html += `</tbody></table>`;
                } else {
                    html += `<h4 style="margin-top: 15px; color: #999;">💰 Payments Made</h4><p style="color: #999;">No payments recorded</p>`;
                }
                
                html += `</div><hr style="margin: 30px 0;">`;
            }
            
            document.getElementById("summary_output").innerHTML = html;
            log("Detailed Summary:", data);
        } else {
            alert("Error: " + (data.error || "Failed to get summary"));
            err("Error response:", data);
        }
    } catch (error) {
        alert("Error: " + error.message);
        err("Fetch error:", error);
    }
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
    let category = document.getElementById("e_category") ? document.getElementById("e_category").value : null;

    if (!group_id || !payer || participants.length === 0 || !amount || !split_type) {
        alert("Please fill all fields!");
        return;
    }

    let payload = {
        group_id: parseInt(group_id),
        payer,
        participants,
        amount: parseFloat(amount),
        split_type
    };

    if (category) payload.category = category;

    if (split_type === "ratio") {
        try {
            payload.ratio = JSON.parse(document.getElementById("e_ratio").value);
        } catch (e) {
            alert("Invalid ratio JSON format!");
            return;
        }
    }

    try {
        const { res, ok, status, body } = await fetchJsonSafe(`${BASE_URL}/expense/split`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        let data = body;

        if (ok) {
            alert("Expense added!");
            log("Response:", data);
        } else {
            const msg = (typeof data === 'object' && data.error) ? data.error : (typeof data === 'string' ? data : 'Failed to add expense');
            alert("Error: " + msg);
            err("Error response:", data);
        }
    } catch (error) {
        alert("Error: " + error.message);
        err("Fetch error:", error);
    }
}
// ---------------------------
// LOAD MEMBERS FOR EXPENSE FORM
// ---------------------------
async function loadExpenseMembers() {
    const groupEl = document.getElementById('e_group');
    const groupId = groupEl ? groupEl.value : null;
    if (!groupId) {
        alert('Enter group id and click Load members');
        return;
    }

    try {
        const { res, ok, status, body } = await fetchJsonSafe(`${BASE_URL}/group/summary/${groupId}`);
        const data = body;
        if (!res.ok) {
            alert('Failed to load members: ' + (data.error || res.statusText));
            return;
        }

        // Extract member names from the returned structure
        let names = [];
        if (Array.isArray(data.members)) {
            names = data.members.map(m => m.name);
        } else if (data && data.summary) {
            names = Object.keys(data.summary);
        } else if (data && typeof data === 'object') {
            names = Object.keys(data);
        }

        populateDatalist('payers', names);
        populateDatalist('participants-list', names);
        // Non-blocking feedback: log instead of popup
        log('Member suggestions loaded');
    } catch (err) {
        err('Error loading members for expense form', err);
        alert('Error: ' + err.message);
    }
}

function populateDatalist(datalistId, names) {
    const dl = document.getElementById(datalistId);
    if (!dl) return;
    dl.innerHTML = '';
    const unique = Array.from(new Set(names));
    unique.forEach(n => {
        const opt = document.createElement('option');
        opt.value = n;
        dl.appendChild(opt);
    });
}
function goBack() {
    navigateBack();
}

// Called when user clicks "Next" in the members card.
function nextFromLoad() {
    navigateNext();
}

/* ---------------------------
   Navigation helpers (flow)
   --------------------------- */
const FLOW = ['group.html','wallet.html','expense.html','summary.html'];

function getPageName() {
    const p = window.location.pathname.split('/').pop();
    return p === '' ? 'index.html' : p;
}

function getGroupIdFromPage() {
    // look for known inputs in the page in order
    const ids = ['group_id', 'load_group_id', 'e_group', 'sum_group', 'w_group'];
    for (const id of ids) {
        const el = document.getElementById(id);
        if (el && el.value && String(el.value).trim() !== '') return String(el.value).trim();
    }
    // fallback to last loaded in memory
    if (typeof lastLoadedGroupId !== 'undefined' && lastLoadedGroupId) return String(lastLoadedGroupId);
    // fallback to session storage
    try { const v = sessionStorage.getItem('current_group'); if (v) return v; } catch(e) {}
    return null;
}

function navigateNext() {
    const page = getPageName();
    const idx = FLOW.indexOf(page);
    const targetIndex = idx === -1 ? 0 : idx + 1;

    // obtain group id if available
    // const gid = getGroupIdFromPage();
    // if (!gid) {
    //     alert('Please provide or load a Group ID before proceeding.');
    //     return;
    // }

    // persist for next page
    try { sessionStorage.setItem('current_group', String(gid)); } catch(e) {}

    if (targetIndex >= FLOW.length) {
        // already last page - do nothing
        return;
    }

    const target = FLOW[targetIndex];
    // if next is summary and we're on same page that has summary inputs, just show it
    if (target === 'summary.html') {
        // if we are on a page that contains sum_group, just call getSummary
        const sumEl = document.getElementById('sum_group');
        if (sumEl) { sumEl.value = gid; getSummary(); const targetDiv = document.getElementById('summary_output'); if (targetDiv) targetDiv.scrollIntoView({behavior:'smooth'}); return; }
    }

    // navigate to next page
    window.location.href = target;
}

function navigateBack() {
    const page = getPageName();
    const idx = FLOW.indexOf(page);
    const prevIndex = idx === -1 ? -1 : idx - 1;

    if (prevIndex < 0) {
        // go to index (home)
        window.location.href = 'index.html';
        return;
    }

    const target = FLOW[prevIndex];
    window.location.href = target;
}


// ---------------------------
// LOAD WALLET MEMBERS (UI)
// ---------------------------
// remember last loaded group so Next can work even if input is cleared
let lastLoadedGroupId = null;
async function loadWalletMembers() {
    const groupIdInput = document.getElementById('load_group_id');
    const groupId = groupIdInput ? groupIdInput.value : null;

    if (!groupId) {
        alert('Please enter a group id to load members');
        return;
    }

    try {
        const { res, ok, status, body } = await fetchJsonSafe(`${BASE_URL}/group/summary/${groupId}`);
        const data = body;

        if (!res.ok) {
            alert('Error fetching group members: ' + (data.error || res.statusText));
            return;
        }

        const area = document.getElementById('members_area');
        const template = document.getElementById('member-template');
        area.innerHTML = '';

        let first = true;
        // Server returns: { summary: {name: balance, ...}, members: [{user_id,wallet_id,name,balance}, ...] }
        let membersList = [];
        if (Array.isArray(data.members)) {
            membersList = data.members;
        } else if (data && typeof data === 'object' && data.summary) {
            // fallback for older format
            membersList = Object.keys(data.summary).map(n => ({ name: n, wallet_id: null, balance: data.summary[n] }));
        } else if (data && typeof data === 'object') {
            // if server returned plain mapping
            membersList = Object.keys(data).map(n => ({ name: n, wallet_id: null, balance: data[n] }));
        }

        for (const item of membersList) {
            const name = item.name;
            const clone = template.content.cloneNode(true);
            const row = clone.querySelector('.member-row');
            const nameEl = clone.querySelector('.member-name');
            const amountEl = clone.querySelector('.member-amount');
            // no per-row add button (bulk-only). We'll still get the status element via the row.
            const gidSlot = clone.querySelector('.group-id-slot');

            nameEl.textContent = name;
            if (first) {
                gidSlot.textContent = `Group: ${groupId}`;
                // show it only for the first item
                gidSlot.style.minWidth = '120px';
                first = false;
            } else {
                gidSlot.remove();
            }

            // store wallet id and name on the DOM for later bulk operations
            if (item.wallet_id) row.dataset.walletId = item.wallet_id;
            row.dataset.name = name;

            // per-row add buttons removed; individual add is done via bulk action
            // keep row datasets and DOM nodes; no per-row click handler

            area.appendChild(clone);
        }
        // remember the last loaded group id so Next works even if input cleared
        lastLoadedGroupId = parseInt(groupId, 10);
        try { sessionStorage.setItem('current_group', String(lastLoadedGroupId)); } catch (e) {}

        // ensure area scrolls properly (if many members)
        area.scrollTop = 0;
    } catch (err) {
        err('Error loading members', err);
        alert('Failed to load members: ' + err.message);
    }
}


// ---------------------------
// ADD MONEY FOR A MEMBER (programmatic variant)
// ---------------------------
async function addMoneyForMember(name, group_id, amount, triggerBtn=null, wallet_id=null, rowElement=null) {
    try {
        // Basic UI feedback
        if (triggerBtn) { triggerBtn.disabled = true; triggerBtn.textContent = 'Adding...'; }

        // find the inline status element (present in template) so we can show per-row success/failure
        // prefer rowElement if provided (bulk path), otherwise derive from triggerBtn if individual button available
        const statusEl = rowElement ? rowElement.querySelector('.member-status') : (triggerBtn ? triggerBtn.parentElement.querySelector('.member-status') : null);

        // allow group_id == 0 as valid; guard against NaN/null
        if (group_id === null || group_id === undefined || isNaN(group_id)) {
            alert('Invalid group id');
            return;
        }

        const payload = { amount: parseFloat(amount) };
        if (wallet_id) payload.wallet_id = wallet_id;
        else { payload.name = name; payload.group_id = parseInt(group_id, 10); }

        const { res, ok, status, body: data } = await fetchJsonSafe(`${BASE_URL}/wallet/add`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        // write response to debug panel and console for easier diagnosis
        showLastResponse({ status, ok, body: data });

        if (res.ok) {
            // Show inline success without collapsing UI or prompting blocking alerts
            if (statusEl) {
                statusEl.textContent = `Added ₹${parseFloat(amount).toFixed(2)}`;
                statusEl.style.color = 'var(--success-color)';
            }
            if (triggerBtn) {
                triggerBtn.textContent = 'Added';
            }
            log('Response:', data);
            // restore button text after a short delay but keep members loaded
            setTimeout(() => {
                if (triggerBtn) { triggerBtn.textContent = 'Add'; }
                if (statusEl) { statusEl.textContent = ''; }
            }, 1800);
        } else {
            // Provide clearer message when wallet cannot be found and show helpful server hints
            if (res.status === 404) {
                let msg = data.error || 'Wallet not found for the given user/group';
                if (data.hint) msg += '\n' + data.hint;
                if (Array.isArray(data.existing_members_in_group)) {
                    msg += '\nExisting members in group: ' + data.existing_members_in_group.join(', ');
                }
                // show inline error message
                if (statusEl) {
                    // show the first line of the server-provided hint/error
                    statusEl.textContent = msg.split('\n')[0];
                    statusEl.style.color = 'var(--error-color)';
                }
                // also make sure the in-page debug panel contains the server response (already done)
            } else {
                if (statusEl) {
                    statusEl.textContent = (data.error || 'Failed to add money');
                    statusEl.style.color = 'var(--error-color)';
                }
            }
            err('Error response:', data);
        }
    } catch (error) {
        alert('Error: ' + error.message);
        err('Fetch error:', error);
    } finally {
        if (triggerBtn) { triggerBtn.disabled = false; triggerBtn.textContent = 'Add'; }
    }
}


// ---------------------------
// BULK ADD (All members)
// ---------------------------
async function addAllMembersForGroup() {
    const groupIdInput = document.getElementById('load_group_id');
    const groupId = groupIdInput ? groupIdInput.value : lastLoadedGroupId;

    if (!groupId) {
        alert('Load a group first');
        return;
    }

    const area = document.getElementById('members_area');
    if (!area) return;

    const rows = Array.from(area.querySelectorAll('.member-row'));
    if (!rows.length) {
        alert('No members loaded');
        return;
    }

    // Validate: all members MUST have an amount entered
    const missing = [];
    const payloads = [];
    for (const row of rows) {
        const name = row.dataset.name || row.querySelector('.member-name').textContent;
        const wid = row.dataset.walletId ? parseInt(row.dataset.walletId, 10) : null;
        const amtEl = row.querySelector('.member-amount');
        const val = amtEl ? amtEl.value : '';
        const num = parseFloat(val);
        if (val === '' || isNaN(num) || num < 0) missing.push(name);
        payloads.push({ row, name, wid, amount: num });
    }

    if (missing.length) {
        alert('Please enter a non-negative amount for all members before adding. Missing: ' + missing.join(', '));
        return;
    }

    // Disable bulk button while running
    const bulkBtn = document.getElementById('add_all_btn');
    if (bulkBtn) { bulkBtn.disabled = true; bulkBtn.textContent = 'Adding...'; }

    // Perform adds sequentially so UI updates cleanly
    for (const p of payloads) {
        const trigger = p.row.querySelector('.member-add-btn');
        // reuse existing addMoneyForMember so statuses and handling apply
        try {
            await addMoneyForMember(p.name, parseInt(groupId, 10), p.amount, null, p.wid, p.row);
        } catch (e) {
            err('Bulk add error for', p.name, e);
        }
    }

    if (bulkBtn) { bulkBtn.disabled = false; bulkBtn.textContent = 'Add For All'; }
    // keep UI loaded and show final success
    showLastResponse({ status: 200, ok: true, body: { message: 'Bulk add completed' } });
}


// Display server JSON responses into the on-page debug panel
function showLastResponse(obj) {
    const el = document.getElementById('last_response');
    if (!el) return;
    try {
        el.textContent = JSON.stringify(obj, null, 2);
    } catch (e) {
        el.textContent = String(obj);
    }
    // Also log to console for advanced inspection
    log('Last server response panel updated:', obj);
}

// Auto-fill flow group across pages and auto-load when appropriate
window.addEventListener('DOMContentLoaded', () => {
    try {
        const pre = sessionStorage.getItem('current_group');
        if (!pre) return;

        // wallet page: auto-fill load_group_id and auto-load members
        const loadEl = document.getElementById('load_group_id');
        if (loadEl) {
            loadEl.value = pre;
            lastLoadedGroupId = parseInt(pre, 10);
            // attempt to load members automatically (non-blocking)
            try { loadWalletMembers(); } catch (e) { log('Auto-load members failed', e); }
            return;
        }

        // summary page: auto-fill and fetch
        const sumEl = document.getElementById('sum_group');
        if (sumEl) {
            sumEl.value = pre;
            try { getSummary(); } catch (e) { log('Auto-get summary failed', e); }
            return;
        }

        // expense page: prefill e_group
        const eg = document.getElementById('e_group');
        if (eg) eg.value = pre;
    } catch (e) {
        // ignore storage errors
    }
});