"""Test intent detection for enhanced analytics"""
from app import detect_enhanced_analytics_intent

test_questions = [
    "What is DUP brand coverage in the last 12 months?",
    "Which accounts stopped buying DUP?",
    "Which DUP items had no sales in the last 30 days?",
    "Show me seasonal items for DUP",
    "Supply chain issues for DUP brand",
    "What are the non-growing items for DUP?",  # Should NOT trigger enhanced
]

print("🧪 Testing Intent Detection\n")
print("=" * 80)

for question in test_questions:
    result = detect_enhanced_analytics_intent(question)
    enhanced = "✅ ENHANCED" if result['needs_enhanced'] else "❌ REGULAR"
    intent_type = result['type'] if result['type'] else "N/A"
    print(f"\n{enhanced} | Type: {intent_type:15} | Q: {question}")

print("\n" + "=" * 80)
print("✅ All intent detection tests completed!")
