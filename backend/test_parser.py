"""Quick smoke-test for the Canara Bank CSV format."""
from csv_parser import parse_csv

sample = (
    ',,Current & Saving Account Statement\n'
    '\n'
    'HRUSHIKESH AJAY KANT\n'
    'JIJAMATA SQUARE\n'
    '\n'
    ',Account Statement as of,19-02-2026 23:28:33 +0530\n'
    'Account Holders Name,HRUSHIKESH AJAY KANT\n'
    'Customer Id ,="313552339"\n'
    'Branch Name,"KARANJA"\n'
    'MICR Code,="444015452"\n'
    'IFSC Code,"CNRB0005998"\n'
    'Searched By,From 08 Feb 2026 To 19 Feb 2026\n'
    'Account Number,="110080200993"\n'
    'Account Currency,INR\n'
    'Product Name,101 - CANARA SB GENERAL\n'
    '"Opening Balance","Rs.1,855.26"\n'
    '"Closing Balance","Rs.1,179.26"\n'
    '\n'
    '\n'
    'Txn Date,Value Date,Cheque No.,Description,Branch Code,Debit,Credit,Balance,\n'
    '="08-02-2026 10:04:23",="08 Feb 2026",="640532274910","UPI/DR/640532274910/VAISHAMPA","9998","200.00","","1655.26",\n'
    '="10-02-2026 14:30:00",="10 Feb 2026","","SALARY CREDIT","9998","","5000.00","6655.26",\n'
    '="12-02-2026 09:15:00",="12 Feb 2026",="640532274911","ATM WITHDRAWAL","9998","500.00","","6155.26",\n'
)

result = parse_csv(sample)
print(f"Headers  : {result['headers']}")
print(f"Preamble : {len(result['preamble'])} rows skipped")
print(f"Rows     : {len(result['transactions'])} transactions found")
for tx in result['transactions']:
    sign = '+' if tx['is_credit'] else '-'
    print(f"  [{tx['date']}]  {tx['description'][:45]:45s}  {sign}{abs(tx['amount']):.2f}")
