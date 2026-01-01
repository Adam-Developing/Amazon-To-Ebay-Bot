# bulk_parser.py
import re
from typing import List, Dict

COMMON_SPEC_KEYS = {
    "size", "size name", "style", "style name", "colour", "colour name", "color",
    "pattern", "model", "material", "capacity", "length", "width", "height",
    "flavour", "flavor", "pack size", "variant", "type", "edition", "storage",
    "ram", "connectivity", "platform", "shape", "fit", "waist", "chest",
    "age range", "gender", "power", "wattage", "voltage"
}

_url_re = re.compile(r'https?://\S*amazon\.[a-z.]+/\S+', re.IGNORECASE)
_qty_re = re.compile(r'^\s*(?:qty|quantity)\s*:\s*(\d+)\s*$', re.IGNORECASE)
_note_re = re.compile(r'^\s*note\b[:\s]\s*(.+)$', re.IGNORECASE)

def _parse_specifics_line(line: str) -> Dict[str, str]:
    """Return {} unless line clearly looks like key:value pairs (| allowed). Avoids titles (e.g. '4:1 Extract')."""
    segments = [seg.strip() for seg in line.split('|')] if '|' in line else [line.strip()]
    pairs = []
    for seg in segments:
        if ':' in seg:
            k, v = seg.split(':', 1)
            k, v = k.strip(), v.strip()
            pairs.append((k, v))
    if len(pairs) >= 2:
        return {k: v for k, v in pairs if k and v}
    if len(pairs) == 1:
        k = pairs[0][0].strip().lower()
        if k in COMMON_SPEC_KEYS:  # only keep common single keys
            return {pairs[0][0].strip(): pairs[0][1].strip()}
    return {}

def parse_bulk_items(text: str) -> List[Dict]:
    """Parse bulk text into items of the form: {url, quantity, note, custom_specifics}."""
    lines = [ln.rstrip() for ln in text.strip().splitlines()]

    blocks, current = [], []
    for ln in lines:
        # New: split blocks on blank lines OR a line that's just a number (e.g., "23")
        if not ln.strip() or re.match(r'^\s*\d+\s*$', ln):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(ln)
    if current:
        blocks.append(current)

    items = []
    for block in blocks:
        url, qty, note = '', None, ''
        custom_specifics: Dict[str, str] = {}

        for ln in block:
            if not url:
                m_url = _url_re.search(ln)
                if m_url:
                    # Trim common trailing punctuation/brackets
                    url = m_url.group(0).strip().rstrip(').,]')
                    continue

            m_qty = _qty_re.match(ln)
            if m_qty:
                qty = int(m_qty.group(1))
                continue

            m_note = _note_re.match(ln)
            if m_note:
                note = m_note.group(1).strip()
                continue

            # Specifics lines: "Key: Value | Key: Value" etc.
            if ':' in ln and not ln.lower().startswith(('quantity', 'qty', 'note')) and not _url_re.search(ln):
                cand = _parse_specifics_line(ln)
                if cand:
                    custom_specifics.update(cand)

        if url or qty is not None or note or custom_specifics:
            items.append({
                "url": url,
                "quantity": qty if qty is not None else 1,
                "note": note,
                "custom_specifics": custom_specifics
            })
    return items
