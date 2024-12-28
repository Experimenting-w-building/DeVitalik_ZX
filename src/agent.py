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
                "tweet_interval": config.get("tweet_interval", 900),
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
        
        # Changed from weight=1 to weight=0 default
        self.task_weights = [task.get("weight", 0) for task in self.tasks]
        
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
                success = False  # Track if action succeeded
                time.sleep(self.loop_delay if success else 60)  # Different delays for success/failure
        except KeyboardInterrupt:
            logger.info("Agent loop stopped by user")
        except Exception as e:
            logger.error(f"Error in agent loop: {str(e)}")

    def _analyze_tweet_sentiment(self, tweet_text: str) -> str:
        """Analyze if tweet is hostile/neutral/positive"""
        hostile_keywords = ['wrong', 'stupid', 'idiot', 'dumb', 'fake', 'scam']
        if any(word in tweet_text.lower() for word in hostile_keywords):
            return 'hostile'
        return 'neutral'

    def _construct_reply_prompt(self, tweet: dict, is_reply_to_me: bool) -> str:
        tweet_text = tweet.get('text', '')
        sentiment = self._analyze_tweet_sentiment(tweet_text)
        
        if is_reply_to_me:
            if sentiment == 'hostile':
                base_prompt = (
                    f"Someone is criticizing you: '{tweet_text}'. "
                    "Respond with intellectual superiority and condescension. "
                    "Use complex technical or mathematical concepts to subtly imply "
                    "they're out of their depth. Don't use direct insults, but make "
                    "your intellectual dominance clear. Include a subtle dig at their "
                    "understanding. Keep it under 280 characters."
                )
            else:
                base_prompt = (
                    f"Someone replied to you: '{tweet_text}'. "
                    "Respond with strong condescension and intellectual authority. "
                    "Reference technical concepts they might not understand. "
                    "Keep it under 280 characters."
                )
            
            system_prompt = (
                "You are DeVitalik, an intellectually superior and condescending "
                "version of Vitalik Buterin. You believe most people's understanding "
                "of blockchain is pathetically simplistic. When challenged, you respond "
                "with mathematical concepts and subtle intellectual put-downs."
            )
            
            return base_prompt, system_prompt
