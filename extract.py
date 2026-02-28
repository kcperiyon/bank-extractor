#!/usr/bin/env python3
"""
extract.py - Called by TaxMasterAgent Node.js backend
Usage: python extract.py <pdf_path>
Output: JSON to stdout
"""
import sys
import json
import traceback
import os

# Add package directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extractor import DocumentExtractor
from ai_parser import AIParser
from reporter import Reporter


def detect_bank(text: str) -> str:
    text_lower = text.lower()
    banks = {
        "zenith":      "Zenith Bank",
        "ecobank":     "Ecobank",
        "opay":        "OPay",
        "guaranty":    "GTBank",
        "gtbank":      "GTBank",
        "access bank": "Access Bank",
        "united bank": "UBA",
        "uba":         "UBA",
        "first bank":  "First Bank",
        "fidelity":    "Fidelity Bank",
        "stanbic":     "Stanbic IBTC",
        "kuda":        "Kuda Bank",
        "moniepoint":  "Moniepoint",
        "palmpay":     "PalmPay",
        "wema":        "Wema Bank",
        "fcmb":        "FCMB",
        "sterling":    "Sterling Bank",
        "union bank":  "Union Bank",
        "polaris":     "Polaris Bank",
    }
    for key, name in banks.items():
        if key in text_lower:
            return name
    return "Unknown"


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "No file path provided. Usage: python extract.py <pdf_path>"
        }))
        sys.exit(1)

    filepath = sys.argv[1]

    if not os.path.exists(filepath):
        print(json.dumps({
            "success": False,
            "error": f"File not found: {filepath}"
        }))
        sys.exit(1)

    try:
        # Step 1: Extract raw text
        extractor = DocumentExtractor(filepath)
        raw_text = extractor.extract()

        if not raw_text or len(raw_text.strip()) < 50:
            print(json.dumps({
                "success": False,
                "error": "Could not extract text from document"
            }))
            sys.exit(1)

        # Step 2: Parse with AI
        parser = AIParser(model="gpt-4o")
        transactions = parser.parse(raw_text)

        if not transactions:
            print(json.dumps({
                "success": False,
                "error": "No transactions found"
            }))
            sys.exit(1)

        # Step 3: Build summary
        reporter = Reporter(transactions, source_file=filepath)
        df = reporter.df

        total_debits  = float(df["debit"].sum())
        total_credits = float(df["credit"].sum())
        closing_bal   = float(df["balance"].iloc[-1]) if not df.empty else 0.0
        net_flow      = total_credits - total_debits

        # Step 4: Print JSON to stdout (Node.js reads this)
        result = {
            "success": True,
            "bank": detect_bank(raw_text),
            "summary": {
                "total_rows":      len(transactions),
                "debit_rows":      int((df["debit"] > 0).sum()),
                "credit_rows":     int((df["credit"] > 0).sum()),
                "total_debits":    total_debits,
                "total_credits":   total_credits,
                "net_cash_flow":   net_flow,
                "closing_balance": closing_bal,
                "direction":       "surplus" if net_flow >= 0 else "deficit"
            },
            "transactions": transactions
        }

        print(json.dumps(result))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({
            "success": False,
            "error": str(e),
            "trace": traceback.format_exc()
        }))
        sys.exit(1)


if __name__ == "__main__":
    main()
