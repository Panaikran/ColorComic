import os
import unittest


class ResponsiveLayoutCssTests(unittest.TestCase):
    def test_action_rows_wrap_without_redesigning_layout(self):
        root = os.getcwd()
        with open(os.path.join(root, "static", "css", "style.css"), encoding="utf-8") as handle:
            css = handle.read()

        self.assertIn(".recent-output-item", css)
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn(".recent-output-details", css)
        self.assertIn("flex: 1 1 260px", css)
        self.assertIn(".recent-output-actions .btn,\n.processing-actions .btn", css)
        self.assertIn("white-space: normal", css)
        self.assertIn(".processing-actions", css)
        self.assertIn("flex: 1 1 180px", css)

    def test_processing_completion_actions_use_responsive_class(self):
        root = os.getcwd()
        with open(os.path.join(root, "templates", "processing.html"), encoding="utf-8") as handle:
            template = handle.read()

        self.assertIn('class="flex mt-2 processing-actions"', template)


if __name__ == "__main__":
    unittest.main()
