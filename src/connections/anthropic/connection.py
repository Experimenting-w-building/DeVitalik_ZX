from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import logging
import asyncio
from datetime import datetime
import anthropic
from src.connections.base import BaseConnection, ConnectionConfig, ConnectionState

logger = logging.getLogger(__name__)

class AnthropicConfig(ConnectionConfig):
    """Anthropic-specific configuration"""
    model: str = Field(default="claude-3-sonnet-20240229")
    max_tokens: int = Field(default=1000, gt=0)
    temperature: float = Field(default=0.7, ge=0, le=1)
    top_p: float = Field(default=1.0, ge=0, le=1)
    rate_limit_rpm: int = Field(default=50, gt=0)  # Conservative default

class Message(BaseModel):
    """Message model for Claude"""
    role: str
    content: str

class AnthropicResponse(BaseModel):
    """Response from Claude"""
    content: str
    model: str
    stop_reason: Optional[str]
    usage: Dict[str, int]

class AnthropicConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._client = None
        self._last_request_time = None
        self._request_count = 0
        self._rate_limit_lock = asyncio.Lock()
        
    def validate_config(self, config: Dict[str, Any]) -> AnthropicConfig:
        return AnthropicConfig(**config)
        
    async def initialize(self) -> bool:
        """Initialize Anthropic client"""
        try:
            api_key = await self._load_credentials()
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            
            # Verify API access
            await self.health_check()
            
            self.state.is_connected = True
            self.state.last_connected = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"Anthropic initialization failed: {e}")
            self.state.last_error = str(e)
            return False
            
    async def shutdown(self) -> None:
        """Clean shutdown of Anthropic connection"""
        if self._client:
            await self._client.aclose()
        self._client = None
        self.state.is_connected = False
        
    async def health_check(self) -> bool:
        """Verify Anthropic API access"""
        try:
            # Simple message to verify API access
            await self._client.messages.create(
                model=self.config.model,
                max_tokens=1,
                messages=[{"role": "user", "content": "test"}]
            )
            return True
        except Exception as e:
            logger.error(f"Anthropic health check failed: {e}")
            return False

    async def _manage_rate_limit(self):
        """Manage API rate limiting"""
        async with self._rate_limit_lock:
            current_time = datetime.now()
            if self._last_request_time:
                # Reset counter if a minute has passed
                if (current_time - self._last_request_time).seconds >= 60:
                    self._request_count = 0
                    self._last_request_time = current_time
                # Wait if we've hit the rate limit
                elif self._request_count >= self.config.rate_limit_rpm:
                    wait_time = 60 - (current_time - self._last_request_time).seconds
                    await asyncio.sleep(wait_time)
                    self._request_count = 0
                    self._last_request_time = datetime.now()
            else:
                self._last_request_time = current_time
            
            self._request_count += 1
            
    async def generate_text(self, 
                          prompt: str, 
                          system_prompt: Optional[str] = None) -> AnthropicResponse:
        """Generate text using Claude"""
        return await self._execute_with_retry(
            "generate_text",
            self._generate_text_impl,
            prompt,
            system_prompt
        )
        
    async def _generate_text_impl(self, 
                                prompt: str, 
                                system_prompt: Optional[str]) -> AnthropicResponse:
        """Implementation of text generation"""
        await self._manage_rate_limit()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self._client.messages.create(
                model=self.config.model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                top_p=self.config.top_p
            )
            
            return AnthropicResponse(
                content=response.content[0].text,
                model=response.model,
                stop_reason=response.stop_reason,
                usage={
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens
                }
            )
            
        except Exception as e:
            logger.error(f"Text generation failed: {e}")
            raise
        
    async def _load_credentials(self) -> str:
        """Load Anthropic credentials from environment"""
        import os
        
        api_key = os.getenv('ANTHROPIC_API_KEY')
        
        if not api_key:
            raise ValueError("Missing Anthropic API key")
            
        return api_key 