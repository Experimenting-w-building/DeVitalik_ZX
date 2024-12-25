from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class ConnectionConfig(BaseModel):
    """Base configuration for all connections"""
    name: str
    enabled: bool = True
    retry_attempts: int = 3
    retry_delay: float = 1.0

class ConnectionState(BaseModel):
    """Track connection state"""
    is_connected: bool = False
    last_connected: Optional[datetime] = None
    error_count: int = 0
    last_error: Optional[str] = None

class BaseConnection(ABC):
    """Abstract base class for all connections"""
    def __init__(self, config: Dict[str, Any]):
        self.config = self.validate_config(config)
        self.state = ConnectionState()
        self._lock = asyncio.Lock()
        
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> ConnectionConfig:
        """Validate and return typed config"""
        pass

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the connection"""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """Clean shutdown of connection"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if connection is healthy"""
        pass

    async def __aenter__(self):
        """Async context manager support"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure clean shutdown"""
        await self.shutdown()

    async def _execute_with_retry(self, operation: str, func, *args, **kwargs) -> Any:
        """Execute with retry logic"""
        for attempt in range(self.config.retry_attempts):
            try:
                async with self._lock:  # Ensure thread safety
                    result = await func(*args, **kwargs)
                    self.state.error_count = 0
                    return result
            except Exception as e:
                self.state.error_count += 1
                self.state.last_error = str(e)
                logger.error(f"{operation} failed (attempt {attempt + 1}/{self.config.retry_attempts}): {e}")
                if attempt < self.config.retry_attempts - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                else:
                    raise 