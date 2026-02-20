import time
import threading
from collections import defaultdict, deque
from typing import Dict, Any, List

class PerformanceMonitor:
    """Track system performance metrics and timings."""
    
    def __init__(self):
        self.timers = {}
        self.metrics = {
            'cache_hits': 0,
            'cache_misses': 0,
            'exact_hits': 0,
            'hallucinations_detected': 0,
            'api_calls': 0,
            'api_errors': 0
        }
        self.history = defaultdict(lambda: deque(maxlen=100))
        self.lock = threading.Lock()
        
    def start_timer(self, name):
        """Start a timer for a specific operation."""
        with self.lock:
            self.timers[name] = time.perf_counter()
        
    def stop_timer(self, name, metric_name=None):
        """Stop a timer and record the duration."""
        with self.lock:
            if name not in self.timers:
                return 0
                
            start_time = self.timers.pop(name)
            duration = (time.perf_counter() - start_time) * 1000 # Convert to ms
            
            if metric_name:
                self.history[metric_name].append(duration)
                    
            return duration
        
    def record_hit(self, exact=False):
        """Record a cache hit."""
        with self.lock:
            self.metrics['cache_hits'] += 1
            if exact:
                self.metrics['exact_hits'] += 1
            
    def record_miss(self):
        """Record a cache miss."""
        with self.lock:
            self.metrics['cache_misses'] += 1
        
    def record_api_call(self, success=True):
        """Record an API call."""
        with self.lock:
            self.metrics['api_calls'] += 1
            if not success:
                self.metrics['api_errors'] += 1
            
    def record_hallucination(self):
        """Record a detected hallucination."""
        with self.lock:
            self.metrics['hallucinations_detected'] += 1
        
    def get_report(self):
        """Generate a summary report of performance metrics."""
        report = []
        report.append("--- Kaia Performance Report ---")
        
        total_cache = self.metrics['cache_hits'] + self.metrics['cache_misses']
        hit_rate = (self.metrics['cache_hits'] / total_cache * 100) if total_cache > 0 else 0
        
        report.append(f"Cache Hits: {self.metrics['cache_hits']} ({hit_rate:.1f}%)")
        report.append(f"Cache Misses: {self.metrics['cache_misses']}")
        report.append(f"Exact Hits: {self.metrics['exact_hits']}")
        
        report.append(f"Ollama API Calls: {self.metrics['api_calls']} (Errors: {self.metrics['api_errors']})")
        report.append(f"Hallucinations Blocked: {self.metrics['hallucinations_detected']}")
        
        # Add timing averages
        with self.lock:
            for metric, times in self.history.items():
                if times:
                    avg = sum(times) / len(times)
                    report.append(f"Avg {metric.replace('_', ' ').title()}: {avg:.2f}ms")
                
        return "\n".join(report)
