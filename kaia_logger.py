"""
Kaia's Color-Coded Logging System
Uses colorama for ANSI colors and Rich for advanced formatting.
Automatically strips colors when output is redirected to files.
"""

import sys
from datetime import datetime
from colorama import Fore, Back, Style, init
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Initialize colorama with autoreset
init(autoreset=True)

# Create Rich console with auto-detection of TTY
console = Console()

# Detect if output is a TTY (terminal) or being redirected
IS_TTY = sys.stdout.isatty()


def _get_timestamp():
    """Return current timestamp in dim gray (only if TTY)."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if IS_TTY:
        return f"{Style.DIM}{Fore.WHITE}[{timestamp}]{Style.RESET_ALL} "
    else:
        return f"[{timestamp}] "


def _colorize(text, color_code):
    """Apply color only if output is a TTY."""
    if IS_TTY:
        return f"{color_code}{text}{Style.RESET_ALL}"
    else:
        return text


# ============================================================================
# CORE LOGGING FUNCTIONS
# ============================================================================

def log_success(message):
    """Log success messages with bold green checkmark."""
    prefix = _colorize("✓", Fore.GREEN + Style.BRIGHT)
    print(f"{_get_timestamp()}{prefix} {_colorize(message, Fore.GREEN + Style.BRIGHT)}")


def log_user(user_name, user_id, context=""):
    """Log user identity in cyan."""
    user_str = _colorize(f"{user_name}", Fore.CYAN)
    user_id_str = _colorize(f"({user_id})", Fore.CYAN)
    
    if context:
        print(f"{_get_timestamp()}{user_str} {user_id_str}: {context}")
    else:
        print(f"{_get_timestamp()}{user_str} {user_id_str}")


def log_action(message):
    """Log core action messages in yellow."""
    print(f"{_get_timestamp()}{_colorize(message, Fore.YELLOW)}")


def log_response(prefix, content):
    """Log AI response with magenta prefix and white content."""
    formatted_prefix = _colorize(prefix, Fore.MAGENTA + Style.BRIGHT)
    formatted_content = _colorize(content, Fore.WHITE)
    print(f"{_get_timestamp()}{formatted_prefix} {formatted_content}")


def log_file(path):
    """Log file paths with underlined blue."""
    if IS_TTY:
        formatted_path = f"{Fore.BLUE}{Style.BRIGHT}\033[4m{path}\033[0m{Style.RESET_ALL}"
    else:
        formatted_path = path
    print(f"{_get_timestamp()}{formatted_path}")


def log_critical(message):
    """Log critical messages in bold red."""
    print(f"{_get_timestamp()}{_colorize(message, Fore.RED + Style.BRIGHT)}")


def log_warning(message):
    """Log warning messages in yellow with 'Warning:' prefix."""
    prefix = _colorize("Warning:", Fore.YELLOW + Style.BRIGHT)
    print(f"{_get_timestamp()}{prefix} {message}")


def log_error(message):
    """Log error messages in red with 'ERROR:' prefix."""
    prefix = _colorize("ERROR:", Fore.RED + Style.BRIGHT)
    print(f"{_get_timestamp()}{prefix} {message}")


def log_info(message):
    """Log general info messages without special color."""
    print(f"{_get_timestamp()}{message}")


def log_separator():
    """Print a horizontal separator line after interactions."""
    if IS_TTY:
        separator = f"{Style.DIM}{Fore.WHITE}{'─' * 80}{Style.RESET_ALL}"
    else:
        separator = "─" * 80
    print(separator)


# ============================================================================
# RICH TABLE FORMATTING FOR RAG CONTEXT
# ============================================================================

def format_rag_table(nodes, query_info=None):
    """
    Display RAG context nodes as a beautiful Rich table.
    
    Args:
        nodes: List of context node strings
        query_info: Optional dict with 'query_type', 'persona_count', 'user_log_count', 'lore_count'
    """
    if not nodes:
        log_info("No context nodes retrieved.")
        return
    
    # Create table
    table = Table(
        title=f"📚 RAG Context ({len(nodes)} nodes)",
        title_style="bold cyan",
        show_header=True,
        header_style="bold magenta",
        border_style="dim white",
        expand=False
    )
    
    table.add_column("#", style="dim cyan", width=4, justify="right")
    table.add_column("Content", style="white", no_wrap=False)
    table.add_column("Length", style="dim yellow", width=8, justify="right")
    
    # Add rows
    for i, node in enumerate(nodes):
        # Truncate very long nodes for display
        display_content = node[:200] + "..." if len(node) > 200 else node
        table.add_row(str(i), display_content, str(len(node)))
    
    # Print timestamp manually since Rich console bypasses our timestamping
    print(_get_timestamp()[:-1])  # Remove trailing space
    console.print(table)
    
    # Add query info if provided
    if query_info:
        info_text = (
            f"Query Type: {query_info.get('query_type', 'N/A')} | "
            f"Persona: {query_info.get('persona_count', 0)} | "
            f"User Logs: {query_info.get('user_log_count', 0)} | "
            f"Lore: {query_info.get('lore_count', 0)}"
        )
        print(f"{_get_timestamp()}{_colorize(info_text, Style.DIM + Fore.CYAN)}")


def format_rag_panel(title, content):
    """
    Display RAG-related information in a Rich panel.
    
    Args:
        title: Panel title
        content: Content to display in panel
    """
    panel = Panel(
        content,
        title=title,
        title_align="left",
        border_style="cyan",
        padding=(1, 2)
    )
    print(_get_timestamp()[:-1])
    console.print(panel)


# ============================================================================
# CONVENIENCE FUNCTIONS FOR COMMON PATTERNS
# ============================================================================

def log_model_action(model_name, action):
    """Log model-related actions (loading, unloading, etc.)."""
    model_str = _colorize(model_name, Fore.CYAN + Style.BRIGHT)
    log_action(f"{action}: {model_str}")


def log_message_received(author_name, author_id, content):
    """Log received Discord message."""
    user_str = _colorize(f"{author_name}", Fore.CYAN)
    # Truncate long messages
    truncated = content[:100] + "..." if len(content) > 100 else content
    print(f"{_get_timestamp()}Message from {user_str}: {truncated}")


def log_context_retrieval(query, count=None):
    """Log context retrieval action."""
    if count is not None:
        log_action(f"Retrieving context for: {query} (found {count} nodes)")
    else:
        log_action(f"Retrieving context for: {query}")


# ============================================================================
# TEST FUNCTION
# ============================================================================

def test_logging():
    """Test all logging functions to verify colors and formatting."""
    print("\n" + "=" * 80)
    print("KAIA LOGGING SYSTEM TEST")
    print("=" * 80 + "\n")
    
    log_success("Model prewarmed successfully!")
    log_user("Gwaihir the Wizend", "123456789", "Sent a message")
    log_action("Calling ollama.chat...")
    log_action("Retrieving context from RAG...")
    log_action("Processing vision task...")
    log_response("Got response:", "This is a sample AI response that would be displayed in the terminal.")
    log_file("/home/ekco/github/Kaiacord/knowledge_base/user_logs/123456789_gwaihir_the_wizend.md")
    log_critical("Shutting down...")
    log_warning("This is a warning message")
    log_error("This is an error message")
    log_info("This is general information")
    
    print("\n")
    log_separator()
    print("\n")
    
    # Test RAG table
    sample_nodes = [
        "User: What's your favorite color? Kaia: don't have one. colors are wavelengths. i don't play favorites with physics.",
        "User: Tell me about yourself. Kaia: i'm kaia. i exist in text. i think, i respond, i remember. that's the scope.",
        "Kaia's Core Principles: Be direct, grounded, and real. No corporate-speak, no hand-holding.",
    ]
    
    format_rag_table(
        sample_nodes,
        query_info={
            'query_type': 'identity',
            'persona_count': 1,
            'user_log_count': 2,
            'lore_count': 0
        }
    )
    
    print("\n")
    log_success("All logging tests completed!")
    log_separator()


if __name__ == "__main__":
    test_logging()
