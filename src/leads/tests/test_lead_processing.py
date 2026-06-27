import unittest

from config import OUTPUT_COLUMNS
from lead_processing import (
    deduplicate_leads,
    extract_emails,
    extract_phones,
    sanitize_sheet_name,
)


class LeadProcessingTest(unittest.TestCase):
    def test_extract_emails_deduplicates_case_insensitively(self):
        self.assertEqual(
            extract_emails("A@EXAMPLE.com b@test.org a@example.com"),
            ["a@example.com", "b@test.org"],
        )

    def test_extract_phones_accepts_plus_prefixed_country_code(self):
        self.assertEqual(
            extract_phones("+44 20 1234 5678", country_code="+44", filter_enabled=True),
            ["+442012345678"],
        )

    def test_deduplicate_leads_uses_contact_and_website_identity(self):
        email_col = OUTPUT_COLUMNS[3]
        phone_col = OUTPUT_COLUMNS[4]
        website_col = OUTPUT_COLUMNS[6]
        leads = [
            {email_col: "a@example.com", phone_col: "+4420", website_col: "https://a.test"},
            {email_col: "a@example.com", phone_col: "+4420", website_col: "https://a.test"},
            {email_col: "b@example.com", phone_col: "+4420", website_col: "https://a.test"},
        ]

        self.assertEqual(len(deduplicate_leads(leads)), 2)

    def test_sanitize_sheet_name_replaces_invalid_chars_and_truncates(self):
        value = sanitize_sheet_name("a:b/c*d?e[f]g\\h" * 4)

        self.assertLessEqual(len(value), 31)
        for char in "[]:*?/\\":
            self.assertNotIn(char, value)


if __name__ == "__main__":
    unittest.main()
