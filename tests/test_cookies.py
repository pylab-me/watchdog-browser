import unittest

from src.state import (
    compress_session_storage,
    compress_storage_state,
    decompress_session_storage,
    decompress_storage_state,
    storage_state_to_cookie_header,
    storage_state_to_headers,
)


class CookiesTest(unittest.TestCase):
    def test_storage_state_round_trip(self) -> None:
        storage_state = {
            "cookies": [{"name": "sid", "value": "abc", "domain": ".example.com"}],
            "origins": [{"origin": "https://example.com", "localStorage": [{"name": "k", "value": "v"}]}],
        }
        payload = compress_storage_state(storage_state)
        restored = decompress_storage_state(payload)
        self.assertEqual(restored, storage_state)

    def test_session_storage_round_trip(self) -> None:
        session_storage = {"https://example.com": {"token": "abc"}}
        payload = compress_session_storage(session_storage)
        restored = decompress_session_storage(payload)
        self.assertEqual(restored, session_storage)

    def test_storage_state_to_headers(self) -> None:
        storage_state = {
            "cookies": [
                {"name": "sid", "value": "abc", "domain": ".example.com"},
                {"name": "uid", "value": "42", "domain": ".example.com"},
            ],
            "origins": [],
        }
        payload = compress_storage_state(storage_state)
        self.assertEqual(storage_state_to_cookie_header(payload), "sid=abc; uid=42")
        self.assertEqual(storage_state_to_headers(payload), {"Cookie": "sid=abc; uid=42"})


if __name__ == "__main__":
    unittest.main()
