import json
import random
import time
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from src.connection_manager import ConnectionManager
from src.helpers import print_h_bar
from typing import Dict, Any

REQUIRED_FIELDS = ["name", "bio", "traits", "examples", "loop_delay", "config", "tasks"]

logger = logging.getLogger("agent")

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
        if not self.is_llm_set:
            self._setup_llm_provider()
            self.is_llm_set = True
            
        print(f"DEBUG: In prompt_llm - Prompt: {prompt}")
        print(f"DEBUG: In prompt_llm - System prompt: {system_prompt}")
        
        # Ensure params is a list with at least the prompt
        params = [prompt]
        if system_prompt is not None:
            params.append(system_prompt)
            
        print(f"DEBUG: Final params list: {params}")
        
        return self.connection_manager.perform_action(
            connection_name=self.model_provider,
            action_name="generate-text",
            params=params
        )

    def perform_action(self, connection: str, action: str, **kwargs) -> None:
        return self.connection_manager.perform_action(connection, action, **kwargs)

    def run(self) -> None:
        """Run the agent's main loop"""
        logger.info("\nStarting loop in 5 seconds...")
        for i in range(5, 0, -1):
            logger.info(f"{i}...")
            time.sleep(1)

        while True:
            try:
                # Process timeline
                self._process_timeline()
                
                # Select and perform random action
                action = self._select_action()
                if action == "post-tweet":
                    self._generate_and_post_tweet()
                elif action == "like-tweet":
                    self._like_random_tweet()
                
                # Wait before next iteration
                self._wait_loop_delay()
                
            except Exception as e:
                logger.error(f"\n❌ Error in agent loop iteration: {str(e)}")
                self._wait_loop_delay()
                continue

    def _should_reply_to_tweet(self, tweet: Dict[str, Any]) -> bool:
        """Determine if we should reply to a tweet"""
        # Skip if it's our own tweet
        if tweet.get('author_username', '').lower() == self.username.lower():
            return False
            
        # Only reply if we're mentioned
        mentions = tweet.get('mentions', [])
        return self.username.lower() in [m.lower() for m in mentions]

    def generate_reply(self, tweet: Dict[str, Any]) -> str:
        """Generate a reply to a tweet"""
        if not self._should_reply_to_tweet(tweet):
            return None
            
        base_prompt = (f"Generate a short, chaotic reply to this tweet: {tweet.get('text')}. "
            f"Keep it under 100 characters and make it feel like a quick, unhinged response.")
            
        return self.prompt_llm(base_prompt)

    def _process_timeline(self) -> None:
        """Process the timeline for potential interactions"""
        logger.info("\n👀 READING TIMELINE")
        
        try:
            # Get timeline tweets
            timeline = self.connection_manager.perform_action(
                connection_name="twitter",
                action_name="read-timeline"
            )
            
            # Process each tweet
            for tweet in timeline:
                # Check if we should reply (only if mentioned)
                if self._should_reply_to_tweet(tweet):
                    self._generate_and_post_reply(tweet)
                    
                # Consider liking the tweet
                if random.random() < 0.5:  # 50% chance to like
                    self._like_tweet(tweet)
                    
        except Exception as e:
            logger.error(f"\nError processing timeline: {str(e)}")
            raise
