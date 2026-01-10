import json
import os
from pathlib import Path
from typing import Optional, Any


class LocalCache:
    """File-based local cache for development."""
    
    def __init__(self, cache_dir: str = ".cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
    
    def _get_path(self, key: str) -> Path:
        """Get file path for key."""
        safe_key = key.replace('/', '_').replace(':', '_')
        return self.cache_dir / f"{safe_key}.json"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        path = self._get_path(key)
        if path.exists():
            with open(path, 'r') as f:
                return json.load(f)
        return None
    
    def set(self, key: str, value: Any, ttl: int = None):
        """Set value in cache (TTL not implemented)."""
        path = self._get_path(key)
        with open(path, 'w') as f:
            json.dump(value, f)
    
    def delete(self, key: str):
        """Delete key from cache."""
        path = self._get_path(key)
        if path.exists():
            path.unlink()
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return self._get_path(key).exists()
    
    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern."""
        for path in self.cache_dir.glob(f"{pattern}*.json"):
            path.unlink()


# Global cache instance
cache = LocalCache()
