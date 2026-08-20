"""Tests des ressources mises en cache sans importer Streamlit ni le modèle."""

from importlib import import_module
from types import ModuleType
import sys
from unittest import TestCase
from unittest.mock import patch


def fake_cache_resource(**_options):
    """Émule le contrat de cache nécessaire à ce test unitaire."""
    def decorate(function):
        values = {}

        def cached(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            if key not in values:
                values[key] = function(*args, **kwargs)
            return values[key]

        cached.clear = values.clear
        return cached

    return decorate


fake_streamlit = ModuleType("streamlit")
fake_streamlit.cache_resource = fake_cache_resource
with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
    model_resource = import_module("app.utils.model_resource")

_load_cached_artifact = model_resource._load_cached_artifact


class TestModelResource(TestCase):
    def setUp(self) -> None:
        _load_cached_artifact.clear()

    def tearDown(self) -> None:
        _load_cached_artifact.clear()

    @patch.object(model_resource, "_load_artifact_uncached")
    def test_same_model_version_is_loaded_once(self, mocked_loader) -> None:
        mocked_loader.return_value = {"model_version": "test"}

        first = _load_cached_artifact("/tmp/expenseai-test.joblib", 100)
        second = _load_cached_artifact("/tmp/expenseai-test.joblib", 100)

        self.assertIs(first, second)
        mocked_loader.assert_called_once_with("/tmp/expenseai-test.joblib")

    @patch.object(model_resource, "_load_artifact_uncached")
    def test_file_timestamp_change_invalidates_model_cache(self, mocked_loader) -> None:
        mocked_loader.side_effect = [
            {"model_version": "test-1"},
            {"model_version": "test-2"},
        ]

        first = _load_cached_artifact("/tmp/expenseai-test.joblib", 100)
        second = _load_cached_artifact("/tmp/expenseai-test.joblib", 101)

        self.assertEqual(first["model_version"], "test-1")
        self.assertEqual(second["model_version"], "test-2")
        self.assertEqual(mocked_loader.call_count, 2)
