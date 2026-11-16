"""Evidence remains inspectable offline; untrusted labels cannot become markup."""
from pathlib import Path
import tempfile
import unittest

from scripts.appearance_diagnostic_corpus.authoring import png_rgba
from scripts.diagnostic_qualification.presentation import render_page


class OfflineEvidencePageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)

    def test_original_asset_is_embedded_and_untrusted_text_is_escaped(self):
        image = self.root / "original.png"
        original = png_rgba(1, 1, bytes((5, 8, 13, 255)))
        image.write_bytes(original)
        output = self.root / "review.html"
        render_page(output, {"qualification_status": "unknown", "note": "</pre><script>bad()</script>"},
                    pictures=(("<bad label>", image),), review_template={"comment": "</script><script>bad()</script>"})
        text = output.read_text(encoding="utf-8")
        self.assertEqual(image.read_bytes(), original)
        self.assertIn("data:image/png;base64,", text)
        self.assertIn("&lt;bad label&gt;", text)
        self.assertNotIn("</pre><script>bad()", text)
        self.assertNotIn("</script><script>bad()", text)
        self.assertIn("connect-src 'none'", text)
        self.assertIn("aucune validation globale", text)

    def test_no_fake_review_form_when_no_bound_packet_exists(self):
        output = self.root / "unavailable.html"
        render_page(output, {"qualification_status": "unknown"})
        text = output.read_text(encoding="utf-8")
        self.assertNotIn('id="review"', text)
        self.assertIn("Des preuves restent à compléter", text)


if __name__ == "__main__":
    unittest.main()
