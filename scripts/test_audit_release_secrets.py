from __future__ import annotations

import unittest

import audit_release_secrets as audit


class ReleaseSecretAuditTests(unittest.TestCase):
    def assert_clean(self, value: str, encoding: str = "utf-8") -> None:
        self.assertEqual(audit.inspect_chunk(value.encode(encoding)), set())

    def assert_finds(self, value: str, rule: str, encoding: str = "utf-8") -> None:
        self.assertIn(rule, audit.inspect_chunk(value.encode(encoding)))

    def test_placeholder_profile_paths_are_allowed(self) -> None:
        for value in (
            r"C:\Users\username\project\example.c",
            r"C:\Users\user\project\example.c",
            r"C:\Users\<username>\project\example.c",
            r"C:\Users\MyUser\project\example.c",
            r"C:\Users\All Users\AppData\example.ini",
            "/home/user/project/example.c",
            "/home/distutils/project/example.c",
            "/Users/trentm/project/example.c",
            "/Users/example/project/example.c",
        ):
            with self.subTest(value=value):
                self.assert_clean(value)

    def test_non_placeholder_profile_paths_are_blocked(self) -> None:
        self.assert_finds(
            "D:\\" + r"Users\actual-builder\project\example.c",
            "Windows user-profile path",
        )
        self.assert_finds(
            "/" + "home/actual-builder/project/example.c",
            "Unix user-profile path",
        )

    def test_real_identity_is_blocked_in_utf8_and_utf16(self) -> None:
        workspace = str(audit.REPOSITORY_ROOT)
        for encoding in ("utf-8", "utf-16le"):
            with self.subTest(encoding=encoding):
                self.assert_finds(workspace, "current workspace path", encoding)

    def test_example_host_and_codex_placeholder_are_allowed(self) -> None:
        self.assert_clean("DESKTOP-EXAMPLE")
        self.assert_clean(r"%USERPROFILE%\.codex\config.toml")

    def test_spdx_identifier_is_not_an_api_key(self) -> None:
        self.assert_clean("sk-linking-protocols-exception")

    def test_url_path_segment_is_not_a_user_profile(self) -> None:
        self.assert_clean("https://downloads.example/uploads/Home/Dingoo/file.zip")

    def test_api_tokens_are_blocked_in_utf8_and_utf16(self) -> None:
        samples = {
            "OpenAI-style API key": "s" + "k-proj-A1b2C3d4E5f6G7h8J9k0LmNoPqRsTuVw",
            "GitHub token": "g" + "hp_A1b2C3d4E5f6G7h8J9k0LmNoPqRsTuVwXyZ0",
            "Bearer token": "Bear" + "er A1b2C3d4E5f6G7h8J9k0LmNoPqRsTuVw",
        }
        for rule, value in samples.items():
            for encoding in ("utf-8", "utf-16le"):
                with self.subTest(rule=rule, encoding=encoding):
                    self.assert_finds(value, rule, encoding)


if __name__ == "__main__":
    unittest.main()
