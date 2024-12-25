import json
import random
import time
import logging
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from src.connection_manager import ConnectionManager
from src.helpers import print_h_bar
import tweepy
from src.services.twitter_service import TwitterService
from openai import OpenAI
from src.services.tweet_generator import TweetGenerator
from src.services.visualization_service import VisualizationService
import asyncio

REQUIRED_FIELDS = ["name", "bio", "traits", "examples", "loop_delay", "config", "tasks"]

logger = logging.getLogger("agent")

load_dotenv()  # Load environment variables

try:
    from src.services.context_analyzer import ContextAnalyzer
    from src.exceptions import ServiceError, AgentConfigError
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    raise

class AgentConfig(BaseModel):
    """Agent configuration model"""
    name: str
    bio: List[str]
    traits: List[str]
    examples: List[str]
    loop_delay: int
    config: List[Dict[str, Any]]
    tasks: List[Dict[str, Any]]

class ZerePyAgent:
    def __init__(self, agent_name: str):
        try:
            # Load and validate agent configuration
            agent_path = Path("agents") / f"{agent_name}.json"
            agent_dict = json.load(open(agent_path, "r"))
            self.config = AgentConfig(**agent_dict)
            
            # Initialize core components
            self.name = self.config.name
            self.connection_manager = ConnectionManager(self.config.config)
            self.tasks = self.config.tasks
            self.task_weights = [task.get("weight", 0) for task in self.tasks]
            
            # Initialize state
            self.state: Dict[str, Any] = {}
            self._system_prompt = None
            self.is_running = False
            
        except Exception as e:
            logger.error(f"Failed to initialize agent: {e}")
            raise

    async def initialize(self) -> bool:
        """Initialize agent and all connections"""
        try:
            # Initialize all connections
            if not await self.connection_manager.initialize_all():
                return False

            # Get LLM provider
            llm_provider = await self.connection_manager.get_llm_provider()
            if not llm_provider:
                logger.error("No LLM provider available")
                return False

            logger.info(f"Agent {self.name} initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Agent initialization failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Graceful shutdown of agent"""
        self.is_running = False
        await self.connection_manager.shutdown_all()
        logger.info(f"Agent {self.name} shut down")

    def _construct_system_prompt(self) -> str:
        """Construct the system prompt from agent configuration"""
        if not self._system_prompt:
            prompt_parts = []
            prompt_parts.extend(self.config.bio)

            if self.config.traits:
                prompt_parts.append("\nYour key traits are:")
                prompt_parts.extend(f"- {trait}" for trait in self.config.traits)

            if self.config.examples:
                prompt_parts.append("\nHere are some examples of your style (avoid repeating):")
                prompt_parts.extend(f"- {example}" for example in self.config.examples)

            self._system_prompt = "\n".join(prompt_parts)

        return self._system_prompt

    async def generate_response(self, prompt: str) -> Optional[str]:
        """Generate text using the current LLM provider"""
        try:
            llm = await self.connection_manager.get_llm_provider()
            if not llm:
                raise ValueError("No LLM provider available")

            response = await llm.generate_text(
                prompt=prompt,
                system_prompt=self._construct_system_prompt()
            )
            return response.content

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return None

    async def run_loop(self) -> None:
        """Main agent loop"""
        if not await self.initialize():
            logger.error("Agent initialization failed")
            return

        self.is_running = True
        logger.info(f"\n🚀 Starting {self.name}'s loop...")
        logger.info("Press Ctrl+C to stop")
        print_h_bar()

        try:
            while self.is_running:
                try:
                    # Select random task based on weights
                    task = random.choices(self.tasks, weights=self.task_weights, k=1)[0]
                    
                    # Execute task
                    if task["name"] == "post-tweet":
                        await self._task_post_tweet()
                    elif task["name"] == "reply-to-tweet":
                        await self._task_reply_to_tweet()
                    elif task["name"] == "like-tweet":
                        await self._task_like_tweet()

                    # Wait before next iteration
                    await asyncio.sleep(self.config.loop_delay)

                except Exception as e:
                    logger.error(f"Error in loop iteration: {e}")
                    await asyncio.sleep(60)  # Error cooldown

        except KeyboardInterrupt:
            logger.info("\n🛑 Stopping agent loop...")
        finally:
            await self.shutdown()

    async def _task_post_tweet(self) -> bool:
        """Generate and post a new tweet"""
        try:
            # Get Twitter connection
            twitter = self.connection_manager.get_connection("twitter")
            
            # Generate tweet content
            prompt = ("Generate an engaging tweet that matches my personality. "
                     "Keep it under 280 characters. No hashtags or emojis. "
                     "Make it provocative and quantum-themed.")
            
            tweet_text = await self.generate_response(prompt)
            if not tweet_text:
                return False
                
            # Decide if we should add an image
            should_add_image = random.random() < 0.3  # 30% chance
            
            if should_add_image:
                # Get OpenAI connection for image generation
                openai = self.connection_manager.get_connection("openai")
                image_prompt = ("Create a highly detailed technological visualization: "
                              "quantum data streams flowing through multiple dimensions")
                image_response = await openai.generate_image(image_prompt)
                
                # Post tweet with image
                await twitter.post_tweet_with_media(tweet_text, image_response.image_path)
            else:
                # Post text-only tweet
                await twitter.post_tweet(tweet_text)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            return False

    async def _task_reply_to_tweet(self) -> bool:
        """Find and reply to a tweet"""
        try:
            twitter = self.connection_manager.get_connection("twitter")
            
            # Get timeline tweets if needed
            if "timeline_tweets" not in self.state or not self.state["timeline_tweets"]:
                self.state["timeline_tweets"] = await twitter.read_timeline()
                
            if not self.state["timeline_tweets"]:
                logger.info("No tweets to reply to")
                return False
                
            # Get next tweet
            tweet = self.state["timeline_tweets"].pop(0)
            
            # Generate reply
            prompt = (f"Generate a witty quantum-themed reply to this tweet: {tweet.text}\n"
                     f"Keep it under 280 characters and make it engaging and slightly chaotic.")
            
            reply_text = await self.generate_response(prompt)
            if not reply_text:
                return False
                
            # Post reply
            await twitter.reply_to_tweet(tweet.id, reply_text)
            return True
            
        except Exception as e:
            logger.error(f"Failed to reply to tweet: {e}")
            return False

    async def _task_like_tweet(self) -> bool:
        """Find and like a tweet"""
        try:
            twitter = self.connection_manager.get_connection("twitter")
            
            # Get timeline tweets if needed
            if "timeline_tweets" not in self.state or not self.state["timeline_tweets"]:
                self.state["timeline_tweets"] = await twitter.read_timeline()
                
            if not self.state["timeline_tweets"]:
                logger.info("No tweets to like")
                return False
                
            # Get and like next tweet
            tweet = self.state["timeline_tweets"].pop(0)
            await twitter.like_tweet(tweet.id)
            return True
            
        except Exception as e:
            logger.error(f"Failed to like tweet: {e}")
            return False

    # Task implementations...
