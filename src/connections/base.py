from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging
import asyncio

logger = logging.getLogger(__name__)

@dataclass
class ConnectionState:
    """Connection state model"""
    is_connected: bool = False
    last_connected: Optional[datetime] = None
    last_error: Optional[str] = None

@dataclass
class ConnectionConfig:
    """Base connection configuration"""
    pass

class BaseConnection:
    """Base class for all connections"""
    def __init__(self, config: Dict[str, Any]):
        self.config = self.validate_config(config)
        self.state = ConnectionState()
        
    def validate_config(self, config: Dict[str, Any]) -> ConnectionConfig:
        """Validate and return connection configuration"""
        return ConnectionConfig()
        
    async def initialize(self) -> bool:
        """Initialize the connection"""
        raise NotImplementedError
        
    async def shutdown(self) -> None:
        """Clean shutdown of the connection"""
        raise NotImplementedError
        
    async def health_check(self) -> bool:
        """Check if connection is healthy"""
        raise NotImplementedError
        
    async def _execute_with_retry(self, operation: str, func, *args, **kwargs):
        """Execute operation with retry logic"""
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Failed {operation} after {max_retries} attempts: {e}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                await asyncio.sleep(retry_delay * (attempt + 1)) 