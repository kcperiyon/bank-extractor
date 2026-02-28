def chunk_text(text: str, chunk_size: int = 6000, max_chars: int = None) -> list:
    """Split text into chunks of approximately chunk_size characters."""
    size = max_chars or chunk_size
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        if end < len(text):
            newline = text.rfind('\n', start, end)
            if newline > start:
                end = newline
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]
