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
    def __init__(self, config: Dict[str, Any]):
        """Initialize the agent with the given configuration"""
        self.name = config.get("name", "unnamed")
        self.username = config.get("username", "")  # Add username
        self.model_provider = config.get("model_provider", "openai")
        self.loop_delay = config.get("loop_delay", 180)  # Add loop_delay
        self.tweet_interval = config.get("tweet_interval", 3600)
        
        self.connection_manager = ConnectionManager()
        self.is_llm_set = False
        
        # Load connections from config
        connections = config.get("connections", [])
        for conn_config in connections:
            self.connection_manager.add_connection(conn_config)

    def _wait_loop_delay(self) -> None:
        """Wait for the configured loop delay"""
        logger.info(f"\n⏳ Waiting {self.loop_delay} seconds before next loop...")
        time.sleep(self.loop_delay)

    def _process_timeline(self) -> None:
        """Process the timeline for potential interactions"""
        logger.info("\n👀 READING TIMELINE")
        
        try:
            # Get timeline tweets
            timeline = self.connection_manager.perform_action(
                connection_name="twitter",
                action_name="read-timeline",
                params=[]  # Ensure we always pass params as list
            )
            
            if not timeline:
                return
                
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

    def _should_reply_to_tweet(self, tweet: Dict[str, Any]) -> bool:
        """Determine if we should reply to a tweet"""
        # Skip if it's our own tweet
        if str(tweet.get('author_id')) == str(self.connection_manager.get_user_id()):
            return False
            
        # Only reply if we're mentioned
        mentions = tweet.get('mentions', [])
        return self.username.lower() in [m.lower() for m in mentions]

    def _like_tweet(self, tweet: Dict[str, Any]) -> None:
        """Like a specific tweet"""
        tweet_id = tweet.get('id')
        if not tweet_id:
            return
            
        try:
            logger.info(f"\n👍 LIKING TWEET: {tweet.get('text', '')[:50]}...")
            self.connection_manager.perform_action(
                connection_name="twitter",
                action_name="like-tweet",
                params=[tweet_id]
            )
            logger.info("✅ Tweet liked successfully!")
        except Exception as e:
            logger.error(f"\nError liking tweet: {str(e)}")
