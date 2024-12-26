from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
import logging
import asyncio
from datetime import datetime
import tweepy
from src.connections.base import BaseConnection, ConnectionConfig, ConnectionState

logger = logging.getLogger(__name__)

@dataclass
class TwitterConfig(ConnectionConfig):
    """Twitter-specific configuration"""
    consumer_key: str = ""
    consumer_secret: str = ""
    access_token: str = ""
    access_token_secret: str = ""
    timeline_read_count: int = 10
    
    def __post_init__(self):
        if not self.consumer_key:
            raise ValueError("Missing consumer key")
        if not self.consumer_secret:
            raise ValueError("Missing consumer secret")
        if not self.access_token:
            raise ValueError("Missing access token")
        if not self.access_token_secret:
            raise ValueError("Missing access token secret")
        if self.timeline_read_count <= 0:
            raise ValueError("Timeline read count must be positive")

@dataclass
class Tweet:
    """Tweet model"""
    id: str
    text: str
    author_id: str
    author_username: Optional[str] = None
    created_at: Optional[datetime] = None

class TwitterConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._client = None
        self._api = None
        
    def validate_config(self, config: Dict[str, Any]) -> TwitterConfig:
        return TwitterConfig(**config)
        
    async def initialize(self) -> bool:
        """Initialize Twitter client"""
        try:
            # Initialize Twitter client
            auth = tweepy.OAuthHandler(
                self.config.consumer_key,
                self.config.consumer_secret
            )
            auth.set_access_token(
                self.config.access_token,
                self.config.access_token_secret
            )
            
            self._client = tweepy.Client(
                consumer_key=self.config.consumer_key,
                consumer_secret=self.config.consumer_secret,
                access_token=self.config.access_token,
                access_token_secret=self.config.access_token_secret
            )
            
            self._api = tweepy.API(auth)
            
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
        """Verify Twitter API access"""
        try:
            me = await asyncio.to_thread(self._api.verify_credentials)
            return bool(me)
        except Exception as e:
            logger.error(f"Twitter health check failed: {e}")
            return False
            
    async def post_tweet(self, text: str) -> Tweet:
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
        
    async def post_tweet_with_media(self, text: str, media_url: str) -> Tweet:
        """Post a tweet with media"""
        return await self._execute_with_retry(
            "post_tweet_with_media",
            self._post_tweet_with_media_impl,
            text,
            media_url
        )
        
    async def _post_tweet_with_media_impl(self, text: str, media_url: str) -> Tweet:
        """Implementation of media tweet posting"""
        if len(text) > 280:
            raise ValueError("Tweet exceeds 280 character limit")
            
        # Upload media
        media = await asyncio.to_thread(
            self._api.media_upload,
            media_url
        )
        
        # Post tweet with media
        response = await asyncio.to_thread(
            self._client.create_tweet,
            text=text,
            media_ids=[media.media_id]
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
        
    async def reply_to_tweet(self, tweet_id: str, text: str) -> Tweet:
        """Reply to a tweet"""
        return await self._execute_with_retry(
            "reply_to_tweet",
            self._reply_to_tweet_impl,
            tweet_id,
            text
        )
        
    async def _reply_to_tweet_impl(self, tweet_id: str, text: str) -> Tweet:
        """Implementation of tweet reply"""
        if len(text) > 280:
            raise ValueError("Reply exceeds 280 character limit")
            
        response = await asyncio.to_thread(
            self._client.create_tweet,
            text=text,
            in_reply_to_tweet_id=tweet_id
        )
        
        tweet_data = response.data
        return Tweet(
            id=tweet_data['id'],
            text=text,
            author_id=tweet_data['author_id'],
            created_at=datetime.now()
        )
        
    async def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet"""
        return await self._execute_with_retry(
            "like_tweet",
            self._like_tweet_impl,
            tweet_id
        )
        
    async def _like_tweet_impl(self, tweet_id: str) -> bool:
        """Implementation of tweet liking"""
        response = await asyncio.to_thread(
            self._client.like,
            tweet_id
        )
        return bool(response.data) 