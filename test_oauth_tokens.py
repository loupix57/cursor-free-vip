"""Tests unitaires pour la logique OAuth / session (sans appels réseau réels)."""
import io
import sys
import unittest
from unittest.mock import patch

from get_user_token import (
    _oauth_refresh_candidates,
    _same_jwt_token,
    extract_jwt_token,
    prepare_tokens_for_storage,
    refresh_cursor_oauth_tokens,
)


FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ0ZXN0In0."
    "signature"
)
OTHER_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJvdGhlciJ9."
    "signature"
)


class OAuthTokenTests(unittest.TestCase):
    def setUp(self):
        self._stdout = sys.stdout
        sys.stdout = io.StringIO()

    def tearDown(self):
        sys.stdout = self._stdout

    def test_extract_jwt_from_workos_cookie(self):
        raw = "user_01ABC%3A%3A" + FAKE_JWT
        self.assertEqual(extract_jwt_token(raw), FAKE_JWT)

    def test_same_jwt_token(self):
        self.assertTrue(_same_jwt_token(FAKE_JWT, FAKE_JWT))
        self.assertFalse(_same_jwt_token(FAKE_JWT, OTHER_JWT))

    def test_oauth_candidates_prefers_distinct_refresh(self):
        cands = _oauth_refresh_candidates(OTHER_JWT, access_token=FAKE_JWT)
        self.assertEqual(cands[0], OTHER_JWT)
        self.assertIn(FAKE_JWT, cands)

    @patch("builtins.print")
    @patch("get_user_token.verify_cursor_session_active", return_value=True)
    @patch("get_user_token.requests.post")
    def test_cookie_session_skips_oauth_api(self, mock_post, _mock_verify, _mock_print):
        result = refresh_cursor_oauth_tokens(FAKE_JWT, access_token=FAKE_JWT)
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("via"), "api")
        mock_post.assert_not_called()

    @patch("builtins.print")
    @patch("get_user_token.verify_cursor_session_active", return_value=True)
    @patch("get_user_token.requests.post")
    def test_prepare_tokens_skips_oauth_for_valid_cookie_session(self, mock_post, _mock_verify, _mock_print):
        result = prepare_tokens_for_storage(FAKE_JWT, FAKE_JWT, oauth_refresh=True)
        self.assertTrue(result["ok"])
        mock_post.assert_not_called()

    @patch("get_user_token.verify_cursor_session_active", return_value=False)
    @patch("get_user_token.requests.post")
    def test_prepare_tokens_strict_expired(self, mock_post, _mock_verify):
        mock_post.return_value.json.return_value = {
            "access_token": "",
            "shouldLogout": True,
        }
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "{}"
        result = prepare_tokens_for_storage(FAKE_JWT, FAKE_JWT, oauth_refresh=True, strict=True)
        self.assertFalse(result["ok"])
        self.assertEqual(result.get("error"), "reuse_token_expired")

    @patch("builtins.print")
    @patch("get_user_token.requests.post")
    def test_oauth_success_with_distinct_refresh(self, mock_post, _mock_print):
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = "{}"
        mock_post.return_value.json.return_value = {
            "access_token": FAKE_JWT,
            "refresh_token": OTHER_JWT,
            "shouldLogout": False,
        }
        result = refresh_cursor_oauth_tokens(OTHER_JWT, access_token=FAKE_JWT)
        self.assertTrue(result["ok"])
        self.assertEqual(result.get("via"), "oauth")
        mock_post.assert_called_once()


if __name__ == "__main__":
    unittest.main()
