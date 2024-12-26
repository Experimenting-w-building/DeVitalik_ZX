import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Optional
from src.connections import ConnectionManager

logger = logging.getLogger(__name__)

class ZerePyAgent:
    def __init__(self, agent_config):
        """Initialize the agent with a configuration"""
        if isinstance(agent_config, str):
            # If agent_config is a string, treat it as a filename
            with open(f"agents/{agent_config}.json", 'r') as f:
                config = json.load(f)
                
            # Extract connections from config
            connections = []
            for conn in config.get("config", []):
                connections.append({
                    "type": conn["name"],
                    "config": conn
                })
                
            # Build agent config
            self.config = {
                "name": config["name"],
                "username": "DeVitalik",
                "loop_delay": config.get("loop_delay", 300),
                "tweet_interval": 3600,
                "connections": connections,
                "model_provider": "openai"
            }
        else:
            # If agent_config is a dict, use it directly
            self.config = agent_config
            
        # Initialize components
        self.name = self.config["name"]
        self.username = self.config["username"]
        self.loop_delay = self.config["loop_delay"]
        self.is_llm_set = False
        
        # Setup connection manager
        self.connection_manager = ConnectionManager(self.config)
        
    def _setup_llm_provider(self):
        """Setup the LLM provider if not already done"""
        if not self.is_llm_set:
            self.llm = self.connection_manager.get_connection(self.config["model_provider"])
            self.is_llm_set = True
            
    def prompt_llm(self, prompt: str) -> str:
        """Send a prompt to the LLM and get response"""
        if not self.is_llm_set:
            self._setup_llm_provider()
        return self.llm.chat(prompt)
        
    def perform_action(self, connection: str, action: str, params: List[str] = None) -> str:
        """Perform a single action with a connection"""
        conn = self.connection_manager.get_connection(connection)
        if not conn:
            return f"Connection {connection} not found"
            
        if not hasattr(conn, action):
            return f"Action {action} not found for connection {connection}"
            
        try:
            if params:
                result = getattr(conn, action)(*params)
            else:
                result = getattr(conn, action)()
            return result
        except Exception as e:
            return f"Error performing action: {str(e)}"
            
    def loop(self):
        """Main agent loop"""
        logger.info(f"Starting agent loop for {self.name}")
        try:
            while True:
                # Perform actions here
                time.sleep(self.loop_delay)
        except KeyboardInterrupt:
            logger.info("Agent loop stopped by user")
        except Exception as e:
            logger.error(f"Error in agent loop: {str(e)}")
