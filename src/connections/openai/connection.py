from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field
import logging
import asyncio
from datetime import datetime
import openai
from openai import AsyncOpenAI
from src.connections.base import BaseConnection, ConnectionConfig, ConnectionState
from base64 import b64decode
from pathlib import Path

logger = logging.getLogger(__name__)

class OpenAIConfig(ConnectionConfig):
    """OpenAI-specific configuration"""
    model: str = Field(default="gpt-3.5-turbo")
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=1000, gt=0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    rate_limit_rpm: int = Field(default=60, gt=0)
    # Image generation configs
    image_model: str = Field(default="dall-e-3")
    image_size: str = Field(default="1024x1024")
    image_quality: str = Field(default="standard")
    image_style: str = Field(default="vivid")
    save_dir: str = Field(default="generated_images")

class ChatMessage(BaseModel):
    """Chat message model"""
    role: str
    content: str

class ChatResponse(BaseModel):
    """Response from chat completion"""
    content: str
    finish_reason: Optional[str]
    usage: Dict[str, int]

class ImageGenerationResponse(BaseModel):
    """Response from image generation"""
    image_path: Path
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
            models = await self._client.models.list()
            return bool(models)
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
        
    async def _load_credentials(self) -> str:
        """Load OpenAI credentials from environment"""
        from dotenv import load_dotenv
        import os
        
        load_dotenv()
        api_key = os.getenv('OPENAI_API_KEY')
        
        if not api_key:
            raise ValueError("Missing OpenAI API key")
            
        return api_key 

    async def generate_image(self, 
                           prompt: str,
                           save: bool = True) -> ImageGenerationResponse:
        """Generate image using DALL-E"""
        return await self._execute_with_retry(
            "generate_image",
            self._generate_image_impl,
            prompt,
            save
        )
        
    async def _generate_image_impl(self,
                                 prompt: str,
                                 save: bool) -> ImageGenerationResponse:
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
                response_format="b64_json"
            )
            
            revised_prompt = response.data[0].revised_prompt
            image_data = b64decode(response.data[0].b64_json)
            
            if save:
                # Create save directory if it doesn't exist
                save_dir = Path(self.config.save_dir)
                save_dir.mkdir(exist_ok=True)
                
                # Generate unique filename based on timestamp
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                image_path = save_dir / f"quantum_vision_{timestamp}.png"
                
                # Save the image
                with open(image_path, "wb") as f:
                    f.write(image_data)
                
                return ImageGenerationResponse(
                    image_path=image_path,
                    prompt=prompt,
                    revised_prompt=revised_prompt
                )
            else:
                # Return in-memory image data if not saving
                return ImageGenerationResponse(
                    image_data=image_data,
                    prompt=prompt,
                    revised_prompt=revised_prompt
                )
                
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            raise

    async def _ensure_save_directory(self) -> None:
        """Ensure the image save directory exists"""
        save_dir = Path(self.config.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True) 