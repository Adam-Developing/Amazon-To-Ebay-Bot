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
            # Normalize repeated colons/spaces for parsing without mutating the original line used for title heuristics
            ln_norm = re.sub(r"\s*:\s*", ":", ln)
            ln_norm = re.sub(r":+", ":", ln_norm).strip()
            # Ensure a single space after colon for regex matching (e.g. "Quantity:5" -> "Quantity: 5")
            if ':' in ln_norm:
                parts = ln_norm.split(':', 1)
                ln_matchable = f"{parts[0].strip()}: {parts[1].strip()}"
            else:
                ln_matchable = ln_norm

            # Check URL (use original line to preserve full URL text)
            if not url:
                m_url = _url_re.search(ln)
                if m_url:
                    url = m_url.group(0).strip().rstrip(').,]')
                    continue

            # Check Quantity using the normalized, matchable line
            m_qty = _qty_re.match(ln_matchable)
            if m_qty:
                try:
                    qty = int(m_qty.group(1))
                except Exception:
                    qty = None
                continue

            # Check Explicit Note (inside the block) - collect all note lines (normalized)
            m_note = _note_re.match(ln_matchable)
            if m_note:
                note_val = m_note.group(1).strip()
                if note_val:
                    local_notes.append(note_val)
                continue

            # Check Specifics (Key: Value) using normalized form
            if ':' in ln_matchable and not ln_matchable.lower().startswith(('quantity', 'qty', 'note')) and not _url_re.search(ln):
                cand = _parse_specifics_line(ln_matchable)
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

        # 4. New: attempt to heuristically find a product title inside the block.
        # Candidates are lines that are not URL/qty/note and do not look like key:value specifics.
        title_candidates: List[str] = []
        for ln in block:
            # Skip URL/qty/note lines (use normalized matchable representation for qty/note)
            ln_norm = re.sub(r"\s*:\s*", ":", ln)
            ln_norm = re.sub(r":+", ":", ln_norm).strip()
            if ':' in ln_norm:
                parts = ln_norm.split(':', 1)
                ln_matchable = f"{parts[0].strip()}: {parts[1].strip()}"
            else:
                ln_matchable = ln_norm

            if _url_re.search(ln) or _qty_re.match(ln_matchable) or _note_re.match(ln_matchable):
                continue
            # If the line contains a ':' but parses as specifics, skip it
            if ':' in ln and _parse_specifics_line(ln):
                continue
            # Skip extremely short lines
            stripped = ln.strip()
            if len(stripped) < 10:
                continue
            # Heuristic: avoid lines that look like codes (mostly uppercase alnum, like X002F8MT1B)
            if re.match(r'^[A-Z0-9\-]{6,}$', stripped):
                continue
            title_candidates.append(stripped)

        # Prefer the longest candidate (likely the product title); fallback to first candidate
        parsed_title = ''
        if title_candidates:
            title_candidates.sort(key=lambda s: len(s), reverse=True)
            parsed_title = title_candidates[0]

        items.append({
            "url": url,
            "quantity": qty if qty is not None else 1,
            "note": final_note,
            "custom_specifics": custom_specifics,
            "title": parsed_title,
        })

    return items
