from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import logging
import asyncio
from src.connections.twitter.connection import TwitterConnection
from src.connections.openai.connection import OpenAIConnection
from src.connections.anthropic.connection import AnthropicConnection
from src.connections.base import BaseConnection

logger = logging.getLogger(__name__)

@dataclass
class ConnectionManager:
    """Manage all service connections"""
    connections: Dict[str, BaseConnection] = field(default_factory=dict)
    
    def __init__(self, configs: List[Dict[str, Any]]):
        self.connections = {}
        for config in configs:
            connection_type = config.get("type", "").lower()
            if connection_type == "twitter":
                self.connections["twitter"] = TwitterConnection(config)
            elif connection_type == "openai":
                self.connections["openai"] = OpenAIConnection(config)
            elif connection_type == "anthropic":
                self.connections["anthropic"] = AnthropicConnection(config)
            else:
                logger.warning(f"Unknown connection type: {connection_type}")
    
    def get_connection(self, name: str) -> Optional[BaseConnection]:
        """Get a connection by name"""
        return self.connections.get(name)
    
    async def initialize_all(self) -> bool:
        """Initialize all connections"""
        success = True
        for name, connection in self.connections.items():
            try:
                if not await connection.initialize():
                    logger.error(f"Failed to initialize {name} connection")
                    success = False
            except Exception as e:
                logger.error(f"Error initializing {name} connection: {e}")
                success = False
        return success
    
    async def shutdown_all(self) -> None:
        """Shutdown all connections"""
        for name, connection in self.connections.items():
            try:
                await connection.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down {name} connection: {e}")
    
    async def get_llm_provider(self) -> Optional[BaseConnection]:
        """Get the first available LLM provider"""
        providers = ["openai", "anthropic"]
        for provider in providers:
            connection = self.get_connection(provider)
            if connection and connection.state.is_connected:
                return connection
        return None