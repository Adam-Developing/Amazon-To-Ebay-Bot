import unittest

from bulk_parser import parse_bulk_items


class ParseBulkItemsTests(unittest.TestCase):
    def test_parses_markdown_url_metadata_and_title(self):
        text = """bulk text:
Note:Attic on left of ladder on Iceland bag
quantity: 13
Size Name: 24 count (Pack of 1)
Vitamin C Under Eye Patches
[https://www.amazon.co.uk/dp/B0FB5YDC23?ref=orders&th=1](https://www.amazon.co.uk/dp/B0FB5YDC23?ref=orders&th=1)
"""

        self.assertEqual(parse_bulk_items(text), [{
            "url": "https://www.amazon.co.uk/dp/B0FB5YDC23?ref=orders&th=1",
            "quantity": 13,
            "note": "Attic on left of ladder on Iceland bag",
            "custom_specifics": {"Size Name": "24 count (Pack of 1)"},
            "title": "Vitamin C Under Eye Patches",
        }])

    def test_uses_last_product_when_a_block_contains_a_stale_product(self):
        text = """5
Note: top shelf
quantity: 13
Old product title
https://www.amazon.co.uk/dp/B000000001
Correct product title
https://www.amazon.co.uk/dp/B000000002
"""

        item = parse_bulk_items(text)[0]
        self.assertEqual(item["url"], "https://www.amazon.co.uk/dp/B000000002")
        self.assertEqual(item["title"], "Correct product title")

    def test_recovers_missing_url_from_asin_without_leaking_notes(self):
        text = """20
note: Garage Box 116 B0DP7QMN53
Quantity: 3
First product title

21
this malformed block must not become a global note

22
note: A different shelf X002MJ7G89
Second product title
https://www.amazon.co.uk/dp/B0H6FZLFGP
"""

        items = parse_bulk_items(text)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["url"], "https://www.amazon.co.uk/dp/B0DP7QMN53")
        self.assertEqual(items[0]["quantity"], 3)
        self.assertEqual(items[1]["note"], "A different shelf X002MJ7G89")

    def test_joins_multiline_title_and_parses_set_name(self):
        text = """11
Set name: Wrist Brace - Medium
First part of the product title
second part of the product title
https://www.amazon.co.uk/dp/B0716Z2X4R
"""

        item = parse_bulk_items(text)[0]
        self.assertEqual(item["custom_specifics"], {"Set name": "Wrist Brace - Medium"})
        self.assertEqual(
            item["title"],
            "First part of the product title second part of the product title",
        )


if __name__ == "__main__":
    unittest.main()
