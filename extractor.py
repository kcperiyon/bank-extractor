import fitz          # PyMuPDF
import camelot
import pytesseract
from PIL import Image
import re, os, io

# ── Nigerian bank column header patterns ───────────────────────────────────
_DATE_KW    = re.compile(r'\bdate\b', re.I)
_DESC_KW    = re.compile(r'\b(description|narration|particulars|details|remarks|ref)\b', re.I)
_DEBIT_KW   = re.compile(r'\b(debit|dr\.?|withdrawal[s]?|paid out)\b', re.I)
_CREDIT_KW  = re.compile(r'\b(credit|cr\.?|deposit[s]?|paid in)\b', re.I)
_BALANCE_KW = re.compile(r'\b(balance|bal\.?|running)\b', re.I)


def _is_header(words_in_row: list) -> bool:
    text = " ".join(words_in_row)
    return bool(
        _DATE_KW.search(text) and
        (_DEBIT_KW.search(text) or _CREDIT_KW.search(text))
    )


def _cluster_columns(header_words: list) -> dict:
    """
    Given a list of (text, x0, x1) tuples from the header row,
    return a dict: column_name -> x_centre.
    Works for ANY Nigerian bank layout because it reads the actual
    header text rather than assuming fixed positions.
    """
    cols = {}
    for text, x0, x1 in header_words:
        cx = (x0 + x1) / 2
        if _DATE_KW.search(text):
            cols["date"] = cx
        elif _DESC_KW.search(text):
            cols["description"] = cx
        elif _DEBIT_KW.search(text):
            cols["debit"] = cx
        elif _CREDIT_KW.search(text):
            cols["credit"] = cx
        elif _BALANCE_KW.search(text):
            cols["balance"] = cx
    return cols


def _nearest_col(cx: float, col_map: dict) -> str:
    if not col_map:
        return "description"
    return min(col_map, key=lambda c: abs(col_map[c] - cx))


def _rows_from_words(word_list: list, y_tol: int = 5) -> list:
    """
    word_list: list of (x0, y0, x1, y1, text, ...) from fitz get_text("words")
    Groups words into rows by y-position, sorts each row left-to-right.
    Returns list of rows, each row = list of (text, x0, x1, y0).
    """
    if not word_list:
        return []

    # Sort by y0 then x0
    sorted_words = sorted(word_list, key=lambda w: (round(w[1] / y_tol), w[0]))

    rows = []
    current_row = []
    current_y = sorted_words[0][1]

    for w in sorted_words:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        if abs(y0 - current_y) <= y_tol:
            current_row.append((text, x0, x1, y0))
        else:
            if current_row:
                rows.append(sorted(current_row, key=lambda r: r[1]))
            current_row = [(text, x0, x1, y0)]
            current_y = y0

    if current_row:
        rows.append(sorted(current_row, key=lambda r: r[1]))

    return rows


def _extract_page_pymupdf(page) -> str:
    """
    Core extraction using PyMuPDF word-level bounding boxes.
    Detects column positions from the header row, then assigns
    each word to date/description/debit/credit/balance.
    Returns a pipe-delimited string: one line per transaction row.
    """
    word_list = page.get_text("words")
    if not word_list:
        return ""

    rows = _rows_from_words(word_list, y_tol=5)
    if not rows:
        return ""

    # ── Find header row ──────────────────────────────────────────────────
    col_map = {}
    header_idx = 0
    for i, row in enumerate(rows):
        texts = [w[0] for w in row]
        if _is_header(texts):
            col_map = _cluster_columns([(w[0], w[1], w[2]) for w in row])
            header_idx = i
            break

    # ── Build output lines ───────────────────────────────────────────────
    lines = []
    for row in rows[header_idx:]:
        if col_map:
            cells = {"date": [], "description": [], "debit": [],
                     "credit": [], "balance": []}
            for text, x0, x1, y0 in row:
                cx = (x0 + x1) / 2
                col = _nearest_col(cx, col_map)
                cells[col].append(text)
            line = " | ".join([
                " ".join(cells["date"]),
                " ".join(cells["description"]),
                " ".join(cells["debit"]),
                " ".join(cells["credit"]),
                " ".join(cells["balance"]),
            ])
        else:
            line = " ".join(w[0] for w in row)

        if line.strip(" |"):
            lines.append(line)

    return "\n".join(lines)


def _try_camelot(filepath: str, page_num: int) -> str:
    """
    Try Camelot stream mode on a single page as a fallback.
    Returns pipe-delimited rows or empty string on failure.
    """
    try:
        tables = camelot.read_pdf(
            filepath,
            pages=str(page_num),
            flavor="stream",
            edge_tol=50,
            row_tol=10,
        )
        if tables and len(tables) > 0:
            lines = []
            for table in tables:
                df = table.df
                for _, row in df.iterrows():
                    lines.append(" | ".join(str(v).strip() for v in row))
            return "\n".join(lines)
    except Exception:
        pass
    return ""


def _ocr_page(page) -> str:
    """Rasterise page at 300 DPI and run Tesseract OCR on it."""
    try:
        mat = fitz.Matrix(300 / 72, 300 / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        img_bytes = pix.tobytes("png")
        pil_img = Image.open(io.BytesIO(img_bytes))
        return pytesseract.image_to_string(pil_img, config="--psm 6")
    except Exception as e:
        return f"[OCR ERROR: {e}]"


class DocumentExtractor:
    """
    Universal Nigerian bank statement extractor.
    Strategy per page:
      1. PyMuPDF word-level positional extraction  (best for digital PDFs)
      2. Camelot stream mode                        (fallback for borderless tables)
      3. Tesseract OCR                              (fallback for scanned pages)
    """

    def __init__(self, filepath: str):
        self.filepath = filepath

    def extract(self) -> str:
        ext = os.path.splitext(self.filepath)[1].lower()
        if ext == ".pdf":
            return self._extract_pdf()
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
            return self._extract_image()
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def _extract_pdf(self) -> str:
        all_pages = []

        doc = fitz.open(self.filepath)
        total = len(doc)

        for page_num, page in enumerate(doc, 1):
            print(f"    Page {page_num}/{total} ...", end="\r")

            # Strategy 1: PyMuPDF positional
            text = _extract_page_pymupdf(page)

            # Strategy 2: Camelot if PyMuPDF gave nothing useful
            if len(text.strip()) < 50:
                print(f"    Page {page_num}/{total} ... trying Camelot", end="\r")
                text = _try_camelot(self.filepath, page_num)

            # Strategy 3: OCR if still empty
            if len(text.strip()) < 50:
                print(f"    Page {page_num}/{total} ... running OCR  ", end="\r")
                text = _ocr_page(page)

            all_pages.append(f"\n--- PAGE {page_num} ---\n{text}")

        doc.close()
        print(f"\n    All {total} pages extracted.")
        return "\n".join(all_pages)

    def _extract_image(self) -> str:
        pil_img = Image.open(self.filepath)
        return pytesseract.image_to_string(pil_img, config="--psm 6")
