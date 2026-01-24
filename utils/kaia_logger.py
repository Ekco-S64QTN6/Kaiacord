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
from utils.unified_logging import logger as global_logger

# Initialize colorama with autoreset
init(autoreset=True)

# Create Rich console with auto-detection of TTY
console = Console()

# Detect if output is a TTY (terminal) or being redirected
IS_TTY = sys.stdout.isatty()

# Global monitor reference for dashboard integration
_monitor = None

def set_monitor(monitor):
    """Set the monitor instance for dashboard integration."""
    global _monitor
    _monitor = monitor


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
    """Log success messages."""
    # Consolidated logger handles formatting and printing
    global_logger.log(message, "SUCCESS")
    if _monitor:
        _monitor.log_system_event("SUCCESS", message)


def log_user(user_name, user_id, context=""):
    """Log user identity."""
    message = f"{user_name} ({user_id})"
    if context:
        message += f": {context}"
    
    global_logger.log(message, "INFO")


def log_action(message):
    """Log core action messages."""
    global_logger.log(message, "ACTION")
    if _monitor:
        _monitor.log_system_event("ACTION", message)


def log_response(prefix, content, response_time=0.0):
    """Log AI response."""
    message = f"{prefix} {content}"
    if response_time > 0:
        message = f"{prefix} ({response_time:.2f}s) {content}"
        
    global_logger.log(message, "INFO")
    
    if _monitor:
        # Extract tokens saved if present in content
        tokens_saved = 0
        if "[optimized: saved" in content:
            try:
                tokens_saved = int(content.split("saved")[1].split()[0])
            except: pass
        _monitor.log_response(content, tokens_saved=tokens_saved, response_time=response_time)


def log_file(path):
    """Log file paths."""
    global_logger.log(path, "INFO")


def log_critical(message):
    """Log critical messages."""
    global_logger.log(message, "CRITICAL")
    if _monitor:
        _monitor.log_system_event("CRITICAL", message)


def log_warning(message):
    """Log warning messages."""
    global_logger.log(message, "WARNING")
    if _monitor:
        _monitor.log_system_event("WARNING", message)


def log_error(message):
    """Log error messages."""
    global_logger.log(message, "ERROR")
    if _monitor:
        _monitor.log_system_event("ERROR", message)


def log_info(message):
    """Log general info messages."""
    global_logger.log(message, "INFO")


def log_separator():
    """Print a horizontal separator line."""
    # Separators are visual clutter in dashboard logs, so we might skip them
    # or log them as a special info message
    pass


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
    global_logger.log(f"Message from {author_name}: {content}", "INFO")


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
