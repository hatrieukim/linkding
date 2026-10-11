from unittest import mock

from django.test import TestCase

from bookmarks.services import embed_checker
from bookmarks.services.http_client import BlockedAddressError, RequestException


class MockStreamingResponse:
    def __init__(self, headers=None, status_code=200):
        self.headers = headers or {}
        self.status_code = status_code

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class EmbedCheckerTestCase(TestCase):
    def setUp(self) -> None:
        self.mock_get_patcher = mock.patch("bookmarks.services.http_client.get")
        self.mock_get = self.mock_get_patcher.start()
        self.mock_get.return_value = MockStreamingResponse()

    def tearDown(self) -> None:
        self.mock_get_patcher.stop()

    def check(self, headers=None, status_code=200):
        self.mock_get.return_value = MockStreamingResponse(headers, status_code)
        return embed_checker.check_embeddable("https://example.com")

    def test_allows_embedding_without_restricting_headers(self):
        self.assertIs(self.check({"Content-Type": "text/html"}), True)

    def test_uses_http_client_and_does_not_read_body(self):
        self.check()

        self.mock_get.assert_called_once()
        args, kwargs = self.mock_get.call_args
        self.assertEqual(args[0], "https://example.com")
        self.assertTrue(kwargs["stream"])

    def test_x_frame_options_block_embedding(self):
        for value in ["DENY", "deny", "SAMEORIGIN", "ALLOW-FROM https://example.org"]:
            with self.subTest(value=value):
                self.assertIs(self.check({"X-Frame-Options": value}), False)

    def test_header_names_are_case_insensitive(self):
        from requests.structures import CaseInsensitiveDict

        headers = CaseInsensitiveDict({"x-frame-options": "DENY"})
        self.assertIs(self.check(headers), False)

    def test_frame_ancestors_none_or_self_block_embedding(self):
        for value in [
            "frame-ancestors 'none'",
            "frame-ancestors 'self'",
            "default-src 'self'; frame-ancestors 'self' https://example.org",
            "frame-ancestors https://*.example.org",
        ]:
            with self.subTest(value=value):
                self.assertIs(self.check({"Content-Security-Policy": value}), False)

    def test_frame_ancestors_wildcard_allows_embedding(self):
        for value in [
            "frame-ancestors *",
            "default-src 'self'; frame-ancestors https:",
            "FRAME-ANCESTORS *",
        ]:
            with self.subTest(value=value):
                self.assertIs(self.check({"Content-Security-Policy": value}), True)

    def test_csp_without_frame_ancestors_does_not_block_embedding(self):
        headers = {"Content-Security-Policy": "default-src 'self'; script-src 'none'"}
        self.assertIs(self.check(headers), True)

    def test_frame_ancestors_takes_precedence_over_x_frame_options(self):
        headers = {
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "frame-ancestors *",
        }
        self.assertIs(self.check(headers), True)

    def test_x_frame_options_applies_if_csp_has_no_frame_ancestors(self):
        headers = {
            "X-Frame-Options": "SAMEORIGIN",
            "Content-Security-Policy": "default-src 'self'",
        }
        self.assertIs(self.check(headers), False)

    def test_multiple_policies_must_all_allow_embedding(self):
        headers = {
            "Content-Security-Policy": "frame-ancestors *, frame-ancestors 'none'"
        }
        self.assertIs(self.check(headers), False)

    def test_returns_none_for_error_responses(self):
        self.assertIsNone(self.check(status_code=500))
        self.assertIsNone(self.check(status_code=404))

    def test_returns_none_on_request_errors(self):
        self.mock_get.side_effect = RequestException("boom")
        self.assertIsNone(embed_checker.check_embeddable("https://example.com"))

    def test_returns_none_for_blocked_addresses(self):
        self.mock_get.side_effect = BlockedAddressError(
            "localhost", mock.Mock(__str__=lambda self: "127.0.0.1")
        )
        self.assertIsNone(embed_checker.check_embeddable("http://localhost"))
