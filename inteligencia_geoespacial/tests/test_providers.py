"""Unit tests for provider module."""

import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any

from inteligencia_geoespacial.providers.base import BaseProvider
from inteligencia_geoespacial.providers.exceptions import (
    ProviderException,
    ProviderValidationException,
)


class MockProvider(BaseProvider):
    """Mock provider for testing purposes.

    Implements all abstract methods with simple test data.
    """

    def __init__(self, name: str = "Mock", source_id: str = "mock_source", cache_dir=None, cache_ttl_hours: int = 24):
        """Initialize mock provider."""
        if cache_dir is None:
            cache_dir = Path(tempfile.gettempdir()) / "test_provider_cache"
        super().__init__(name, source_id, cache_dir, cache_ttl_hours)
        self.fetch_called = False
        self.validate_called = False
        self.transform_called = False

    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch mock data."""
        self.fetch_called = True
        return [
            {
                "id": 1,
                "nome": "Test Location 1",
                "valor": 100,
                "lat": -23.550520,
                "lon": -46.633308,
            },
            {
                "id": 2,
                "nome": "Test Location 2",
                "valor": 200,
                "lat": -22.902756,
                "lon": -43.209537,
            },
        ]

    def validate(self, data: List[Dict[str, Any]]) -> bool:
        """Validate mock data."""
        self.validate_called = True
        if not data or not isinstance(data, list):
            raise ProviderValidationException("Data must be a non-empty list")
        for item in data:
            if "id" not in item or "nome" not in item:
                raise ProviderValidationException("Missing required fields: id, nome")
        return True

    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform data to standard schema."""
        self.transform_called = True
        transformed = []
        for item in data:
            transformed.append(
                {
                    "id": str(item["id"]),
                    "codigo_ibge": "",
                    "nome": item["nome"],
                    "regiao": "SE",
                    "uf": "SP",
                    "geometria": None,
                    "coordenadas": (item.get("lon", 0), item.get("lat", 0)),
                    "metadados": {"valor": item.get("valor", 0)},
                    "source": self.source_id,
                }
            )
        return transformed

    def to_geojson(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert to GeoJSON FeatureCollection."""
        features = []
        for item in data:
            feature = {
                "type": "Feature",
                "properties": {
                    "id": item["id"],
                    "nome": item["nome"],
                    "regiao": item["regiao"],
                    "uf": item["uf"],
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": item["coordenadas"],
                } if item.get("geometria") is None else item["geometria"],
            }
            features.append(feature)
        return {
            "type": "FeatureCollection",
            "features": features,
        }


class TestMockProvider:
    """Test MockProvider implementation."""

    def test_mock_provider_fetch(self):
        """Test that MockProvider.fetch() returns expected data."""
        provider = MockProvider()
        data = provider.fetch()
        assert len(data) == 2
        assert data[0]["id"] == 1
        assert data[0]["nome"] == "Test Location 1"
        assert provider.fetch_called is True

    def test_mock_provider_validate_success(self):
        """Test that MockProvider.validate() accepts valid data."""
        provider = MockProvider()
        data = provider.fetch()
        result = provider.validate(data)
        assert result is True
        assert provider.validate_called is True

    def test_mock_provider_validate_empty_list(self):
        """Test that MockProvider.validate() rejects empty list."""
        provider = MockProvider()
        with pytest.raises(ProviderValidationException):
            provider.validate([])

    def test_mock_provider_validate_missing_fields(self):
        """Test that MockProvider.validate() rejects data with missing fields."""
        provider = MockProvider()
        invalid_data = [{"id": 1}]  # Missing 'nome'
        with pytest.raises(ProviderValidationException):
            provider.validate(invalid_data)

    def test_mock_provider_transform(self):
        """Test that MockProvider.transform() converts to standard schema."""
        provider = MockProvider()
        raw_data = provider.fetch()
        transformed = provider.transform(raw_data)

        assert len(transformed) == 2
        assert transformed[0]["id"] == "1"
        assert transformed[0]["nome"] == "Test Location 1"
        assert transformed[0]["uf"] == "SP"
        assert transformed[0]["regiao"] == "SE"
        assert transformed[0]["source"] == "mock_source"
        assert transformed[0]["coordenadas"] == (-46.633308, -23.550520)

    def test_mock_provider_to_geojson(self):
        """Test that MockProvider.to_geojson() produces valid GeoJSON."""
        provider = MockProvider()
        raw_data = provider.fetch()
        transformed = provider.transform(raw_data)
        geojson = provider.to_geojson(transformed)

        assert geojson["type"] == "FeatureCollection"
        assert len(geojson["features"]) == 2
        assert geojson["features"][0]["type"] == "Feature"
        assert geojson["features"][0]["geometry"]["type"] == "Point"
        assert geojson["features"][0]["geometry"]["coordinates"] == (-46.633308, -23.550520)


class TestProviderCaching:
    """Test caching functionality."""

    def test_cache_write(self, tmp_path):
        """Test that fetch_with_cache() writes cache file."""
        provider = MockProvider(cache_dir=tmp_path)
        data = provider.fetch_with_cache(use_cache=False)

        assert len(data) == 2
        assert provider.fetch_count == 1

        # Check that cache file was created
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) > 0

    def test_cache_read(self, tmp_path):
        """Test that fetch_with_cache() reads from cache on second call."""
        provider = MockProvider(cache_dir=tmp_path)

        # First fetch: should fetch fresh data
        data1 = provider.fetch_with_cache(use_cache=True)
        assert provider.fetch_count == 1
        fetch_count_after_first = provider.fetch_count

        # Reset fetch_called flag
        provider.fetch_called = False

        # Second fetch with same params: should read from cache
        data2 = provider.fetch_with_cache(use_cache=True)
        assert provider.fetch_count == fetch_count_after_first  # Should not increment
        assert provider.fetch_called is False  # fetch() should not be called

        # Data should be identical
        assert data1 == data2

    def test_cache_disabled(self, tmp_path):
        """Test that fetch_with_cache(use_cache=False) skips cache."""
        provider = MockProvider(cache_dir=tmp_path)

        # First fetch
        data1 = provider.fetch_with_cache(use_cache=False)
        assert provider.fetch_count == 1

        # Second fetch with use_cache=False should fetch again
        data2 = provider.fetch_with_cache(use_cache=False)
        assert provider.fetch_count == 2

        assert data1 == data2

    def test_cache_expiry(self, tmp_path):
        """Test that expired cache is ignored."""
        # Use very short TTL (1 second)
        provider = MockProvider(cache_dir=tmp_path, cache_ttl_hours=0.0001)  # ~0.36 seconds

        # First fetch: write cache
        data1 = provider.fetch_with_cache(use_cache=True)
        assert provider.fetch_count == 1

        # Modify the cache file's modification time to make it old
        cache_files = list(tmp_path.glob("*.json"))
        assert len(cache_files) > 0
        cache_file = cache_files[0]

        # Set modification time to 2 seconds ago
        import time
        old_time = time.time() - 2
        import os
        os.utime(cache_file, (old_time, old_time))

        # Reset fetch_called
        provider.fetch_called = False

        # Second fetch: cache should be expired, should fetch fresh
        data2 = provider.fetch_with_cache(use_cache=True)
        assert provider.fetch_count == 2  # fetch_count should increment
        assert provider.fetch_called is True  # fetch() should be called

        assert data1 == data2


class TestProviderValidation:
    """Test validation pipeline."""

    def test_valid_data_passes(self):
        """Test that valid data passes validation in fetch_with_cache()."""
        provider = MockProvider()
        # This should not raise an exception
        data = provider.fetch_with_cache(use_cache=False)
        assert len(data) == 2

    def test_invalid_data_raises_exception(self):
        """Test that invalid data raises ProviderValidationException."""
        class BadProvider(MockProvider):
            def fetch(self, **kwargs):
                # Return data with missing required fields
                return [{"id": 1}]  # Missing 'nome'

        provider = BadProvider()
        with pytest.raises(ProviderValidationException):
            provider.fetch_with_cache(use_cache=False)

    def test_validation_called_in_pipeline(self):
        """Test that validate() is called in fetch_with_cache() pipeline."""
        provider = MockProvider()
        provider.validate_called = False
        data = provider.fetch_with_cache(use_cache=False)
        assert provider.validate_called is True

    def test_transform_called_in_pipeline(self):
        """Test that transform() is called in fetch_with_cache() pipeline."""
        provider = MockProvider()
        provider.transform_called = False
        data = provider.fetch_with_cache(use_cache=False)
        assert provider.transform_called is True


class TestProviderMetadata:
    """Test metadata functionality."""

    def test_get_metadata_empty_provider(self):
        """Test get_metadata() on fresh provider."""
        provider = MockProvider()
        metadata = provider.get_metadata()

        assert metadata["name"] == "Mock"
        assert metadata["source_id"] == "mock_source"
        assert metadata["last_fetch_time"] is None
        assert metadata["last_error"] is None
        assert metadata["fetch_count"] == 0
        assert metadata["cache_ttl_hours"] == 24

    def test_get_metadata_after_fetch(self, tmp_path):
        """Test get_metadata() after fetch_with_cache()."""
        provider = MockProvider(cache_dir=tmp_path)
        provider.fetch_with_cache(use_cache=False)
        metadata = provider.get_metadata()

        assert metadata["fetch_count"] == 1
        assert metadata["last_fetch_time"] is not None
        assert metadata["last_error"] is None

    def test_hash_query_deterministic(self):
        """Test that _hash_query() produces deterministic hashes."""
        provider = MockProvider()

        hash1 = provider._hash_query(param1="value1", param2="value2")
        hash2 = provider._hash_query(param1="value1", param2="value2")
        hash3 = provider._hash_query(param2="value2", param1="value1")

        # Same params should produce same hash
        assert hash1 == hash2
        # Order of params should not matter (dict is sorted)
        assert hash1 == hash3

    def test_hash_query_different(self):
        """Test that _hash_query() produces different hashes for different params."""
        provider = MockProvider()

        hash1 = provider._hash_query(param1="value1")
        hash2 = provider._hash_query(param1="value2")

        assert hash1 != hash2


class TestProviderExceptions:
    """Test exception hierarchy."""

    def test_provider_exception_is_exception(self):
        """Test that ProviderException is an Exception."""
        exc = ProviderException("test")
        assert isinstance(exc, Exception)

    def test_provider_timeout_is_provider_exception(self):
        """Test that ProviderTimeoutException inherits from ProviderException."""
        from inteligencia_geoespacial.providers.exceptions import ProviderTimeoutException
        exc = ProviderTimeoutException("test")
        assert isinstance(exc, ProviderException)
        assert isinstance(exc, Exception)

    def test_provider_validation_is_provider_exception(self):
        """Test that ProviderValidationException inherits from ProviderException."""
        exc = ProviderValidationException("test")
        assert isinstance(exc, ProviderException)
        assert isinstance(exc, Exception)
