#!/usr/bin/env python3
"""Test script to verify ALL CAPS pronunciation fix for Chatterbox Turbo."""

import sys
from pathlib import Path

# Add parent directory to path to import audiblez
sys.path.insert(0, str(Path(__file__).parent))

from audiblez.core import ChatterboxPipelineWrapper


def test_clean_text_for_tts():
    """Test the _clean_text_for_tts method with various text cases."""

    wrapper = ChatterboxPipelineWrapper()

    test_cases = [
        # (input, expected_output, description)
        ("THIS IS ALL CAPS TEXT", "This Is All Caps Text", "ALL CAPS text"),
        ("This is normal case text", "This is normal case text", "Normal case text"),
        (
            "This Has SOME all caps WORDS",
            "This Has SOME all caps WORDS",
            "Mixed case text",
        ),
        (
            '"THIS IS A QUOTED ALL CAPS SENTENCE"',
            "This Is A Quoted All Caps Sentence",
            "ALL CAPS with quotes",
        ),
        ("HELLO, WORLD!", "Hello, World!", "ALL CAPS with punctuation"),
        ("hello world", "hello world", "All lowercase (should not be changed)"),
        (
            "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG",
            "The Quick Brown Fox Jumps Over The Lazy Dog",
            "Long ALL CAPS sentence",
        ),
    ]

    print("Testing _clean_text_for_tts method:")
    print("=" * 80)

    all_passed = True
    for input_text, expected, description in test_cases:
        result = wrapper._clean_text_for_tts(input_text)
        passed = result == expected
        all_passed = all_passed and passed

        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"\n{status} - {description}")
        print(f"  Input:    {input_text!r}")
        print(f"  Expected: {expected!r}")
        print(f"  Got:      {result!r}")

        if not passed:
            print(f"  ERROR: Output doesn't match expected!")

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed!")

    return all_passed


if __name__ == "__main__":
    success = test_clean_text_for_tts()
    sys.exit(0 if success else 1)
