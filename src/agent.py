import json
import random
import time
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from src.connection_manager import ConnectionManager
from src.helpers import print_h_bar
import tweepy
from src.services.twitter_service import TwitterService

REQUIRED_FIELDS = ["name", "bio", "traits", "examples", "loop_delay", "config", "tasks"]

logger = logging.getLogger("agent")

load_dotenv()  # Load environment variables

class ZerePyAgent:
    def __init__(
            self,
            agent_name: str
    ):
        try:        
            agent_path = Path("agents") / f"{agent_name}.json"
            agent_dict = json.load(open(agent_path, "r"))

            missing_fields = [field for field in REQUIRED_FIELDS if field not in agent_dict]
            if missing_fields:
                raise KeyError(f"Missing required fields: {', '.join(missing_fields)}")

            self.name = agent_dict["name"]
            self.bio = agent_dict["bio"]
            self.traits = agent_dict["traits"]
            self.examples = agent_dict["examples"]
            self.loop_delay = agent_dict["loop_delay"] 
            self.connection_manager = ConnectionManager(agent_dict["config"])
            
            # Extract Twitter config
            twitter_config = next((config for config in agent_dict["config"] if config["name"] == "twitter"), None)
            if not twitter_config:
                raise KeyError("Twitter configuration is required")

            # TODO: These should probably live in the related task parameters
            self.tweet_interval = twitter_config.get("tweet_interval", 900)
            self.own_tweet_replies_count = twitter_config.get("own_tweet_replies_count", 2)

            self.is_llm_set = False
            
            # Cache for system prompt
            self._system_prompt = None

            # Extract loop tasks
            self.tasks = agent_dict.get("tasks", [])
            self.task_weights = [task.get("weight", 0) for task in self.tasks]

            # Set up empty agent state
            self.state = {}
            
        except Exception as e:
            logger.error("Could not load ZerePy agent")
            raise e
        
    def _setup_llm_provider(self):           
        # Get first available LLM provider and its model
        llm_providers = self.connection_manager.get_model_providers()
        if not llm_providers:
            raise ValueError("No configured LLM provider found")
        self.model_provider = llm_providers[0]
        
        # Load Twitter username for self-reply detection
        load_dotenv()
        self.username = os.getenv('TWITTER_USERNAME', '').lower()
        if not self.username:
                raise ValueError("Twitter username is required")

    def _construct_system_prompt(self) -> str:
        """Construct the system prompt from agent configuration"""
        if self._system_prompt is None:
            prompt_parts = []
            prompt_parts.extend(self.bio)

            if self.traits:
                prompt_parts.append("\nYour key traits are:")
                prompt_parts.extend(f"- {trait}" for trait in self.traits)

            if self.examples:
                prompt_parts.append("\nHere are some examples of your style (Please avoid repeating any of these):")
                prompt_parts.extend(f"- {example}" for example in self.examples)

            self._system_prompt = "\n".join(prompt_parts)

        return self._system_prompt

    def prompt_llm(self, prompt: str, system_prompt: str = None) -> str:
        """Generate text using the configured LLM provider"""
        system_prompt = system_prompt or self._construct_system_prompt()
        
        return self.connection_manager.perform_action(
            connection_name=self.model_provider,
            action_name="generate-text",
            params=[prompt, system_prompt]
        )
    
    def perform_action(self, connection: str, action: str, **kwargs) -> None:
        return self.connection_manager.perform_action(connection, action, **kwargs)

    async def run_loop(self):
        try:
            if not await self.twitter_service.check_credentials():
                # Attempt to reconnect
                auth = tweepy.OAuthHandler(os.getenv('TWITTER_API_KEY'), os.getenv('TWITTER_API_SECRET'))
                auth.set_access_token(os.getenv('TWITTER_ACCESS_TOKEN'), os.getenv('TWITTER_ACCESS_TOKEN_SECRET'))
                self.api_client = tweepy.API(auth)
                self.twitter_service = TwitterService(self.api_client)
        except Exception as e:
            logger.error(f"Error in run_loop: {e}")
