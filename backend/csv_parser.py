"""
csv_parser.py  —  Canara Bank statement parser

Two functions:

    find_transactions(file_content)
        Skips the bank's metadata preamble and returns the raw
        transaction rows (list of lists).

    parse_transaction(row)
        Parses one transaction row into a clean dict with:
          amount, is_credit, sent_to / receive_from,
          date, time, comment
"""

import csv, io, re
from datetime import datetime


# ── Canara Bank column positions (0-based) ─────────────────────────
# Txn Date | Value Date | Cheque No. | Description | Branch | Debit | Credit | Balance
COL_DATE  = 0
COL_DESC  = 3
COL_DEBIT = 5
COL_CREDIT= 6

# UPI remarks that carry no real meaning
_GENERIC = {"upi", "pay", "na", "neft", "imps", "rtgs"}


class ParseError(Exception):
    pass


# ══════════════════════════════════════════════════════════════════
# FUNCTION 1 — skip preamble, return transaction rows
# ══════════════════════════════════════════════════════════════════

def find_transactions(file_content: str | bytes):
    """
    Decode the file, skip the bank's header/address block,
    and return (headers, data_rows).

    headers   — list[str]        column names
    data_rows — list[list[str]]  one list per transaction
    """
    # Decode bytes
    if isinstance(file_content, bytes):
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                file_content = file_content.decode(enc); break
            except UnicodeDecodeError:
                continue

    # Strip Excel  ="value"  escaping AND plain quoted cells
    def clean(cell):
        c = cell.strip()
        if c.startswith('="') and c.endswith('"'):
            return c[2:-1]          # ="640532274910"  →  640532274910
        if c.startswith('"') and c.endswith('"') and len(c) >= 2:
            return c[1:-1]          # "UPI/DR/..."  →  UPI/DR/...
        return c

    rows = [[clean(c) for c in r]
            for r in csv.reader(io.StringIO(file_content))]

    # Find the real header — the row that contains "Txn Date"
    header_idx = next(
        (i for i, r in enumerate(rows) if any("txn date" in c.lower() for c in r)),
        None
    )
    if header_idx is None:
        raise ParseError("Could not find the 'Txn Date' header row.")

    headers   = rows[header_idx]
    data_rows = [r for r in rows[header_idx + 1:] if any(c for c in r)]
    return headers, data_rows


# ══════════════════════════════════════════════════════════════════
# FUNCTION 2 — parse one transaction row into a dict
# ══════════════════════════════════════════════════════════════════

def parse_transaction(row: list[str], index: int = 0):
    """
    Parse a single Canara Bank transaction row.

    Returns a dict with:
        index, date, time, amount, is_credit,
        sent_to, receive_from, comment, description, category
    Returns None if the row has no useful data.
    """
    def get(i):
        return row[i].strip() if i < len(row) else ""

    # ── Amount ────────────────────────────────────────────────────
    def to_float(s):
        s = re.sub(r"[^\d.]", "", s)
        return float(s) if s else 0.0

    debit  = to_float(get(COL_DEBIT))
    credit = to_float(get(COL_CREDIT))
    amount = credit - debit        # positive = money in, negative = money out
    is_credit = amount >= 0

    raw_date = get(COL_DATE)
    raw_desc = get(COL_DESC)

    if not raw_date and not raw_desc and amount == 0:
        return None                # skip blank/footer rows

    # ── Date & Time ───────────────────────────────────────────────
    date = time = None
    try:
        dt   = datetime.strptime(raw_date, "%d-%m-%Y %H:%M:%S")
        date = dt.strftime("%Y-%m-%d")
        time = dt.strftime("%H:%M:%S")
    except ValueError:
        date = raw_date            # keep raw if format differs

    # ── UPI description parsing ───────────────────────────────────
    # Format: UPI/DR/<ref>/<Name>/<Bank>/<upi-id>/<remark>//<txn-ref>/...
    sent_to = receive_from = comment = None

    if raw_desc.upper().startswith("UPI/"):
        parts = raw_desc.split("/")
        name   = parts[3].strip()  if len(parts) > 3 else ""
        remark = parts[6].strip()  if len(parts) > 6 else ""

        if name:
            if is_credit: receive_from = name
            else:         sent_to      = name

        if remark and remark.lower() not in _GENERIC:
            comment = remark
    
    

    result = {
        "index":        index,
        "date":         date,
        "time":         time,
        "amount":       round(amount, 2),
        "is_credit":    is_credit,
        "sent_to":      sent_to,
        "receive_from": receive_from,
        "comment":      comment,
        "description":  raw_desc or "Unknown",
        "category":     None,
    }

    print(f"[TX] sent_to={sent_to} | receive_from={receive_from} | comment={comment} | amount={amount}", flush=True)

    return result


# ══════════════════════════════════════════════════════════════════
# Orchestrator used by main.py  (signature unchanged)
# ══════════════════════════════════════════════════════════════════

def parse_csv(file_content: str | bytes) -> dict:
    headers, data_rows = find_transactions(file_content)

    transactions = [
        tx for i, row in enumerate(data_rows)
        if (tx := parse_transaction(row, index=i)) is not None
    ]

    if not transactions:
        raise ParseError("No valid transactions found.")

    return {
        "headers":      headers,
        "col_indices":  {},        # not needed for fixed-column Canara format
        "raw_rows":     data_rows,
        "transactions": transactions,
        "preamble":     [],
    }


def to_categorised_csv(headers, raw_rows, categorised,
                       category_col_name="Category") -> str:
    cat_map = {t["index"]: (t["category"] or "") for t in categorised}
    out = io.StringIO()
    w   = csv.writer(out, lineterminator="\r\n")
    w.writerow(headers + [category_col_name])
    for i, row in enumerate(raw_rows):
        w.writerow(list(row) + [cat_map.get(i, "")])
    return out.getvalue()
