from pathlib import Path
import tempfile

from django.test import SimpleTestCase
from dotenv import dotenv_values

from .configure_local import configure_local


class LocalEnvironmentSetupTests(SimpleTestCase):
    def test_creates_a_distinct_secret_for_each_installation(self):
        keys = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".env.example").write_text("SECRET_KEY=replace-with-generated-secret\nDEBUG=True\n")
                self.assertTrue(configure_local(root))
                values = dotenv_values(root / ".env")
                self.assertEqual(values["DEBUG"], "True")
                self.assertGreaterEqual(len(values["SECRET_KEY"]), 50)
                self.assertNotEqual(values["SECRET_KEY"], "replace-with-generated-secret")
                keys.append(values["SECRET_KEY"])
        self.assertNotEqual(keys[0], keys[1])

    def test_preserves_an_existing_environment_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = b"SECRET_KEY=existing-private-key\r\nDEBUG=False\r\n"
            (root / ".env").write_bytes(original)
            self.assertFalse(configure_local(root))
            self.assertEqual((root / ".env").read_bytes(), original)
