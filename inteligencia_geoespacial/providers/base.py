"""Base provider abstract class and caching layer."""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

from .exceptions import ProviderException, ProviderTimeoutException, ProviderValidationException


class BaseProvider(ABC):
    """Abstract base class for all data providers."""

    def __init__(self, name: str, source_id: str, cache_dir: Optional[Path] = None, cache_ttl_hours: int = 24):
        """Initialize provider with caching configuration.

        Args:
            name: Display name of the provider
            source_id: Unique identifier for the data source
            cache_dir: Directory for cache files (default: inteligencia_geoespacial/caches)
            cache_ttl_hours: Cache time-to-live in hours (default: 24)
        """
        self.name = name
        self.source_id = source_id
        self.cache_dir = cache_dir or Path("inteligencia_geoespacial/caches")
        self.cache_ttl = timedelta(hours=cache_ttl_hours)
        self.last_fetch_time: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self.fetch_count = 0

    @abstractmethod
    def fetch(self, **kwargs) -> List[Dict[str, Any]]:
        """Fetch raw data from provider.

        Must be implemented by subclasses.

        Args:
            **kwargs: Provider-specific query parameters

        Returns:
            List of raw data dictionaries from provider
        """
        pass

    @abstractmethod
    def validate(self, data: List[Dict[str, Any]]) -> bool:
        """Validate data structure and content.

        Must be implemented by subclasses.

        Args:
            data: Raw data from fetch()

        Returns:
            True if data is valid

        Raises:
            ProviderValidationException: If validation fails
        """
        pass

    @abstractmethod
    def transform(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Transform raw data to standard schema.

        Must be implemented by subclasses.

        Standard schema fields:
            - id: str, unique identifier
            - codigo_ibge: str, IBGE code if applicable
            - nome: str, canonical name
            - regiao: str, region name
            - uf: str, UF code (2-letter)
            - geometria: Dict, GeoJSON geometry (optional)
            - coordenadas: Tuple[float, float], (lon, lat) in EPSG:4326
            - metadados: Dict, source-specific metadata
            - source: str, source provider ID

        Args:
            data: Validated raw data

        Returns:
            List of transformed data dictionaries matching standard schema
        """
        pass

    @abstractmethod
    def to_geojson(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert data to GeoJSON FeatureCollection.

        Must be implemented by subclasses.

        Args:
            data: Transformed data from transform()

        Returns:
            GeoJSON FeatureCollection dictionary
        """
        pass

    def fetch_with_cache(self, use_cache: bool = True, **kwargs) -> List[Dict[str, Any]]:
        """Orchestrate fetch → validate → transform → cache pipeline.

        This is the main entry point for getting data from a provider.
        Handles caching automatically.

        Args:
            use_cache: Whether to use cached data if available (default: True)
            **kwargs: Query parameters to pass to fetch()

        Returns:
            Transformed data list (from cache or fresh fetch)

        Raises:
            ProviderValidationException: If validation fails
            ProviderException: If other errors occur
        """
        try:
            query_hash = self._hash_query(**kwargs)

            # Try to load from cache if enabled
            if use_cache:
                cached_data = self._load_cache(query_hash)
                if cached_data is not None:
                    return cached_data

            # Fetch fresh data
            raw_data = self.fetch(**kwargs)

            # Validate
            self.validate(raw_data)

            # Transform
            transformed_data = self.transform(raw_data)

            # Save to cache
            self._save_cache(query_hash, transformed_data)

            # Update stats
            self.last_fetch_time = datetime.now()
            self.fetch_count += 1

            return transformed_data
        except ProviderException:
            # Re-raise provider exceptions as-is
            raise
        except Exception as e:
            self.last_error = str(e)
            raise ProviderException(f"Error in fetch_with_cache: {str(e)}") from e

    def _load_cache(self, query_hash: str) -> Optional[List[Dict[str, Any]]]:
        """Load cached data from disk if it's still fresh.

        Args:
            query_hash: MD5 hash of query parameters

        Returns:
            Cached data if file exists and is fresh, None otherwise
        """
        cache_file = self.cache_dir / f"{self.source_id}_{query_hash}.json"

        if not cache_file.exists():
            return None

        # Check if cache is still fresh (within TTL)
        try:
            file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            if datetime.now() - file_mtime > self.cache_ttl:
                return None

            # Load and return cached data
            with open(cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.last_error = str(e)
            return None

    def _save_cache(self, query_hash: str, data: List[Dict[str, Any]]) -> None:
        """Save transformed data to cache file.

        Args:
            query_hash: MD5 hash of query parameters
            data: Transformed data to cache
        """
        try:
            # Ensure cache directory exists
            self.cache_dir.mkdir(parents=True, exist_ok=True)

            cache_file = self.cache_dir / f"{self.source_id}_{query_hash}.json"

            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.last_error = str(e)

    def _hash_query(self, **kwargs) -> str:
        """Generate deterministic MD5 hash of query parameters.

        Args:
            **kwargs: Query parameters

        Returns:
            Hexadecimal MD5 hash string
        """
        query_str = json.dumps(kwargs, sort_keys=True, default=str)
        return hashlib.md5(query_str.encode()).hexdigest()

    def get_metadata(self) -> Dict[str, Any]:
        """Return provider metadata dictionary.

        Returns:
            Dictionary with provider metadata and statistics
        """
        return {
            "name": self.name,
            "source_id": self.source_id,
            "last_fetch_time": self.last_fetch_time.isoformat() if self.last_fetch_time else None,
            "last_error": self.last_error,
            "fetch_count": self.fetch_count,
            "cache_ttl_hours": int(self.cache_ttl.total_seconds() // 3600),
        }
