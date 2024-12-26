import logging
import os
from typing import Dict, Any, List
from dotenv import load_dotenv, set_key
from openai import OpenAI
from src.connections.base_connection import BaseConnection, Action, ActionParameter

logger = logging.getLogger(__name__)

class OpenAIConnectionError(Exception):
    """Base exception for OpenAI connection errors"""
    pass

class OpenAIConfigurationError(OpenAIConnectionError):
    """Raised when there are configuration/credential issues"""
    pass

class OpenAIAPIError(OpenAIConnectionError):
    """Raised when OpenAI API requests fail"""
    pass

class OpenAIConnection(BaseConnection):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model = config.get("model", "gpt-3.5-turbo")
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    @property
    def is_llm_provider(self) -> bool:
        return True

    def validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate OpenAI configuration from JSON"""
        required_fields = ["model"]
        missing_fields = [field for field in required_fields if field not in config]
        
        if missing_fields:
            raise ValueError(f"Missing required configuration fields: {', '.join(missing_fields)}")
            
        # Validate model exists (will be checked in detail during configure)
        if not isinstance(config["model"], str):
            raise ValueError("model must be a string")
            
        return config

    def register_actions(self) -> None:
        """Register available OpenAI actions"""
        self.actions = {
            "generate-text": Action(
                name="generate-text",
                parameters=[
                    ActionParameter("prompt", True, str, "Text prompt for generation"),
                    ActionParameter("system_prompt", False, str, "System prompt for context")
                ],
                description="Generate text using the configured model"
            ),
            "generate-image": Action(
                name="generate-image",
                parameters=[
                    ActionParameter("prompt", True, str, "Image generation prompt")
                ],
                description="Generate an image using DALL-E"
            ),
            "check-model": Action(
                name="check-model",
                parameters=[
                    ActionParameter("model", True, str, "Model name to check availability")
                ],
                description="Check if a specific model is available"
            ),
            "list-models": Action(
                name="list-models",
                parameters=[],
                description="List all available OpenAI models"
            )
        }

    def configure(self) -> bool:
        """Sets up OpenAI API authentication"""
        print("\n🤖 OPENAI API SETUP")

        if self.is_configured():
            print("\nOpenAI API is already configured.")
            response = input("Do you want to reconfigure? (y/n): ")
            if response.lower() != 'y':
                return True

        print("\n📝 To get your OpenAI API credentials:")
        print("1. Go to https://platform.openai.com/account/api-keys")
        print("2. Create a new project or open an existing one.")
        print("3. In your project settings, navigate to the API keys section and create a new API key")
        
        api_key = input("\nEnter your OpenAI API key: ")

        try:
            if not os.path.exists('.env'):
                with open('.env', 'w') as f:
                    f.write('')

            set_key('.env', 'OPENAI_API_KEY', api_key)
            
            # Validate the API key by trying to list models
            client = OpenAI(api_key=api_key)
            client.models.list()

            print("\n✅ OpenAI API configuration successfully saved!")
            print("Your API key has been stored in the .env file.")
            return True

        except Exception as e:
            logger.error(f"Configuration failed: {e}")
            return False

    def is_configured(self, verbose = False) -> bool:
        """Check if OpenAI API key is configured and valid"""
        try:
            load_dotenv()
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                return False

            client = OpenAI(api_key=api_key)
            client.models.list()
            return True
            
        except Exception as e:
            if verbose:
                logger.debug(f"Configuration check failed: {e}")
            return False

    def generate_text(self, prompt: str, system_prompt: str = None) -> str:
        """Generate text using the configured model"""
        try:
            messages = []
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            messages.append({
                "role": "user",
                "content": prompt
            })

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.9,
                max_tokens=280
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            logger.error(f"OpenAI text generation failed: {str(e)}")
            raise

    def check_model(self, model, **kwargs):
        try:
            client = self._get_client
            try:
                client.models.retrieve(model=model)
                # If we get here, the model exists
                return True
            except Exception:
                return False
        except Exception as e:
            raise OpenAIAPIError(e)

    def list_models(self, **kwargs) -> None:
        """List all available OpenAI models"""
        try:
            client = self._get_client()
            response = client.models.list().data
            
            fine_tuned_models = [
                model for model in response 
                if model.owned_by in ["organization", "user", "organization-owner"]
            ]

            logger.info("\nGPT MODELS:")
            logger.info("1. gpt-3.5-turbo")
            logger.info("2. gpt-4")
            logger.info("3. gpt-4-turbo")
            logger.info("4. gpt-4o")
            logger.info("5. gpt-4o-mini")
            
            if fine_tuned_models:
                logger.info("\nFINE-TUNED MODELS:")
                for i, model in enumerate(fine_tuned_models):
                    logger.info(f"{i+1}. {model.id}")
                    
        except Exception as e:
            raise OpenAIAPIError(f"Listing models failed: {e}")
    
    def perform_action(self, action_name: str, params: List[Any] = None) -> Any:
        if action_name not in self.actions:
            raise ValueError(f"Unknown action: {action_name}")

        try:
            if action_name == "generate-text":
                # Debug the incoming parameters
                print(f"DEBUG OpenAI Connection: Received params type: {type(params)}")
                print(f"DEBUG OpenAI Connection: Params length: {len(params) if params else 0}")
                
                if not params:
                    raise ValueError("No parameters provided")
                
                # Extract prompt and system_prompt from params
                prompt = params[0]
                system_prompt = params[1] if len(params) > 1 else None
                
                print(f"DEBUG OpenAI Connection: Extracted prompt: {prompt[:100]}...")
                print(f"DEBUG OpenAI Connection: Has system prompt: {system_prompt is not None}")
                
                return self.generate_text(prompt, system_prompt)
                
            elif action_name == "generate-image":
                if not params or len(params) < 1:
                    raise ValueError("Image prompt is required")
                return self.generate_image(params[0])
                
        except Exception as e:
            logger.error(f"Error in {action_name}: {e}")
            raise Exception(f"Error in {action_name}: {str(e)}")

    def generate_image(self, prompt: str) -> str:
        """Generate image using DALL-E"""
        try:
            response = self.client.images.generate(
                model=self.config.get("dalle_model", "dall-e-3"),
                prompt=prompt,
                size=self.config.get("image_size", "1024x1024"),
                quality=self.config.get("image_quality", "standard"),
                style=self.config.get("style", "vivid"),
                n=1
            )
            return response.data[0].url
        except Exception as e:
            logger.error(f"OpenAI image generation failed: {str(e)}")
            raise