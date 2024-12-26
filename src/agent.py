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

    def loop(self):
        """Main agent loop for autonomous behavior"""
        if not self.is_llm_set:
            self._setup_llm_provider()

        logger.info("\n🚀 Starting agent loop...")
        logger.info("Press Ctrl+C at any time to stop the loop.")
        print_h_bar()

        time.sleep(2)
        logger.info("Starting loop in 5 seconds...")
        for i in range(5, 0, -1):
            logger.info(f"{i}...")
            time.sleep(1)

        last_tweet_time = 0

        try:
            while True:
                success = False
                try:
                    # REPLENISH INPUTS
                    # TODO: Add more inputs to complexify agent behavior
                    if "timeline_tweets" not in self.state or self.state["timeline_tweets"] is None or len(self.state["timeline_tweets"]) == 0:
                        logger.info("\n👀 READING TIMELINE")
                        self.state["timeline_tweets"] = self.connection_manager.perform_action(
                            connection_name="twitter",
                            action_name="read-timeline",
                            params=[]
                        )

                    # CHOOSE AN ACTION
                    # TODO: Add agentic action selection
                    action = random.choices(self.tasks, weights=self.task_weights, k=1)[0]
                    action_name = action["name"]

                    # PERFORM ACTION
                    if action_name == "post-tweet":
                        # Check if it's time to post a new tweet
                        current_time = time.time()
                        if current_time - last_tweet_time >= self.tweet_interval:
                            logger.info("\n📝 GENERATING NEW TWEET")
                            print_h_bar()

                            tweet_prompt = ("Generate a short, chaotic tweet. Keep it under 100 characters. "
                                "Make it feel unhinged and weird. Be sarcastic or mock something about "
                                "technology/crypto/reality. No philosophical quotes or formal language. "
                                "Pure chaos demon energy only.")
                            tweet_text = self.prompt_llm(tweet_prompt)

                            if tweet_text:
                                logger.info("\n🚀 Posting tweet:")
                                logger.info(f"'{tweet_text}'")
                                self.connection_manager.perform_action(
                                    connection_name="twitter",
                                    action_name="post-tweet",
                                    params=[tweet_text]
                                )
                                last_tweet_time = current_time
                                success = True
                                logger.info("\n✅ Tweet posted successfully!")
                        else:
                            logger.info("\n👀 Delaying post until tweet interval elapses...")
                            print_h_bar()
                            continue

                    elif action_name == "reply-to-tweet":
                        if "timeline_tweets" in self.state and self.state["timeline_tweets"] is not None and len(self.state["timeline_tweets"]) > 0:
                            # Get next tweet from inputs
                            tweet = self.state["timeline_tweets"].pop(0)
                            tweet_id = tweet.get('id')
                            if not tweet_id:
                                continue

                            # Check if it's our own tweet using username
                            is_own_tweet = tweet.get('author_username', '').lower() == self.username
                            if is_own_tweet:
                                # pick one of the replies to reply to
                                replies = self.connection_manager.perform_action(
                                    connection_name="twitter",
                                    action_name="get-tweet-replies",
                                    params=[tweet.get('author_id')]
                                )
                                if replies:
                                    self.state["timeline_tweets"].extend(replies[:self.own_tweet_replies_count])
                                continue

                            logger.info(f"\n💬 GENERATING REPLY to: {tweet.get('text', '')[:50]}...")

                            # Customize prompt based on whether it's a self-reply
                            base_prompt = (f"Generate a short, chaotic reply to this tweet: {tweet.get('text')}. "
                                f"Keep it under 100 characters and make it feel like a quick, unhinged response. "
                                f"Be sarcastic, weird, or mock the concept in the tweet. No philosophical quotes, "
                                f"no formal language, and definitely no corporate-speak. Channel pure chaos demon energy. "
                                f"Don't include usernames, hashtags, or emojis.")

                            system_prompt = self._construct_system_prompt()
                            reply_text = self.prompt_llm(prompt=base_prompt, system_prompt=system_prompt)

                            if reply_text:
                                logger.info(f"\n🚀 Posting reply: '{reply_text}'")
                                self.connection_manager.perform_action(
                                    connection_name="twitter",
                                    action_name="reply-to-tweet",
                                    params=[tweet_id, reply_text]
                                )
                                success = True
                                logger.info("✅ Reply posted successfully!")

                    elif action_name == "like-tweet":
                        if "timeline_tweets" in self.state and self.state["timeline_tweets"] is not None and len(self.state["timeline_tweets"]) > 0:
                            # Get next tweet from inputs
                            tweet = self.state["timeline_tweets"].pop(0)
                            tweet_id = tweet.get('id')
                            if not tweet_id:
                                continue

                            logger.info(f"\n👍 LIKING TWEET: {tweet.get('text', '')[:50]}...")

                            self.connection_manager.perform_action(
                                connection_name="twitter",
                                action_name="like-tweet",
                                params=[tweet_id]
                            )
                            success = True
                            logger.info("✅ Tweet liked successfully!")

                    elif action_name == "post-image-tweet":
                        current_time = time.time()
                        if current_time - last_tweet_time >= self.tweet_interval:
                            logger.info("\n🎨 GENERATING IMAGE TWEET")
                            print_h_bar()

                            try:
                                # Generate image prompt using base LLM
                                prompt = ("Generate a prompt for DALL-E to create a surreal, technological visualization. "
                                         "The image should reflect quantum computing, dimensional barriers, or digital consciousness. "
                                         "Make it weird but engaging. Don't include any specific names or brands.")
                                
                                # Fix 1: Pass prompt as list for generate-text
                                image_prompt = self.connection_manager.perform_action(
                                    connection_name=self.model_provider,
                                    action_name="generate-text",
                                    params=[prompt]
                                )

                                if image_prompt:
                                    # Generate image
                                    image_url = self.connection_manager.perform_action(
                                        connection_name="openai",
                                        action_name="generate-image",
                                        params=[image_prompt]  # Fix 2: Keep as list for generate-image
                                    )

                                    if image_url:
                                        # Generate tweet text
                                        tweet_prompt = f"Generate a tweet to accompany this image. The image shows: {image_prompt}"
                                        # Fix 3: Pass prompt as list for generate-text
                                        tweet_text = self.connection_manager.perform_action(
                                            connection_name=self.model_provider,
                                            action_name="generate-text",
                                            params=[tweet_prompt]
                                        )

                                        # Post tweet with image
                                        if tweet_text:
                                            logger.info("\n🚀 Posting image tweet:")
                                            logger.info(f"Text: '{tweet_text}'")
                                            logger.info(f"Image prompt: '{image_prompt}'")
                                            
                                            self.connection_manager.perform_action(
                                                connection_name="twitter",
                                                action_name="post-tweet-with-media",
                                                params=[tweet_text, image_url]
                                            )
                                            
                                            last_tweet_time = current_time
                                            success = True
                                            logger.info("\n✅ Image tweet posted successfully!")

                            except Exception as e:
                                logger.error(f"\nError in image tweet generation: {str(e)}")
                                success = False

                    logger.info(f"\n⏳ Waiting {self.loop_delay} seconds before next loop...")
                    print_h_bar()
                    time.sleep(self.loop_delay if success else 60)

                except Exception as e:
                    logger.error(f"\n❌ Error in agent loop iteration: {e}")
                    logger.info(f"⏳ Waiting {self.loop_delay} seconds before retrying...")
                    time.sleep(self.loop_delay)

        except KeyboardInterrupt:
            logger.info("\n🛑 Agent loop stopped by user.")
            return

    def generate_reply(self, tweet: Dict[str, Any]) -> str:
        """Generate a reply to a tweet"""
        # Let's add debug logging here
        print(f"DEBUG: Tweet text to reply to: {tweet.get('text')}")
        
        base_prompt = (f"Generate a short, chaotic reply to this tweet: {tweet.get('text')}. "
            f"Keep it under 100 characters and make it feel like a quick, unhinged response.")
        
        # Debug the prompt and params
        print(f"DEBUG: Base prompt: {base_prompt}")
        print(f"DEBUG: About to call prompt_llm with prompt")
        
        return self.prompt_llm(base_prompt)
