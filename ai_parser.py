# ai_parser.py
import os, json, re
from openai import OpenAI

def _load_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("OPENAI_API_KEY"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    return parts[1].strip().strip('"').strip("'")
    return os.environ.get("OPENAI_API_KEY", "")

def _clean_num(val):
    if val is None or str(val).strip() in ("", "-", "nil", "Nil", "N/A", "nan"):
        return 0.0
    s = re.sub(r"[#,\s]", "", str(val).replace("NGN","").replace("₦",""))
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        return -float(s) if negative else float(s)
    except:
        return 0.0

def _extract_json(raw: str):
    # Strategy 1: direct parse
    try:
        obj = json.loads(raw)
        if isinstance(obj, list): return obj
        if isinstance(obj, dict) and "transactions" in obj:
            return obj["transactions"]
    except: pass

    # Strategy 2: strip markdown fences
    cleaned = re.sub(r"```(?:json)?", "", raw, flags=re.IGNORECASE).strip()
    try:
        obj = json.loads(cleaned)
        if isinstance(obj, list): return obj
        if isinstance(obj, dict) and "transactions" in obj:
            return obj["transactions"]
    except: pass

    # Strategy 3: find first [...] block
    m = re.search(r"(\[.*\])", cleaned, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, list): return obj
        except: pass

    # Strategy 4: fix truncated JSON
    try:
        text = cleaned.strip()
        if text.startswith("[") and not text.endswith("]"):
            last = text.rfind("},")
            if last != -1:
                text = text[:last+1] + "\n]"
            else:
                last = text.rfind("{")
                text = text[:last] + "\n]"
            obj = json.loads(text)
            if isinstance(obj, list): return obj
    except: pass

    # Strategy 5: extract individual objects
    objects = re.findall(r"\{[^{}]+\}", cleaned, re.DOTALL)
    results = []
    for o in objects:
        try:
            results.append(json.loads(o))
        except: pass
    if results: return results
    return []

SYSTEM_PROMPT = """You are an expert Nigerian bank statement parser.
You understand ALL Nigerian bank formats including:
Zenith Bank, GTBank, Access Bank, First Bank, UBA, Stanbic IBTC,
Fidelity Bank, Polaris Bank, Keystone Bank, Sterling Bank, Wema Bank,
Union Bank, FCMB, Ecobank, Heritage Bank, Jaiz Bank, SunTrust Bank.

Extract EVERY transaction row and return ONLY a valid JSON array.

Each transaction object must have exactly these keys:
  "date"        - transaction date as string e.g. "01/12/2025"
  "value_date"  - value date as string, same as date if not shown
  "description" - full narration text, keep under 100 characters
  "debit"       - debit amount as plain number string e.g. "7037.31" or "0"
  "credit"      - credit amount as plain number string e.g. "330000.00" or "0"
  "balance"     - running balance as plain number string e.g. "26397.74" or "0"

CRITICAL RULES FOR AMOUNTS:
- Nigerian bank statements always show a running BALANCE after each transaction
- Use the BALANCE column to verify: Previous_Balance - Debit + Credit = Current_Balance
- If balance goes DOWN compared to previous row, it is a DEBIT transaction
- If balance goes UP compared to previous row, it is a CREDIT transaction
- The BALANCE column is always the RIGHTMOST number column on each row
- The DEBIT column is always to the LEFT of the BALANCE column
- The CREDIT column is always between DEBIT and BALANCE columns
- Never split a number - "7,037.31" must be extracted as "7037.31" not "737.31"
- Numbers with commas like "330,000.00" must become "330000.00"
- NO currency symbols, NO commas inside number strings
- Return ONLY the JSON array, no markdown, no commentary
- If no transactions found return []
"""

class AIParser:
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        api_key = _load_key()
        if not api_key or len(api_key) < 20:
            raise ValueError(
                "\n\nOPENAI_API_KEY is missing or not set!\n"
                "Open your .env file and add:\n"
                "OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx\n"
                "Get your key at: https://platform.openai.com/api-keys\n"
            )
        self.client = OpenAI(api_key=api_key)
        self.total_tokens = 0

    def _parse_chunk(self, chunk: str, chunk_num: int) -> list:
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": (
                        "Extract ALL transactions from this Nigerian bank statement text.\n"
                        "Pay special attention to the BALANCE column to verify debit/credit amounts.\n"
                        "Remember: balance going DOWN = debit, balance going UP = credit.\n\n"
                        f"{chunk}"
                    )}
                ],
                temperature=0,
                max_tokens=8192,
            )
            self.total_tokens += resp.usage.total_tokens if resp.usage else 0
            raw = resp.choices[0].message.content.strip()
            rows = _extract_json(raw)
            cleaned = []
            for r in rows:
                if not isinstance(r, dict): continue
                cleaned.append({
                    "date":        str(r.get("date", "")).strip(),
                    "value_date":  str(r.get("value_date", "")).strip(),
                    "description": str(r.get("description", "")).strip(),
                    "debit":       _clean_num(r.get("debit", 0)),
                    "credit":      _clean_num(r.get("credit", 0)),
                    "balance":     _clean_num(r.get("balance", 0)),
                })
            return cleaned
        except Exception as e:
            print(f"   ERROR on chunk {chunk_num}: {e}")
            return []

    def parse(self, text: str, chunk_size: int = 6000) -> list:
        from utils import chunk_text
        chunks = chunk_text(text, max_chars=chunk_size)
        total_chunks = len(chunks)
        print(f"\n   Model       : {self.model}")
        print(f"   Text length : {len(text):,} characters")
        print(f"   Chunks      : {total_chunks}")

        all_rows = []
        for i, chunk in enumerate(chunks, 1):
            print(f"\n   Processing chunk {i} of {total_chunks}...")
            rows = self._parse_chunk(chunk, i)
            print(f"   Got {len(rows)} transactions from chunk {i}")
            all_rows.extend(rows)

        # Deduplicate
        seen, unique = set(), []
        for r in all_rows:
            key = (r["date"], r["description"][:40], r["debit"], r["credit"])
            if key not in seen:
                seen.add(key)
                unique.append(r)

        print(f"\n   Total transactions : {len(unique)}")
        print(f"   Total tokens used  : {self.total_tokens:,}")
        return unique
