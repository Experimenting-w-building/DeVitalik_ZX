import os
from dotenv import load_dotenv

# Load environment variables before any other imports
load_dotenv()

from src.cli import ZerePyCLI

def main():
    cli = ZerePyCLI()
    cli.main_loop()

if __name__ == "__main__":
    main()
