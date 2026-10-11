import importlib
import os
from unittest import mock

from django.test import TestCase


class SecretKeyTestCase(TestCase):
    def setUp(self) -> None:
        self.settings_module = importlib.import_module("bookmarks.settings.prod")

    def tearDown(self) -> None:
        importlib.reload(self.settings_module)

    def reload_settings(self, env=None, file_content=None):
        env = env or {}
        if file_content is None:
            opener = mock.Mock(side_effect=FileNotFoundError)
        else:
            opener = mock.mock_open(read_data=file_content)
        with mock.patch.dict(os.environ, env):
            if "LD_SECRET_KEY" not in env:
                os.environ.pop("LD_SECRET_KEY", None)
            with mock.patch("builtins.open", opener):
                return importlib.reload(self.settings_module)

    def test_uses_secret_key_from_environment(self):
        module = self.reload_settings(env={"LD_SECRET_KEY": "key-from-env"})

        self.assertEqual(module.SECRET_KEY, "key-from-env")

    def test_environment_takes_precedence_over_file(self):
        module = self.reload_settings(
            env={"LD_SECRET_KEY": "key-from-env"}, file_content="key-from-file"
        )

        self.assertEqual(module.SECRET_KEY, "key-from-env")

    def test_environment_secret_key_is_stable_across_reloads(self):
        first = self.reload_settings(env={"LD_SECRET_KEY": "stable-key"}).SECRET_KEY
        second = self.reload_settings(env={"LD_SECRET_KEY": "stable-key"}).SECRET_KEY

        self.assertEqual(first, second)

    def test_uses_secret_key_from_file_without_environment(self):
        module = self.reload_settings(file_content="key-from-file\n")

        self.assertEqual(module.SECRET_KEY, "key-from-file")

    def test_empty_environment_value_is_ignored(self):
        module = self.reload_settings(
            env={"LD_SECRET_KEY": "  "}, file_content="key-from-file"
        )

        self.assertEqual(module.SECRET_KEY, "key-from-file")

    def test_generates_random_key_without_environment_and_file(self):
        first = self.reload_settings().SECRET_KEY
        second = self.reload_settings().SECRET_KEY

        self.assertTrue(first)
        self.assertNotEqual(first, second)
