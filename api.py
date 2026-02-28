from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import tempfile, os, traceback
from extractor import DocumentExtractor
from ai_parser import AIParser
from reporter import Reporter

app = FastAPI(
    title="Nigerian Bank Statement Extractor",
    description="Universal extractor for all Nigerian bank statements",
    version="1.0.0"
)

# Allow Node.js backend to call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def _detect_bank(text: str) -> str:
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
        "jaiz":        "Jaiz Bank",
    }
    for key, name in banks.items():
        if key in text_lower:
            return name
    return "Unknown"


@app.get("/health")
def health():
    return {
        "status": "ok",
        "engine": "PyMuPDF + GPT-4o",
        "version": "1.0.0"
    }


@app.post("/extract")
async def extract(file: UploadFile = File(...)):
    # Validate file type
    if not file.filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Send a PDF or image."
        )

    # Save to temp file
    suffix = os.path.splitext(file.filename)[1].lower()
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # ── Step 1: Extract raw text ──────────────────────────────
        extractor = DocumentExtractor(tmp_path)
        raw_text = extractor.extract()

        if not raw_text or len(raw_text.strip()) < 50:
            raise HTTPException(
                status_code=422,
                detail="Could not extract text from document. File may be corrupt or empty."
            )

        # ── Step 2: Parse transactions with AI ───────────────────
        parser = AIParser(model="gpt-4o")
        transactions = parser.parse(raw_text)

        if not transactions:
            raise HTTPException(
                status_code=422,
                detail="No transactions found in document."
            )

        # ── Step 3: Build summary ─────────────────────────────────
        reporter = Reporter(transactions, source_file=file.filename)
        df = reporter.df

        total_debits  = float(df["debit"].sum())
        total_credits = float(df["credit"].sum())
        closing_bal   = float(df["balance"].iloc[-1]) if not df.empty else 0.0
        net_flow      = total_credits - total_debits

        # ── Step 4: Return clean JSON to Node.js ──────────────────
        return JSONResponse(content={
            "success": True,
            "bank": _detect_bank(raw_text),
            "filename": file.filename,
            "summary": {
                "total_rows":       len(transactions),
                "debit_rows":       int((df["debit"] > 0).sum()),
                "credit_rows":      int((df["credit"] > 0).sum()),
                "total_debits":     total_debits,
                "total_credits":    total_credits,
                "net_cash_flow":    net_flow,
                "closing_balance":  closing_bal,
                "direction":        "surplus" if net_flow >= 0 else "deficit"
            },
            "transactions": transactions
        })

    except HTTPException:
        raise

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Extraction failed: {str(e)}"
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
