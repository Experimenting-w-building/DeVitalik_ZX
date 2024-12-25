from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import logging
import asyncio
from datetime import datetime
import tweepy
from src.connections.base import BaseConnection, ConnectionConfig, ConnectionState

logger = logging.getLogger(__name__)

class TwitterConfig(ConnectionConfig):
    """Twitter-specific configuration"""
    timeline_read_count: int = Field(default=10, gt=0)
    tweet_interval: int = Field(default=900, gt=0)
    own_tweet_replies_count: int = Field(default=2, ge=0)
    
class Tweet(BaseModel):
    """Tweet data model"""
    id: str
    text: str
    author_id: str
    author_username: Optional[str]
    created_at: Optional[datetime]

class TwitterConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._client = None
        self._api = None
        
    def validate_config(self, config: Dict[str, Any]) -> TwitterConfig:
        return TwitterConfig(**config)
        
    async def initialize(self) -> bool:
        """Initialize Twitter API client"""
        try:
            credentials = await self._load_credentials()
            auth = tweepy.OAuthHandler(
                credentials['TWITTER_CONSUMER_KEY'],
                credentials['TWITTER_CONSUMER_SECRET']
            )
            auth.set_access_token(
                credentials['TWITTER_ACCESS_TOKEN'],
                credentials['TWITTER_ACCESS_TOKEN_SECRET']
            )
            
            # Initialize both v1 and v2 clients
            self._api = tweepy.API(auth)
            self._client = tweepy.Client(
                consumer_key=credentials['TWITTER_CONSUMER_KEY'],
                consumer_secret=credentials['TWITTER_CONSUMER_SECRET'],
                access_token=credentials['TWITTER_ACCESS_TOKEN'],
                access_token_secret=credentials['TWITTER_ACCESS_TOKEN_SECRET']
            )
            
            # Verify credentials
            await self.health_check()
            
            self.state.is_connected = True
            self.state.last_connected = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"Twitter initialization failed: {e}")
            self.state.last_error = str(e)
            return False
            
    async def shutdown(self) -> None:
        """Clean shutdown of Twitter connection"""
        self._client = None
        self._api = None
        self.state.is_connected = False
        
    async def health_check(self) -> bool:
        """Verify Twitter credentials and API access"""
        try:
            # Use v1 API to verify credentials
            me = await asyncio.to_thread(self._api.verify_credentials)
            return bool(me)
        except Exception as e:
            logger.error(f"Twitter health check failed: {e}")
            return False
            
    async def post_tweet(self, text: str) -> Optional[Tweet]:
        """Post a new tweet"""
        return await self._execute_with_retry(
            "post_tweet",
            self._post_tweet_impl,
            text
        )
        
    async def _post_tweet_impl(self, text: str) -> Tweet:
        """Implementation of tweet posting"""
        if len(text) > 280:
            raise ValueError("Tweet exceeds 280 character limit")
            
        response = await asyncio.to_thread(
            self._client.create_tweet,
            text=text
        )
        
        tweet_data = response.data
        return Tweet(
            id=tweet_data['id'],
            text=text,
            author_id=tweet_data['author_id'],
            created_at=datetime.now()
        )
        
    async def read_timeline(self, count: Optional[int] = None) -> List[Tweet]:
        """Read tweets from user's timeline"""
        count = count or self.config.timeline_read_count
        return await self._execute_with_retry(
            "read_timeline",
            self._read_timeline_impl,
            count
        )
        
    async def _read_timeline_impl(self, count: int) -> List[Tweet]:
        """Implementation of timeline reading"""
        response = await asyncio.to_thread(
            self._client.get_home_timeline,
            max_results=count,
            tweet_fields=['created_at', 'author_id'],
            expansions=['author_id'],
            user_fields=['username']
        )
        
        tweets = []
        for tweet in response.data or []:
            author = next(
                (u for u in response.includes['users'] if u.id == tweet.author_id),
                None
            )
            tweets.append(Tweet(
                id=tweet.id,
                text=tweet.text,
                author_id=tweet.author_id,
                author_username=author.username if author else None,
                created_at=tweet.created_at
            ))
        return tweets
        
    async def _load_credentials(self) -> Dict[str, str]:
        """Load Twitter credentials from environment"""
        from dotenv import load_dotenv
        import os
        
        load_dotenv()
        required_vars = {
            'TWITTER_CONSUMER_KEY': 'consumer key',
            'TWITTER_CONSUMER_SECRET': 'consumer secret',
            'TWITTER_ACCESS_TOKEN': 'access token',
            'TWITTER_ACCESS_TOKEN_SECRET': 'access token secret'
        }
        
        missing = [desc for var, desc in required_vars.items() 
                  if not os.getenv(var)]
        
        if missing:
            raise ValueError(f"Missing Twitter credentials: {', '.join(missing)}")
            
        return {var: os.getenv(var) for var in required_vars.keys()} 