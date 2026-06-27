import re
from typing import List, Dict

COMMON_SPEC_KEYS = {
    "size", "size name", "style", "style name", "colour", "colour name", "color",
    "pattern", "model", "material", "capacity", "length", "width", "height",
    "flavour", "flavor", "pack size", "variant", "type", "edition", "storage",
    "ram", "connectivity", "platform", "shape", "fit", "waist", "chest",
    "age range", "gender", "power", "wattage", "voltage", "number of items",
    "brand", "compatible devices", "form factor", "special feature",
    "theme", "item weight", "package dimensions"
}

_url_re = re.compile(r'https?://\S*amazon\.[a-z.]+/\S+', re.IGNORECASE)
_qty_re = re.compile(r'^\s*(?:qty|quantity)\s*:\s*(\d+)\s*$', re.IGNORECASE)
_note_re = re.compile(r'^\s*note\b[:\s]\s*(.+)$', re.IGNORECASE)


def _parse_specifics_line(line: str) -> Dict[str, str]:
    segments = [seg.strip() for seg in line.split('|')] if '|' in line else [line.strip()]
    pairs = []
    for seg in segments:
        if ':' in seg:
            k, v = seg.split(':', 1)
            pairs.append((k.strip(), v.strip()))
    if len(pairs) >= 2:
        return {k: v for k, v in pairs if k and v}
    if len(pairs) == 1:
        k = pairs[0][0].strip().lower()
        if k in COMMON_SPEC_KEYS:
            return {pairs[0][0].strip(): pairs[0][1].strip()}
    return {}


def parse_bulk_items(text: str) -> List[Dict]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    blocks = []
    current = []

    for ln in lines:
        if re.match(r'^\d+$', ln) or re.match(r'^J{5,}$', ln, re.IGNORECASE):
            if current:
                blocks.append(current)
                current = []
        else:
            current.append(ln)
    if current:
        blocks.append(current)

    items = []
    current_global_note = ""

    for block in blocks:
        url = ''
        qty = None
        local_notes = []
        custom_specifics = {}
        title_candidates = []

        for ln in block:
            ln_norm = re.sub(r"\s*:\s*", ":", ln)
            ln_norm = re.sub(r":+", ":", ln_norm).strip()
            ln_matchable = f"{ln_norm.split(':', 1)[0].strip()}: {ln_norm.split(':', 1)[1].strip()}" if ':' in ln_norm else ln_norm

            if not url:
                m_url = _url_re.search(ln)
                if m_url:
                    url = m_url.group(0).strip().rstrip(').,]')
                    continue

            m_qty = _qty_re.match(ln_matchable)
            if m_qty:
                try:
                    qty = int(m_qty.group(1))
                except ValueError:
                    pass
                continue

            m_note = _note_re.match(ln_matchable)
            if m_note:
                note_val = m_note.group(1).strip()
                if note_val:
                    local_notes.append(note_val)
                continue

            if ':' in ln_matchable and not ln_matchable.lower().startswith(
                    ('quantity', 'qty', 'note')) and not _url_re.search(ln):
                cand = _parse_specifics_line(ln_matchable)
                if cand:
                    custom_specifics.update(cand)
                    continue

            stripped = ln.strip()
            if len(stripped) >= 10 and not re.match(r'^[A-Z0-9\-]{6,}$', stripped):
                title_candidates.append(stripped)

        if not url:
            if block:
                current_global_note = " ".join(block).strip()
            continue

        final_note_parts = []
        if current_global_note:
            final_note_parts.append(current_global_note)

        seen = set()
        for n in local_notes:
            if n not in seen:
                seen.add(n)
                final_note_parts.append(n)

        parsed_title = ''
        if title_candidates:
            title_candidates.sort(key=len, reverse=True)
            parsed_title = title_candidates[0]

        items.append({
            "url": url,
            "quantity": qty if qty is not None else 1,
            "note": ' \n '.join(final_note_parts).strip(),
            "custom_specifics": custom_specifics,
            "title": parsed_title,
        })

    return items