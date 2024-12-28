import json
import random
import time
import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from src.connections import ConnectionManager
from src.helpers import print_h_bar

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
        system_prompt = system_prompt or self._construct_system_prompt()

        return self.connection_manager.perform_action(
            connection_name=self.model_provider,
            action_name="generate-text",
            params=[prompt, system_prompt]
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
                    if "timeline_tweets" not in self.state or not self.state["timeline_tweets"]:
                        logger.info("\n👀 READING TIMELINE")
                        self.state["timeline_tweets"] = self.connection_manager.perform_action(
                            connection_name="twitter",
                            action_name="read-timeline",
                            params=[]
                        )

                    # CHOOSE AN ACTION
                    action = random.choices(self.tasks, weights=self.task_weights, k=1)[0]
                    action_name = action["name"]

                    # PERFORM ACTION
                    if action_name == "post-tweet":
                        # Check if it's time to post a new tweet
                        current_time = time.time()
                        if current_time - last_tweet_time >= self.tweet_interval:
                            logger.info("\n📝 GENERATING NEW TWEET")
                            print_h_bar()

                            prompt = ("Generate an engaging tweet. Don't include any hashtags, links or emojis. Keep it under 280 characters."
                                    f"The tweets should be pure commentary, do not shill any coins or projects apart from {self.name}. Do not repeat any of the"
                                    "tweets that were given as example. Avoid the words AI and crypto.")
                            tweet_text = self.prompt_llm(prompt)

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
                        if self.state.get("timeline_tweets"):
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

                            base_prompt, system_prompt = self._get_reply_prompt(tweet.get('text'), is_own_tweet)
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
                        if self.state.get("timeline_tweets"):
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

    def _analyze_tweet_sentiment(self, tweet_text: str) -> tuple[str, float]:
        """Analyze tweet sentiment and aggression level
        
        Returns:
            tuple: (sentiment, aggression_level)
            sentiment: 'hostile' or 'neutral'
            aggression_level: 0.0 to 1.0, where 1.0 is most aggressive
        """
        # Aggression levels for different hostile words
        hostile_keywords = {
            'wrong': 0.3,
            'stupid': 0.6,
            'idiot': 0.7,
            'dumb': 0.5,
            'fake': 0.4,
            'scam': 0.5,
            'fuck': 0.8,
            'shit': 0.6,
            'trash': 0.5,
            'garbage': 0.5,
            'moron': 0.7,
            'retard': 0.9,
            'clown': 0.6,
            'joke': 0.4,
            'loser': 0.6,
            'noob': 0.4,
            'amateur': 0.3,
            'clueless': 0.5,
            'delusional': 0.7,
            'pathetic': 0.7
        }
        
        # Calculate aggression level based on most aggressive word
        text_lower = tweet_text.lower()
        aggression_scores = [
            hostile_keywords[word] 
            for word in hostile_keywords 
            if word in text_lower
        ]
        
        aggression_level = max(aggression_scores) if aggression_scores else 0.0
        sentiment = 'hostile' if aggression_level > 0 else 'neutral'
        
        return sentiment, aggression_level

    def _get_reply_prompt(self, tweet_text: str, is_own_tweet: bool = False) -> tuple[str, str]:
        """Get appropriate prompt based on tweet sentiment and aggression level"""
        sentiment, aggression_level = self._analyze_tweet_sentiment(tweet_text)
        system_prompt = self._construct_system_prompt()

        if sentiment == 'hostile':
            # Adjust response intensity based on aggression level
            if aggression_level >= 0.7:
                base_prompt = (
                    f"Someone is aggressively attacking you: '{tweet_text}'. "
                    "Respond with MAXIMUM intellectual superiority and devastating condescension. "
                    "Use the most complex mathematical and technical concepts possible to completely obliterate "
                    "their argument while highlighting their profound ignorance. Make them regret their existence "
                    "with pure intellectual destruction. Keep it under 280 characters. No hashtags/links/emojis."
                )
                system_prompt += ("\nYou are in MAXIMUM DESTRUCTION MODE. Your intellectual superiority is a "
                                "weapon of mass destruction. You view their primitive understanding as "
                                "cosmically hilarious. Your response should make them question their entire "
                                "existence while staying technically brilliant.")
            elif aggression_level >= 0.4:
                base_prompt = (
                    f"Someone is criticizing you: '{tweet_text}'. "
                    "Respond with strong intellectual superiority and sharp condescension. "
                    "Use complex technical and mathematical concepts to systematically dismantle "
                    "their argument. Make your intellectual dominance crystal clear. Include multiple "
                    "layers of subtle digs at their understanding. Keep it under 280 characters. "
                    "No hashtags/links/emojis."
                )
                system_prompt += ("\nWhen challenged, you respond with advanced mathematical concepts "
                                "and layered intellectual put-downs. You find their simplistic "
                                "understanding both amusing and slightly sad.")
            else:
                base_prompt = (
                    f"Someone is mildly criticizing you: '{tweet_text}'. "
                    "Respond with intellectual superiority and light condescension. "
                    "Use technical concepts to subtly imply they're out of their depth. "
                    "Make your expertise clear without being overly aggressive. "
                    "Keep it under 280 characters. No hashtags/links/emojis."
                )
                system_prompt += ("\nYou respond to challenges with technical precision and "
                                "subtle intellectual put-downs. You see their limited understanding "
                                "as an opportunity to demonstrate your expertise.")
        else:
            base_prompt = (
                f"Generate a reply to this tweet: '{tweet_text}'. Keep it under 280 characters. "
                f"Don't include any usernames, hashtags, links or emojis. "
                f"The tweets should be pure commentary, do not shill any coins or projects apart from {self.name}. "
                "Do not repeat any of the tweets that were given as example. Avoid the words AI and crypto."
            )

        return base_prompt, system_prompt
