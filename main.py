import asyncio
import logging
from src.logging_config import setup_logging
from src.cli import ZerePyCLI

# Initialize logging
setup_logging()

logger = logging.getLogger(__name__)

async def main():
    try:
        cli = ZerePyCLI()
        await cli.main_loop()
    except Exception as e:
        logger.error(f"Application error: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\nApplication stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
