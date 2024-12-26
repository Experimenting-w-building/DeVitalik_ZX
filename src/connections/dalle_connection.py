from typing import Any, Dict, List
import openai
from .base_connection import BaseConnection

class DalleConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model = config.get("dalle_model", "dall-e-3")
        self.size = config.get("image_size", "1024x1024")
        self.quality = config.get("image_quality", "standard")
        self.style = config.get("style", "vivid")

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        required_fields = ["dalle_model"]
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")
        return config

    def generate_image(self, prompt: str) -> str:
        """Generate image using DALL-E and return URL"""
        try:
            response = openai.Image.create(
                model=self.model,
                prompt=prompt,
                size=self.size,
                quality=self.quality,
                style=self.style,
                n=1
            )
            return response.data[0].url
        except Exception as e:
            raise Exception(f"Failed to generate image: {str(e)}")

    def perform_action(self, action_name: str, params: List[Any] = None) -> Any:
        if action_name == "generate-image":
            if not params or len(params) < 1:
                raise ValueError("Image prompt is required")
            return self.generate_image(params[0])
        else:
            raise ValueError(f"Unknown action: {action_name}") 