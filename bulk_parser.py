import re
from typing import Dict, List, Optional, Tuple


COMMON_SPEC_KEYS = {
    "size", "size name", "style", "style name", "set", "set name",
    "colour", "colour name", "color", "color name", "pattern", "model",
    "material", "capacity", "length", "width", "height", "flavour",
    "flavor", "pack size", "variant", "type", "edition", "storage",
    "ram", "connectivity", "platform", "shape", "fit", "waist", "chest",
    "age range", "gender", "power", "wattage", "voltage", "number of items",
    "brand", "compatible devices", "form factor", "special feature",
    "theme", "item weight", "package dimensions",
}

# Stop before Markdown's closing ``]``/``)`` instead of swallowing both copies
# from a link in the form [https://amazon/...](https://amazon/...).
_url_re = re.compile(
    r'https?://(?:[a-z0-9-]+\.)*amazon\.[a-z.]{2,}/[^\s<>\]\)]+',
    re.IGNORECASE,
)
_asin_re = re.compile(r'(?<![A-Z0-9])(B[A-Z0-9]{9})(?![A-Z0-9])', re.IGNORECASE)
_qty_re = re.compile(r'^\s*(?:qty|quantity)\s*[:=-]\s*(\d+)\s*$', re.IGNORECASE)
_note_re = re.compile(r'^\s*note\b(?:\s*:\s*|\s+)(.+?)\s*$', re.IGNORECASE)
_block_separator_re = re.compile(r'^\s*(?:item\s+)?\d+\s*[.)-]?\s*$', re.IGNORECASE)
_legacy_separator_re = re.compile(r'^\s*J{5,}\s*$', re.IGNORECASE)
_heading_re = re.compile(r'^\s*bulk\s+text\s*:?\s*$', re.IGNORECASE)
_code_only_re = re.compile(r'^[A-Z0-9-]{6,}$', re.IGNORECASE)


def _parse_specifics_line(line: str) -> Dict[str, str]:
    """Parse one or more ``Key: Value`` item-specific pairs."""
    segments = [segment.strip() for segment in line.split('|')]
    pairs: List[Tuple[str, str]] = []
    for segment in segments:
        if ':' not in segment:
            continue
        key, value = segment.split(':', 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            pairs.append((key, value))

    # Multiple pipe-delimited fields are unambiguously item specifics. For a
    # single field, retain the allow-list so colons in product titles are safe.
    if len(pairs) >= 2:
        return dict(pairs)
    if len(pairs) == 1 and pairs[0][0].lower() in COMMON_SPEC_KEYS:
        return dict(pairs)
    return {}


def _split_blocks(text: str) -> List[List[str]]:
    blocks: List[List[str]] = []
    current: List[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _block_separator_re.fullmatch(line) or _legacy_separator_re.fullmatch(line):
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)

    if current:
        blocks.append(current)
    return blocks


def _urls_in_line(line: str) -> List[str]:
    urls: List[str] = []
    for match in _url_re.finditer(line):
        url = match.group(0).rstrip('.,;:')
        if url not in urls:
            urls.append(url)
    return urls


def _find_product_url(block: List[str]) -> Tuple[str, Optional[int], Optional[int]]:
    """Return the last URL and the line range belonging to that product.

    A numbered block occasionally contains a stale product and URL followed by
    the real product. Selecting the final URL and the text since the previous
    URL keeps the title paired with the correct Amazon listing.
    """
    url_lines: List[Tuple[int, str]] = []
    for line_index, line in enumerate(block):
        for url in _urls_in_line(line):
            url_lines.append((line_index, url))

    if url_lines:
        selected_line, selected_url = url_lines[-1]
        previous_line = url_lines[-2][0] if len(url_lines) > 1 else None
        title_start = previous_line + 1 if previous_line is not None else 0
        return selected_url, title_start, selected_line

    # A missing URL can be recovered from a standard Amazon ASIN. Restricting
    # this to ASINs beginning with B avoids treating X-prefixed stock codes as
    # product IDs.
    for line in block:
        asin_match = _asin_re.search(line)
        if asin_match:
            asin = asin_match.group(1).upper()
            return f"https://www.amazon.co.uk/dp/{asin}", 0, len(block)

    return '', None, None


def _is_metadata_line(line: str) -> bool:
    return bool(
        _heading_re.fullmatch(line)
        or _qty_re.fullmatch(line)
        or _note_re.fullmatch(line)
        or _parse_specifics_line(line)
        or _urls_in_line(line)
    )


def _parse_title(block: List[str], start: int, end: int) -> str:
    candidates = [
        line.strip()
        for line in block[start:end]
        if not _is_metadata_line(line)
        and not _code_only_re.fullmatch(line.strip())
    ]

    # URLs normally follow titles. If the chosen range contains no title,
    # tolerate the inverse order and look across the whole block.
    if not candidates:
        candidates = [
            line.strip()
            for line in block
            if not _is_metadata_line(line)
            and not _code_only_re.fullmatch(line.strip())
        ]
    return ' '.join(candidates).strip()


def parse_bulk_items(text: str) -> List[Dict]:
    """Parse numbered Amazon bulk-listing text into item dictionaries."""
    items: List[Dict] = []

    for block in _split_blocks(text):
        url, title_start, title_end = _find_product_url(block)
        if not url:
            # A malformed/heading block is local to itself. It must never be
            # turned into a global note that contaminates every later item.
            continue

        quantity: Optional[int] = None
        notes: List[str] = []
        custom_specifics: Dict[str, str] = {}

        for line in block:
            quantity_match = _qty_re.fullmatch(line)
            if quantity_match:
                quantity = int(quantity_match.group(1))
                continue

            note_match = _note_re.fullmatch(line)
            if note_match:
                note = note_match.group(1).strip()
                if note and note not in notes:
                    notes.append(note)
                continue

            if not _urls_in_line(line):
                custom_specifics.update(_parse_specifics_line(line))

        items.append({
            "url": url,
            "quantity": quantity if quantity is not None else 1,
            "note": ' \n '.join(notes),
            "custom_specifics": custom_specifics,
            "title": _parse_title(
                block,
                title_start if title_start is not None else 0,
                title_end if title_end is not None else len(block),
            ),
        })

    return items
