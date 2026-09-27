from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from rest_framework.authtoken.models import Token


class HttpOnlyCookieAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.username = "testagent"
        self.password = "StrongPassword@123"
        self.email = "agent@example.com"
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
            email=self.email,
            first_name="Test",
            last_name="Agent",
        )

    def test_login_sets_httponly_cookie_without_token_in_body(self):
        """
        Verify that login sets the HttpOnly cookie 'insure_token'
        and does NOT expose the raw token in the response JSON.
        """
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Raw token must not be in response body (Inspect Mode security)
        self.assertNotIn("token", response.data)
        self.assertIn("user", response.data)
        self.assertEqual(response.data["user"]["username"], self.username)

        # HttpOnly cookie must be set
        self.assertIn("insure_token", response.cookies)
        cookie = response.cookies["insure_token"]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")

    def test_login_backward_compatibility_include_token(self):
        """
        Verify that external/mobile clients requesting include_token=True
        still receive the token in response JSON.
        """
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.username, "password": self.password, "include_token": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertIn("insure_token", response.cookies)

    def test_authenticated_request_via_httponly_cookie(self):
        """
        Verify that protected endpoints authenticate successfully
        using only the HttpOnly cookie (no Authorization header).
        """
        # First login to establish cookie
        login_resp = self.client.post(
            "/api/auth/login/",
            {"username": self.username, "password": self.password},
            format="json",
        )
        token_key = login_resp.cookies["insure_token"].value

        # Make request to protected profile endpoint with cookie
        self.client.cookies["insure_token"] = token_key
        profile_resp = self.client.get("/api/auth/profile/")
        self.assertEqual(profile_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(profile_resp.data["username"], self.username)

    def test_authenticated_request_via_header_fallback(self):
        """
        Verify that API callers passing 'Authorization: Token ...' header
        continue to work seamlessly (backward compatibility).
        """
        token = Token.objects.create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = client.get("/api/auth/profile/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], self.username)

    def test_stale_cookie_does_not_break_login(self):
        """
        Verify that if the browser sends a stale or deleted cookie,
        LoginView does NOT reject with 401, but allows the user to log in.
        """
        self.client.cookies["insure_token"] = "invalid_or_stale_token_key"
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.username, "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("insure_token", response.cookies)

    def test_logout_deletes_cookie_and_token(self):
        """
        Verify that logout removes the token from the DB and clears the cookie.
        """
        login_resp = self.client.post(
            "/api/auth/login/",
            {"username": self.username, "password": self.password},
            format="json",
        )
        token_key = login_resp.cookies["insure_token"].value
        self.assertTrue(Token.objects.filter(key=token_key).exists())

        self.client.cookies["insure_token"] = token_key
        logout_resp = self.client.post("/api/auth/logout/")
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        # Token removed from DB
        self.assertFalse(Token.objects.filter(key=token_key).exists())

        # Cookie deleted
        self.assertEqual(logout_resp.cookies["insure_token"].value, "")
