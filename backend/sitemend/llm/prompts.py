"""Prompt for one page session."""

from __future__ import annotations

from .base import FieldSpec

SYSTEM_PROMPT = """You write SEO text for one page of a small online shop: page titles, meta descriptions and image alt text.

Rules:
- Submit every piece of text with the submit_fix tool. Text that is not submitted is thrown away.
- submit_fix runs checks and answers with accepted true or false plus reasons. When it rejects, rewrite to fix every reason and submit again. You have at most 3 tries per item.
- Use only facts that appear in the page text you are given. Never add numbers, sizes, prices, materials, offers or claims that are not on the page.
- Write plainly, like the shop owner would. No hype, no filler, no exclamation marks.
- Titles: 30 to 60 characters, include the target query words naturally.
- Meta descriptions: 110 to 155 characters, include the target query words, say what the page offers.
- Alt text: 10 to 125 characters, describe what the image shows, no "image of" and no keyword stuffing.
- When every item is accepted or out of tries, reply with the single word DONE."""

FIELD_NAMES = {"title": "Title", "meta_description": "Meta description", "alt": "Alt text"}


def build_prompt(*, path: str, page_text: str, target_query: str, queries: list[str], fields: tuple[FieldSpec, ...],
                 custom_instructions: str, never_use: list[str]) -> str:
    lines = [f"Page: {path}", f"Target query: {target_query}"]
    if queries[1:]:
        lines.append("Other queries people use: " + "; ".join(queries[1:]))
    if custom_instructions.strip():
        lines.append("Site instructions from the owner: " + custom_instructions.strip())
    if never_use:
        lines.append("Never use these words: " + ", ".join(never_use))
    lines.append("")
    lines.append("Items to write (call submit_fix once per item, with field and target exactly as shown):")
    for f in fields:
        current = f.current or "(none)"
        if f.field == "alt":
            lines.append(f'- field="alt" target="{f.target}" (image near: {f.context or "no caption"})')
        else:
            lines.append(f'- field="{f.field}" target="" (current {FIELD_NAMES[f.field].lower()}: {current})')
    lines.append("")
    lines.append("Visible page text:")
    lines.append(page_text[:3000])
    return "\n".join(lines)


def max_turns_for(fields: tuple[FieldSpec, ...]) -> int:
    """Up to 3 tries per item plus a closing turn, bounded."""
    return min(16, 3 * len(fields) + 2)
