from typing import Dict, List, Type, Any, Optional
import logging
import asyncio
from src.connections.base import BaseConnection
from src.connections.twitter.connection import TwitterConnection
from src.connections.openai.connection import OpenAIConnection
from src.connections.anthropic.connection import AnthropicConnection
from src.exceptions import ConnectionError

logger = logging.getLogger(__name__)

# Map connection names to their implementations
CONNECTION_TYPES: Dict[str, Type[BaseConnection]] = {
    "twitter": TwitterConnection,
    "openai": OpenAIConnection,
    "anthropic": AnthropicConnection
}

class ConnectionManager:
    def __init__(self, agent_config: List[Dict[str, Any]]):
        self.connections: Dict[str, BaseConnection] = {}
        self._initialize_connections(agent_config)
        self._llm_provider = None
        self._lock = asyncio.Lock()

    def _initialize_connections(self, configs: List[Dict[str, Any]]) -> None:
        """Initialize connection instances"""
        for config in configs:
            try:
                name = config.get("name")
                if not name:
                    raise ValueError("Connection config missing 'name' field")
                    
                connection_type = CONNECTION_TYPES.get(name)
                if not connection_type:
                    raise ValueError(f"Unknown connection type: {name}")
                    
                self.connections[name] = connection_type(config)
                logger.info(f"Initialized {name} connection")
                
            except Exception as e:
                logger.error(f"Failed to initialize {config.get('name', 'unknown')}: {e}")

    async def initialize_all(self) -> bool:
        """Initialize all connections"""
        try:
            results = await asyncio.gather(
                *[conn.initialize() for conn in self.connections.values()],
                return_exceptions=True
            )
            
            success = all(
                isinstance(r, bool) and r 
                for r in results
            )
            
            if success:
                logger.info("All connections initialized successfully")
            else:
                logger.error("Some connections failed to initialize")
                
            return success
            
        except Exception as e:
            logger.error(f"Error initializing connections: {e}")
            return False

    async def shutdown_all(self) -> None:
        """Shutdown all connections gracefully"""
        try:
            await asyncio.gather(
                *[conn.shutdown() for conn in self.connections.values()],
                return_exceptions=True
            )
            logger.info("All connections shut down")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")

    async def health_check_all(self) -> Dict[str, bool]:
        """Check health of all connections"""
        results = {}
        for name, conn in self.connections.items():
            try:
                results[name] = await conn.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                results[name] = False
        return results

    def get_connection(self, name: str) -> BaseConnection:
        """Get a connection by name"""
        if name not in self.connections:
            raise ConnectionError(f"Connection {name} not found")
        return self.connections[name]

    async def get_llm_provider(self) -> Optional[BaseConnection]:
        """Get the current LLM provider with fallback logic"""
        async with self._lock:
            if self._llm_provider and self._llm_provider.state.is_connected:
                return self._llm_provider
                
            # Try Anthropic first, then OpenAI
            for provider in ["anthropic", "openai"]:
                if provider in self.connections:
                    conn = self.connections[provider]
                    if await conn.health_check():
                        self._llm_provider = conn
                        logger.info(f"Using {provider} as LLM provider")
                        return conn
                        
            logger.error("No available LLM provider found")
            return None

    async def perform_action(self, 
                           connection_name: str, 
                           action_name: str, 
                           params: List[Any]) -> Optional[Any]:
        """Perform an action on a specific connection"""
        try:
            connection = self.get_connection(connection_name)
            
            if not connection.state.is_connected:
                logger.error(f"Connection '{connection_name}' is not initialized")
                return None
                
            if action_name not in connection.actions:
                logger.error(f"Unknown action '{action_name}' for {connection_name}")
                return None
                
            action = connection.actions[action_name]
            
            # Validate required parameters
            required_params = [p for p in action.parameters if p.required]
            if len(params) < len(required_params):
                param_names = [p.name for p in required_params]
                logger.error(
                    f"Missing required parameters for {action_name}: {', '.join(param_names)}"
                )
                return None
            
            # Convert params list to kwargs
            kwargs = {}
            for i, param in enumerate(required_params):
                kwargs[param.name] = params[i]
            
            return await connection.perform_action(action_name, kwargs)
            
        except Exception as e:
            logger.error(f"Error performing {action_name} on {connection_name}: {e}")
            return None

    def list_connections(self) -> None:
        """List all available connections and their status"""
        logger.info("\nAvailable Connections:")
        for name, conn in self.connections.items():
            status = "✅ Connected" if conn.state.is_connected else "❌ Not Connected"
            logger.info(f"- {name}: {status}")