"""Test focus detection for growth vs decline questions"""
from app import detect_growth_or_decline_focus

test_questions = [
    ("give me the reason why OBG is Growing in 2025 vs 2024", "growing"),
    ("Why is DUP declining in 2025?", "declining"),
    ("What are the non-growing items for DUP?", "declining"),
    ("Show me growing items for OBG", "growing"),
    ("Which items are increasing for DUP?", "growing"),
    ("What's causing the drop in sales?", "declining"),
    ("Why is OBG brand growth improving?", "growing"),
    ("Explain the decline for DUP", "declining"),
    ("Show me items with positive growth", "growing"),
    ("Which products are underperforming?", "declining"),
    ("Compare OBG 2024 vs 2025", "all"),  # Should be 'all' - no clear focus
]

print("🧪 Testing Focus Detection (Growth vs Decline)\n")
print("=" * 80)

passed = 0
failed = 0

for question, expected in test_questions:
    result = detect_growth_or_decline_focus(question)
    status = "✅ PASS" if result == expected else "❌ FAIL"
    
    if result == expected:
        passed += 1
    else:
        failed += 1
    
    print(f"\n{status}")
    print(f"Question: {question}")
    print(f"Expected: {expected:10} | Got: {result:10}")

print("\n" + "=" * 80)
print(f"Results: {passed} passed, {failed} failed out of {len(test_questions)} tests")
print("=" * 80)
