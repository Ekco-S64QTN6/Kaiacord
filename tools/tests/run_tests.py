#!/usr/bin/env python3
"""
Run all tests with summary report.
"""
import subprocess
import sys

def run_tests():
    """Run all test suites and generate summary"""
    print("=" * 60)
    print("KAIACORD TEST SUITE")
    print("=" * 60)
    
    test_suites = [
        ("Unit Tests", "tests/unit/"),
        ("Integration Tests", "tests/integration/"),
    ]
    
    results = {}
    
    for name, path in test_suites:
        print(f"\n🔍 Running {name}...")
        print("-" * 60)
        
        result = subprocess.run(
            [sys.executable, "-m", "pytest", path, "-v", "--tb=short"],
            capture_output=False
        )
        
        results[name] = result.returncode == 0
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    sys.exit(run_tests())
