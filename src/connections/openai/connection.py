from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field
import logging
import asyncio
from datetime import datetime
from openai import AsyncOpenAI, OpenAIError
from src.connections.base import BaseConnection, ConnectionConfig, ConnectionState
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class OpenAIConfig(ConnectionConfig):
    """OpenAI-specific configuration"""
    model: str = "gpt-3.5-turbo"
    temperature: float = 0.7
    max_tokens: int = 1000
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    rate_limit_rpm: int = 60
    # Image generation configs
    image_model: str = "dall-e-3"
    image_size: str = "1024x1024"
    image_quality: str = "standard"
    image_style: str = "vivid"

    def __post_init__(self):
        if not (0 <= self.temperature <= 2):
            raise ValueError("Temperature must be between 0 and 2")
        if self.max_tokens <= 0:
            raise ValueError("Max tokens must be positive")
        if not (-2.0 <= self.frequency_penalty <= 2.0):
            raise ValueError("Frequency penalty must be between -2.0 and 2.0")
        if not (-2.0 <= self.presence_penalty <= 2.0):
            raise ValueError("Presence penalty must be between -2.0 and 2.0")
        if self.rate_limit_rpm <= 0:
            raise ValueError("Rate limit must be positive")

@dataclass
class ChatMessage:
    """Chat message model"""
    role: str
    content: str

@dataclass
class ChatResponse:
    """Response from chat completion"""
    content: str
    finish_reason: Optional[str] = None
    usage: Dict[str, int] = field(default_factory=dict)

@dataclass
class ImageGenerationResponse:
    """Response from image generation"""
    image_url: str
    prompt: str
    revised_prompt: Optional[str] = None
    
class OpenAIConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._client = None
        self._last_request_time = None
        self._request_count = 0
        self._rate_limit_lock = asyncio.Lock()
        
    def validate_config(self, config: Dict[str, Any]) -> OpenAIConfig:
        return OpenAIConfig(**config)
        
    async def initialize(self) -> bool:
        """Initialize OpenAI client"""
        try:
            api_key = await self._load_credentials()
            self._client = AsyncOpenAI(api_key=api_key)
            
            # Verify API access
            await self.health_check()
            
            self.state.is_connected = True
            self.state.last_connected = datetime.now()
            return True
            
        except Exception as e:
            logger.error(f"OpenAI initialization failed: {e}")
            self.state.last_error = str(e)
            return False
            
    async def shutdown(self) -> None:
        """Clean shutdown of OpenAI connection"""
        if self._client:
            await self._client.close()
        self._client = None
        self.state.is_connected = False
        
    async def health_check(self) -> bool:
        """Verify OpenAI API access"""
        try:
            response = await self._client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": "test"}],
                max_tokens=1
            )
            return bool(response)
        except Exception as e:
            logger.error(f"OpenAI health check failed: {e}")
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
                          system_prompt: Optional[str] = None) -> ChatResponse:
        """Generate text using chat completion"""
        return await self._execute_with_retry(
            "generate_text",
            self._generate_text_impl,
            prompt,
            system_prompt
        )
        
    async def _generate_text_impl(self, 
                                prompt: str, 
                                system_prompt: Optional[str]) -> ChatResponse:
        """Implementation of text generation"""
        await self._manage_rate_limit()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = await self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                frequency_penalty=self.config.frequency_penalty,
                presence_penalty=self.config.presence_penalty
            )
            
            return ChatResponse(
                content=response.choices[0].message.content,
                finish_reason=response.choices[0].finish_reason,
                usage=response.usage.model_dump()
            )
        except OpenAIError as e:
            logger.error(f"OpenAI API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in text generation: {e}")
            raise
        
    async def _load_credentials(self) -> str:
        """Load OpenAI credentials from environment"""
        import os
        
        api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            raise ValueError("Missing OpenAI API key")
            
        return api_key

    async def generate_image(self, 
                           prompt: str) -> ImageGenerationResponse:
        """Generate image using DALL-E"""
        return await self._execute_with_retry(
            "generate_image",
            self._generate_image_impl,
            prompt
        )
        
    async def _generate_image_impl(self,
                                 prompt: str) -> ImageGenerationResponse:
        """Implementation of image generation"""
        await self._manage_rate_limit()
        
        try:
            response = await self._client.images.generate(
                model=self.config.image_model,
                prompt=prompt,
                size=self.config.image_size,
                quality=self.config.image_quality,
                style=self.config.image_style,
                n=1,
                response_format="url"
            )
            
            return ImageGenerationResponse(
                image_url=response.data[0].url,
                prompt=prompt,
                revised_prompt=response.data[0].revised_prompt
            )
                
        except OpenAIError as e:
            logger.error(f"OpenAI API error in image generation: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in image generation: {e}")
            raise 