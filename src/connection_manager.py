import logging
from typing import Any, List, Optional, Type, Dict
from src.connections.base_connection import BaseConnection
from src.connections.anthropic_connection import AnthropicConnection
from src.connections.eternalai_connection import EternalAIConnection
from src.connections.openai_connection import OpenAIConnection
from src.connections.twitter_connection import TwitterConnection

logger = logging.getLogger("connection_manager")

class ConnectionManager:
    def __init__(self, agent_config):
        self.connections : Dict[str, BaseConnection] = {}
        for config in agent_config:
            self._register_connection(config)
    
    @staticmethod
    def _class_name_to_type(class_name: str) -> Type[BaseConnection]:
        if class_name == "twitter":
            return TwitterConnection
        elif class_name == "anthropic":
            return AnthropicConnection
        elif class_name == "openai":
            return OpenAIConnection
        elif class_name == "eternalai":
            return EternalAIConnection

        return None
    
    def _register_connection(self, config_dic: Dict[str, Any]) -> None:
        """
        Create and register a new connection with configuration
        
        Args:
            name: Identifier for the connection
            connection_class: The connection class to instantiate
            config: Configuration dictionary for the connection
        """
        try:
            name = config_dic["name"]
            connection_class = self._class_name_to_type(name)
            connection = connection_class(config_dic)
            self.connections[name] = connection
        except Exception as e:
            logging.error(f"Failed to initialize connection {name}: {e}")

    def _check_connection(self, connection_string: str)-> bool:
        try:
            connection = self.connections[connection_string]
            return connection.is_configured(verbose=True)
        except KeyError:
            logging.error("\nUnknown connection. Try 'list-connections' to see all supported connections.")
            return False
        except Exception as e:
            logging.error(f"\nAn error occurred: {e}")
            return False

    def configure_connection(self, connection_name: str) -> bool:
        """Configure a specific connection"""
        try:
            connection = self.connections[connection_name]
            success = connection.configure()
            
            if success:
                logging.info(f"\n✅ SUCCESSFULLY CONFIGURED CONNECTION: {connection_name}")
            else:
                logging.error(f"\n❌ ERROR CONFIGURING CONNECTION: {connection_name}")
            return success
            
        except KeyError:
            logging.error("\nUnknown connection. Try 'list-connections' to see all supported connections.")
            return False
        except Exception as e:
            logging.error(f"\nAn error occurred: {e}")
            return False

    def list_connections(self) -> None:
        """List all available connections and their status"""
        logging.info("\nAVAILABLE CONNECTIONS:")
        for name, connection in self.connections.items():
            status = "✅ Configured" if connection.is_configured() else "❌ Not Configured"
            logging.info(f"- {name}: {status}")

    def list_actions(self, connection_name: str) -> None:
        """List all available actions for a specific connection"""
        try:
            connection = self.connections[connection_name]
            
            if connection.is_configured():
                logging.info(f"\n✅ {connection_name} is configured. You can use any of its actions.")
            else:
                logging.info(f"\n❌ {connection_name} is not configured. You must configure a connection to use its actions.")
            
            logging.info("\nAVAILABLE ACTIONS:")
            for action_name, action in connection.actions.items():
                logging.info(f"- {action_name}: {action.description}")
                logging.info("  Parameters:")
                for param in action.parameters:
                    req = "required" if param.required else "optional"
                    logging.info(f"    - {param.name} ({req}): {param.description}")
                
        except KeyError:
            logging.error("\nUnknown connection. Try 'list-connections' to see all supported connections.")
        except Exception as e:
            logging.error(f"\nAn error occurred: {e}")

    def perform_action(self, connection_name: str, action_name: str, params: List[Any] = None) -> Any:
        """Perform an action using the specified connection"""
        if connection_name not in self.connections:
            raise ValueError(f"Unknown connection: {connection_name}")
            
        print(f"DEBUG Connection Manager: Performing {action_name} for {connection_name}")
        print(f"DEBUG Connection Manager: Params type: {type(params)}")
        print(f"DEBUG Connection Manager: Params content: {params}")
        
        try:
            connection = self.connections[connection_name]
            return connection.perform_action(action_name, params)
        except Exception as e:
            logger.error(f"An error occurred while trying action {action_name} for {connection_name} connection: {str(e)}")
            raise

    def get_model_providers(self) -> List[str]:
        """Get a list of all LLM provider connections"""
        return [
            name for name, conn in self.connections.items() 
            if conn.is_configured() and getattr(conn, 'is_llm_provider', lambda: False)
        ]