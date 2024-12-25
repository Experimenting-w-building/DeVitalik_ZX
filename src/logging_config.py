import logging
import sys
from pathlib import Path

def setup_logging():
    """Configure logging for the application"""
    # Create logs directory if it doesn't exist
    Path("logs").mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/zeropy.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Set specific log levels
    logging.getLogger('tweepy').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING) 