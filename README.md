# Nigerian Bank Statement Extractor — Microservice

## What this is
A Python FastAPI microservice that extracts transactions from ANY Nigerian bank 
statement PDF (Zenith, Ecobank, OPay, GTBank, Access, UBA, First Bank, etc.)
using PyMuPDF for positional extraction and GPT-4o for intelligent parsing.

## Proven results
- Zenith Bank: 430 transactions, closing balance N597.75 exact
- Ecobank: 153 transactions, closing balance N792.32 exact  
- OPay: 173 transactions, closing balance N356.92 exact

## Files
- api.py          → FastAPI REST endpoint (main entry point)
- extractor.py    → PyMuPDF positional PDF extraction engine
- ai_parser.py    → GPT-4o transaction parser
- reporter.py     → Summary and DataFrame builder
- requirements.txt → Python dependencies
- .env            → OPENAI_API_KEY (keep secret)

## How to run
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000

## Single endpoint
POST /extract
- Input:  multipart/form-data with field "file" = PDF or image
- Output: JSON (see below)

## Response format
{
  "success": true,
  "bank": "Zenith Bank",
  "filename": "statement.pdf",
  "summary": {
    "total_rows": 430,
    "debit_rows": 339,
    "credit_rows": 91,
    "total_debits": 2532610.18,
    "total_credits": 3180502.15,
    "net_cash_flow": 647891.97,
    "closing_balance": 597.75,
    "direction": "surplus"
  },
  "transactions": [
    {
      "date": "01/12/2025",
      "value_date": "01/12/2025",
      "description": "NIP CR/MOB/...",
      "debit": 0,
      "credit": 10000.00,
      "balance": 79120.71
    }
  ]
}

## Health check
GET /health → { "status": "ok", "engine": "PyMuPDF + GPT-4o" }

## How TaxMasterAgent Node.js calls this
const axios = require("axios");
const FormData = require("form-data");
const fs = require("fs");

async function extractBankStatement(filePath, filename) {
  const form = new FormData();
  form.append("file", fs.createReadStream(filePath), filename);
  const response = await axios.post(
    process.env.PYTHON_EXTRACTOR_URL + "/extract",
    form,
    { headers: form.getHeaders(), timeout: 180000 }
  );
  return response.data;
}

## Deploy on Render
1. Push this folder to a GitHub repo
2. Create new Render Web Service
3. Runtime: Python
4. Build command: pip install -r requirements.txt
5. Start command: uvicorn api:app --host 0.0.0.0 --port $PORT
6. Add environment variable: OPENAI_API_KEY = your key
7. Copy the Render URL
8. Add to TaxMasterAgent Render env: PYTHON_EXTRACTOR_URL = that URL

## Replace nigerianBankParser.js
In documentWorker.js, replace:
  const result = await parseNigerianBankStatement(filePath);
With:
  const result = await extractBankStatement(filePath, filename);
Delete nigerianBankParser.js entirely.
