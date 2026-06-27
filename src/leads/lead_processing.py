"""Pure lead processing helpers used by the scraper pipeline."""

import hashlib
import re

from config import EMAIL_REGEX, EXCEL_SHEET_MAXLEN, OUTPUT_COLUMNS, PHONE_REGEX


EMAIL_COL = OUTPUT_COLUMNS[3]
PHONE_COL = OUTPUT_COLUMNS[4]
WEBSITE_COL = OUTPUT_COLUMNS[6]


def extract_emails(text: str) -> list[str]:
    """Extract unique email addresses while preserving first-seen order."""
    matches = re.findall(EMAIL_REGEX, text, re.IGNORECASE)
    seen = set()
    result = []
    for match in matches:
        email = match.lower()
        if email not in seen:
            seen.add(email)
            result.append(email)
    return result


def extract_phones(
    text: str,
    country_code: str = "",
    filter_enabled: bool = False,
) -> list[str]:
    """Extract normalized phone-like strings from page text."""
    matches = re.findall(PHONE_REGEX, text)
    seen = set()
    result = []
    normalized_country_code = country_code.lstrip("+")

    for match in matches:
        phone = match.strip().replace(" ", "").replace("-", "").replace(".", "")
        if len(phone) < 7:
            continue
        if filter_enabled and normalized_country_code:
            if not phone.lstrip("+").startswith(normalized_country_code):
                continue
        if phone not in seen:
            seen.add(phone)
            result.append(phone)

    return result[:20]


def deduplicate_leads(leads: list[dict]) -> list[dict]:
    """Deduplicate leads by contact and website fields."""
    seen = set()
    unique = []
    for lead in leads:
        key = f"{lead.get(EMAIL_COL, '')}|{lead.get(PHONE_COL, '')}|{lead.get(WEBSITE_COL, '')}"
        fingerprint = hashlib.md5(key.encode("utf-8")).hexdigest()
        if fingerprint not in seen:
            seen.add(fingerprint)
            unique.append(lead)
    return unique


def sanitize_sheet_name(name: str) -> str:
    """Make a value safe for use as an Excel sheet name."""
    for char in "[]:*?/\\":
        name = name.replace(char, "_")
    return name[:EXCEL_SHEET_MAXLEN]
