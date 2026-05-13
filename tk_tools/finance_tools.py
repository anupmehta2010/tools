"""Finance helpers: currency, rates, invoice PDF, tax, loan payment, compound."""
from __future__ import annotations

import argparse
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from _common import lazy_import


_RATES_URL = "https://api.exchangerate.host"


def _fetch_json(url: str) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"[!] Network error: {e}")
        raise SystemExit(2)


# ---- Currency convert ----

def cmd_currency(args):
    """Convert currency via exchangerate.host."""
    qs = urllib.parse.urlencode({
        "from": args.from_currency,
        "to":   args.to_currency,
        "amount": args.amount,
    })
    data = _fetch_json(f"{_RATES_URL}/convert?{qs}")
    if not data.get("success", True) and data.get("result") is None:
        print(f"[!] Conversion failed: {data}")
        return 1
    result = data.get("result")
    rate = (data.get("info") or {}).get("rate") or data.get("rate")
    print(f"{args.amount} {args.from_currency} = {result} {args.to_currency}")
    if rate is not None:
        print(f"Rate: 1 {args.from_currency} = {rate} {args.to_currency}")


# ---- Rates ----

def cmd_rates(args):
    """Fetch a rates table for a base currency."""
    qs = urllib.parse.urlencode({"base": args.base})
    data = _fetch_json(f"{_RATES_URL}/latest?{qs}")
    rates = data.get("rates", {})
    if not rates:
        print(f"[!] No rates returned: {data}")
        return 1
    if args.output:
        Path(args.output).write_text(json.dumps(rates, indent=2), encoding="utf-8")
        print(f"Wrote {args.output}")
        return
    print(f"Base: {args.base}")
    for code in sorted(rates):
        print(f"  {code:<6} {rates[code]}")


# ---- Invoice PDF ----

def cmd_invoice(args):
    """Generate an invoice PDF from a JSON file (reportlab)."""
    reportlab = lazy_import("reportlab.pdfgen.canvas", "pip install reportlab")
    from reportlab.lib.pagesizes import letter
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    out = args.output or "invoice.pdf"
    c = reportlab.Canvas(out, pagesize=letter)
    W, H = letter
    x_left, y = 72, H - 72
    c.setFont("Helvetica-Bold", 22)
    c.drawString(x_left, y, f"INVOICE #{data.get('number', '0001')}")
    y -= 36
    c.setFont("Helvetica", 11)
    c.drawString(x_left, y, f"Date: {data.get('date', '')}")
    y -= 14
    c.drawString(x_left, y, f"Due:  {data.get('due', '')}")
    y -= 28
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_left, y, "From:")
    c.drawString(x_left + 250, y, "Bill to:")
    y -= 16
    c.setFont("Helvetica", 10)
    for line in (data.get("from") or "").splitlines():
        c.drawString(x_left, y, line); y -= 12
    y2 = y + 12 * len((data.get("from") or "").splitlines())
    for line in (data.get("to") or "").splitlines():
        c.drawString(x_left + 250, y2, line); y2 -= 12
    y = min(y, y2) - 16
    # Items table
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_left, y, "Description")
    c.drawRightString(x_left + 320, y, "Qty")
    c.drawRightString(x_left + 400, y, "Price")
    c.drawRightString(x_left + 480, y, "Total")
    y -= 4
    c.line(x_left, y, x_left + 480, y)
    y -= 14
    c.setFont("Helvetica", 10)
    total = 0.0
    for it in data.get("items", []):
        qty = float(it.get("qty", 1))
        price = float(it.get("price", 0))
        line_total = qty * price
        total += line_total
        c.drawString(x_left, y, str(it.get("description", ""))[:40])
        c.drawRightString(x_left + 320, y, f"{qty:g}")
        c.drawRightString(x_left + 400, y, f"{price:.2f}")
        c.drawRightString(x_left + 480, y, f"{line_total:.2f}")
        y -= 14
    y -= 6
    c.line(x_left + 240, y, x_left + 480, y)
    y -= 16
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(x_left + 400, y, "Total:")
    currency = data.get("currency", "USD")
    c.drawRightString(x_left + 480, y, f"{total:.2f} {currency}")
    c.showPage()
    c.save()
    print(f"Wrote {out} (total: {total:.2f} {currency})")


