import sys
import os
import time

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.kaia_intelligence import PerformanceMonitor
from utils.kaia_logger import log_success, log_info, log_error

def test_performance_monitor_fix():
    log_info("--- Testing PerformanceMonitor Fix ---")
    monitor = PerformanceMonitor()
    
    # Test 1: Existing metric (cache_lookup_time)
    log_info("Test 1: Testing existing metric 'cache_lookup_time'")
    monitor.start_timer('test1')
    time.sleep(0.01)
    duration = monitor.stop_timer('test1', 'cache_lookup_time')
    
    if 'cache_lookup_time' in monitor.metrics and len(monitor.metrics['cache_lookup_time']) == 1:
        log_success(f"Test 1 passed: duration={duration:.2f}ms")
    else:
        log_error("Test 1 failed: 'cache_lookup_time' not found or empty")
        return False

    # Test 2: New (uninitialized) metric
    log_info("Test 2: Testing new (uninitialized) metric 'new_metric'")
    monitor.start_timer('test2')
    time.sleep(0.01)
    duration = monitor.stop_timer('test2', 'new_metric')
    
    if 'new_metric' in monitor.metrics and len(monitor.metrics['new_metric']) == 1:
        log_success(f"Test 2 passed: duration={duration:.2f}ms")
    else:
        log_error("Test 2 failed: 'new_metric' not found or empty")
        return False

    # Test 3: Report generation
    log_info("Test 3: Testing report generation")
    report = monitor.get_report()
    log_info(f"Report output:\n{report}")
    
    if "Avg Cache Lookup:" in report:
        log_success("Test 3 passed: Report contains 'Avg Cache Lookup'")
    else:
        log_error("Test 3 failed: Report missing 'Avg Cache Lookup'")
        return False

    return True

if __name__ == "__main__":
    if test_performance_monitor_fix():
        log_success("\nAll PerformanceMonitor tests passed!")
    else:
        log_error("\nSome PerformanceMonitor tests failed!")
        sys.exit(1)
