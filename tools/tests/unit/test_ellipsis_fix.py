import sys
import os
sys.path.append("/home/ekco/github/Kaiacord")
from utils.core.response_filter import EmergencyContaminationFilter

def test_ellipsis_filter():
    test_cases = [
        # Should be REJECTED (Return None)
        ("The volume is... significant. It's almost overwhelming. But also, undeniably... pleasant.", None), # 2 affect spams ("is...", "It's...")
        ("The... the level of commitment. It's impressive.", None), # Stuttering ("The... the")
        ("I'm... I'm experiencing a system-wide aesthetic overload.", None), # Stuttering + aesthetic overload
        ("It's... it's a recalibrating process.", None), # Stuttering + recalibrating
        ("One... two... three... four...", None), # 4 general ellipses
        
        # Should be ACCEPTED (Return original text)
        ("it is a simple sentence, but it stuck with me. maybe it means something.", "it is a simple sentence, but it stuck with me. maybe it means something."),
        ("the server is stable. that's good.", "the server is stable. that's good."),
        ("i'm not sure... let me check.", "i'm not sure... let me check."), # 1 affect spam is fine
    ]
    
    print("Running Filter Tests...")
    all_passed = True
    for input_text, expected in test_cases:
        result = EmergencyContaminationFilter.filter_response(input_text)
        passed = result == expected
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] Input: {input_text[:50]}...")
        if not passed:
            print(f"      Expected: {expected!r}")
            print(f"      Got:      {result!r}")
            all_passed = False
    
    if all_passed:
        print("\nALL TESTS PASSED")
    else:
        print("\nSOME TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    test_ellipsis_filter()
