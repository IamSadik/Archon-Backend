import redis
from django.conf import settings
from typing import Optional, Any
import json


class RedisCache:
    """Redis cache wrapper."""
    
    def __init__(self):
        self.client = redis.from_url(settings.REDIS_URL)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        value = self.client.get(key)
        if value:
            return json.loads(value)
        return None
    
    def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache with TTL."""
        self.client.setex(key, ttl, json.dumps(value))
    
    def delete(self, key: str):
        """Delete key from cache."""
        self.client.delete(key)
    
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        return self.client.exists(key)
    
    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern."""
        for key in self.client.scan_iter(pattern):
            self.client.delete(key)


# Global cache instance
cache = RedisCache()
