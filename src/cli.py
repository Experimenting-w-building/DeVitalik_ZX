import sys
import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List
from pathlib import Path
from src.agent import ZerePyAgent
from src.helpers import print_h_bar
import os

# Configure logging
logger = logging.getLogger(__name__)

@dataclass
class Command:
    """Dataclass to represent a CLI command"""
    name: str
    description: str
    tips: List[str]
    handler: Callable
    aliases: List[str] = None

    def __post_init__(self):
        if self.aliases is None:
            self.aliases = []

class ZerePyCLI:
    def __init__(self):
        self.agent = None
        
        # Create config directory if it doesn't exist
        self.config_dir = Path.home() / '.zerepy'
        self.config_dir.mkdir(exist_ok=True)
        
        # Initialize command registry
        self._initialize_commands()

    def _initialize_commands(self) -> None:
        """Initialize all CLI commands"""
        self.commands: Dict[str, Command] = {}
        
        # Help command
        self._register_command(
            Command(
                name="help",
                description="Displays a list of all available commands, or help for a specific command.",
                tips=["Try 'help' to see available commands.",
                      "Try 'help {command}' to get more information about a specific command."],
                handler=self.help,
                aliases=['h', '?']
            )
        )
        
        # Agent action command
        self._register_command(
            Command(
                name="agent-action",
                description="Runs a single agent action.",
                tips=["Format: agent-action {connection} {action}",
                      "Use 'list-connections' to see available connections.",
                      "Use 'list-actions' to see available actions."],
                handler=self.agent_action,
                aliases=['action', 'run']
            )
        )
        
        # Agent loop command
        self._register_command(
            Command(
                name="agent-loop",
                description="Starts the current agent's autonomous behavior loop.",
                tips=["Press Ctrl+C to stop the loop"],
                handler=self.agent_loop,
                aliases=['loop', 'start']
            )
        )
        
        # List agents command
        self._register_command(
            Command(
                name="list-agents",
                description="Lists all available agents you have on file.",
                tips=["Agents are stored in the 'agents' directory",
                      "Use 'load-agent' to load an available agent"],
                handler=self.list_agents,
                aliases=['agents', 'ls-agents']
            )
        )
        
        # Load agent command
        self._register_command(
            Command(
                name="load-agent",
                description="Loads an agent from a file.",
                tips=["Format: load-agent {agent_name}",
                      "Use 'list-agents' to see available agents"],
                handler=self.load_agent,
                aliases=['load']
            )
        )
        
        # Exit command
        self._register_command(
            Command(
                name="exit",
                description="Exits the ZerePy CLI.",
                tips=["You can also use Ctrl+D to exit"],
                handler=self.exit,
                aliases=['quit', 'q']
            )
        )

    def _register_command(self, command: Command) -> None:
        """Register a command and its aliases"""
        self.commands[command.name] = command
        for alias in command.aliases:
            self.commands[alias] = command

    def _get_prompt_message(self) -> str:
        """Generate the prompt message based on current state"""
        agent_status = f"({self.agent.name})" if self.agent else "(no agent)"
        return f'ZerePy-CLI {agent_status} > '

    def _handle_command(self, input_string: str) -> None:
        """Parse and handle a command input"""
        input_list = input_string.split()
        if not input_list:
            return
            
        command_string = input_list[0].lower()

        try:
            command = self.commands.get(command_string)
            if command:
                command.handler(input_list)
            else:
                self._handle_unknown_command(command_string)
        except Exception as e:
            logger.error(f"Error executing command: {e}")

    def _handle_unknown_command(self, command: str) -> None:
        """Handle unknown command with suggestions"""
        logger.warning(f"Unknown command: '{command}'") 
        logger.info("Use 'help' to see all available commands.")

    def _print_welcome_message(self) -> None:
        """Print welcome message and initial status"""
        print_h_bar()
        logger.info("👋 Welcome to the ZerePy CLI!")
        logger.info("Type 'help' for a list of commands.")
        print_h_bar() 

    def help(self, input_list: List[str]) -> None:
        """List all commands supported by the CLI"""
        logger.info("\nAvailable Commands:")
        for cmd_name, cmd in self.commands.items():
            if cmd_name == cmd.name:  # Only show main commands, not aliases
                logger.info(f"  {cmd_name:<15} - {cmd.description}")

    async def agent_loop(self, input_list: List[str]) -> None:
        """Handle agent loop command"""
        if self.agent is None:
            logger.info("No agent loaded. Use 'load-agent' first.")
            return

        try:
            await self.agent.run_loop()
        except KeyboardInterrupt:
            logger.info("\n🛑 Agent loop stopped by user")
        except Exception as e:
            logger.error(f"Error in agent loop: {e}")

    def list_agents(self, input_list: List[str]) -> None:
        """Handle list agents command"""
        logger.info("\nAvailable Agents:")
        agents_dir = Path("agents")
        if not agents_dir.exists():
            logger.info("No agents directory found.")
            return

        agents = list(agents_dir.glob("*.json"))
        if not agents:
            logger.info("No agents found.")
            return

        for agent_file in sorted(agents):
            if agent_file.stem == "general":
                continue
            logger.info(f"- {agent_file.stem}")

    def load_agent(self, input_list: List[str]) -> None:
        """Handle load agent command"""
        if len(input_list) < 2:
            logger.info("Please specify an agent name.")
            logger.info("Format: load-agent {agent_name}")
            logger.info("Use 'list-agents' to see available agents.")
            return

        try: 
            self.agent = ZerePyAgent(input_list[1])
            logger.info(f"\n✅ Successfully loaded agent: {self.agent.name}")
        except FileNotFoundError:
            logger.error(f"Agent file not found: {input_list[1]}")
            logger.info("Use 'list-agents' to see available agents.")
        except Exception as e:
            logger.error(f"Error loading agent: {e}")

    def exit(self, input_list: List[str]) -> None:
        """Exit the CLI gracefully"""
        logger.info("\nGoodbye! 👋")
        sys.exit(0)

    def main_loop(self) -> None:
        """Main CLI loop"""
        self._print_welcome_message()
        
        while True:
            try:
                user_input = input(self._get_prompt_message()).strip()
                if user_input:
                    self._handle_command(user_input)
                print_h_bar()
            except KeyboardInterrupt:
                continue
            except EOFError:
                self.exit([])
            except Exception as e:
                logger.error(f"Unexpected error: {e}") 