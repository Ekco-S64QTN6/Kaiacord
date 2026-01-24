import re
import sys

class ANSIStripper:
    """Strips ANSI codes from output during curses"""
    
    def __init__(self):
        self.original_stdout = sys.stdout
        self.original_stderr = sys.stderr
        
    def strip_ansi(self, text):
        """Remove ANSI escape sequences from text"""
        if not text:
            return text
        
        # Remove all ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    def install(self):
        """Install the ANSI stripper"""
        class StrippedStdout:
            def __init__(self, stripper):
                self.stripper = stripper
            
            def write(self, text):
                # Strip ANSI codes before writing
                text = self.stripper.strip_ansi(text)
                self.stripper.original_stdout.write(text)
            
            def flush(self):
                self.stripper.original_stdout.flush()
        
        sys.stdout = StrippedStdout(self)
        sys.stderr = StrippedStdout(self)
    
    def uninstall(self):
        """Restore original stdout/stderr"""
        sys.stdout = self.original_stdout
        sys.stderr = self.original_stderr

# Global instance
ansi_stripper = ANSIStripper()
