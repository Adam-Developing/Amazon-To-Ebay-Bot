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
    """
    Parse bulk text into items.
    Handles 'header notes' (e.g. 'Box 107') that apply to subsequent items
    until a new header note is found.
    """
    lines = [ln.rstrip() for ln in text.strip().splitlines()]

    blocks = []
    current = []

    # Split blocks on blank lines OR a line that's just a number (e.g., "1", "2")
    for ln in lines:
        if not ln.strip() or re.match(r'^\s*\d+\s*$', ln):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(ln)
    if current:
        blocks.append(current)

    items = []
    current_global_note = ""  # This stores the "sticky" note (e.g., "Box 107")

    for block in blocks:
        url = ''
        qty = None
        # collect multiple local notes, then join later
        local_notes: List[str] = []
        custom_specifics: Dict[str, str] = {}

        # 1. Scan block for URL and properties
        for ln in block:
            # Check URL
            if not url:
                m_url = _url_re.search(ln)
                if m_url:
                    url = m_url.group(0).strip().rstrip(').,]')
                    continue

            # Check Quantity
            m_qty = _qty_re.match(ln)
            if m_qty:
                qty = int(m_qty.group(1))
                continue

            # Check Explicit Note (inside the block) - collect all note lines
            m_note = _note_re.match(ln)
            if m_note:
                note_val = m_note.group(1).strip()
                if note_val:
                    local_notes.append(note_val)
                continue

            # Check Specifics (Key: Value)
            if ':' in ln and not ln.lower().startswith(('quantity', 'qty', 'note')) and not _url_re.search(ln):
                cand = _parse_specifics_line(ln)
                if cand:
                    custom_specifics.update(cand)

        # 2. Heuristic: Is this block a "Header Note" or an "Item"?
        if not url:
            # If a block has NO url, we treat the entire text as a new context/note
            # for following items (e.g. "Box 107").
            text_content = " ".join(block).strip()
            if text_content:
                current_global_note = text_content
            continue

        # 3. It is an item (has URL). Apply logic.
        # Merge local notes; if none, use the global header note. If both exist, combine them.
        final_note_parts: List[str] = []
        if current_global_note:
            final_note_parts.append(current_global_note)
        if local_notes:
            # Remove duplicates while preserving order
            seen = set()
            unique_local = []
            for n in local_notes:
                if n not in seen:
                    seen.add(n)
                    unique_local.append(n)
            final_note_parts.extend(unique_local)

        final_note = ' \n '.join(final_note_parts).strip()

        items.append({
            "url": url,
            "quantity": qty if qty is not None else 1,
            "note": final_note,
            "custom_specifics": custom_specifics
        })

    return items
