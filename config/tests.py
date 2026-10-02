import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class EnvironmentConfigurationTests(SimpleTestCase):
    """Check startup configuration in a fresh interpreter, without changing live settings."""

    def run_settings(self, overrides, expression=""):
        environment = os.environ.copy()
        environment.update({
            "SECRET_KEY": "test-only-generated-key-not-for-production-12345678901234567890",
            "DEBUG": "True",
            "DB_ENGINE": "sqlite",
            **overrides,
        })
        return subprocess.run(
            [sys.executable, "-c", "from config import settings as s; " + expression],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_missing_secret_rejects_startup(self):
        result = self.run_settings({"SECRET_KEY": ""})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set SECRET_KEY", result.stderr)

    def test_template_secret_rejects_startup(self):
        result = self.run_settings({"SECRET_KEY": "replace-with-generated-secret"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Set SECRET_KEY", result.stderr)

    def test_unknown_database_engine_rejects_startup(self):
        result = self.run_settings({"DB_ENGINE": "postgreql"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DB_ENGINE must be", result.stderr)

    def test_explicit_origins_and_production_cookie_flags(self):
        result = self.run_settings(
            {"DEBUG": "False", "CORS_ALLOWED_ORIGINS": "https://app.example.com"},
            "assert s.CORS_ALLOWED_ORIGINS == ['https://app.example.com']; "
            "assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
