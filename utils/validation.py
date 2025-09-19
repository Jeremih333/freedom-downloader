import re
from urllib.parse import urlparse, quote

URL_RE = re.compile(r"https?://", re.I)

def is_url(text: str) -> bool:
    return bool(URL_RE.search(text))

def sanitize_filename(name: str) -> str:
    # keep safe filenames
    return re.sub(r'[^A-Za-z0-9._\- ]+', '_', name)[:200]

def safe_quote(s: str) -> str:
    return quote(s, safe='')