# ---- Tax ----

def cmd_tax(args):
    """Simple flat % tax calc."""
    amount = args.amount
    rate = args.rate / 100.0
    tax = amount * rate
    total = amount + tax
    print(f"Subtotal:  {amount:.2f}")
    print(f"Tax ({args.rate}%): {tax:.2f}")
    print(f"Total:     {total:.2f}")


# ---- Loan payment ----

def cmd_pmt(args):
    """Loan payment calc (principal, annual rate %, term months)."""
    p = args.principal
    r = args.rate / 100.0 / 12.0
    n = args.term
    if r == 0:
        pmt = p / n
    else:
        pmt = p * r * (1 + r) ** n / ((1 + r) ** n - 1)
    total_paid = pmt * n
    interest = total_paid - p
    print(f"Principal:        {p:.2f}")
    print(f"Annual rate:      {args.rate}%")
    print(f"Term:             {n} months")
    print(f"Monthly payment:  {pmt:.2f}")
    print(f"Total paid:       {total_paid:.2f}")
    print(f"Total interest:   {interest:.2f}")


# ---- Compound interest ----

def cmd_compound(args):
    """Compound interest calc."""
    p = args.principal
    r = args.rate / 100.0
    n = args.periods_per_year
    t = args.years
    amount = p * (1 + r / n) ** (n * t)
    interest = amount - p
    print(f"Principal:        {p:.2f}")
    print(f"Annual rate:      {args.rate}%")
    print(f"Periods/year:     {n}")
    print(f"Years:             {t}")
    print(f"Final amount:     {amount:.2f}")
    print(f"Interest earned:  {interest:.2f}")


# ---- COMMANDS dict ----
COMMANDS = {
    "currency": "convert currency (exchangerate.host)",
    "rates":    "fetch rates table for a base currency",
    "invoice":  "generate invoice PDF from JSON",
    "tax":      "flat percentage tax breakdown",
    "pmt":      "loan payment calc",
    "compound": "compound interest calc",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="finance_tools", description="Finance helpers")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("currency", help=COMMANDS["currency"])
    p.add_argument("--from", required=True, dest="from_currency")
    p.add_argument("--to", required=True, dest="to_currency")
    p.add_argument("--amount", type=float, required=True)
    p.set_defaults(func=cmd_currency)

    p = sub.add_parser("rates", help=COMMANDS["rates"])
    p.add_argument("--base", default="USD")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_rates)

    p = sub.add_parser("invoice", help=COMMANDS["invoice"])
    p.add_argument("input", help="JSON file: number, date, due, from, to, items[{description,qty,price}], currency")
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_invoice)

    p = sub.add_parser("tax", help=COMMANDS["tax"])
    p.add_argument("amount", type=float)
    p.add_argument("--rate", type=float, required=True, help="percentage, e.g. 8.875")
    p.set_defaults(func=cmd_tax)

    p = sub.add_parser("pmt", help=COMMANDS["pmt"])
    p.add_argument("--principal", type=float, required=True)
    p.add_argument("--rate", type=float, required=True, help="annual rate (percent)")
    p.add_argument("--term", type=int, required=True, help="months")
    p.set_defaults(func=cmd_pmt)

    p = sub.add_parser("compound", help=COMMANDS["compound"])
    p.add_argument("--principal", type=float, required=True)
    p.add_argument("--rate", type=float, required=True, help="annual rate (percent)")
    p.add_argument("--periods-per-year", type=int, default=12, dest="periods_per_year")
    p.add_argument("--years", type=float, required=True)
    p.set_defaults(func=cmd_compound)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
