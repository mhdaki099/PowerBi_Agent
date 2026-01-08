# 🚀 Quick Test Commands

## Start the App
```bash
streamlit run app.py
```

## Test Growth vs Decline Fix

### Test 1: Growth Question
```
Question: "Why is OBG growing in 2025 vs 2024?"
Expected: Shows GROWING items (sorted DESC)
```

### Test 2: Decline Question
```
Question: "Why is DUP declining in 2025 vs 2024?"
Expected: Shows DECLINING items (sorted ASC)
```

### Test 3: Neutral Question
```
Question: "Compare OBG 2024 vs 2025"
Expected: Shows comprehensive analysis
```

## Run Automated Tests

### Test Focus Detection (100% accuracy)
```bash
python test_focus_detection.py
```
Expected: `11 passed, 0 failed`

### Test Enhanced Analytics
```bash
python test_enhanced_analytics.py
```
Expected: Coverage, OOS, Pattern tests pass

### Test Intent Detection
```bash
python test_intent_detection.py
```
Expected: All intents detected correctly

### Quick Database Check
```bash
python quick_test.py
```
Expected: Shows 2.38M records, 150 brands

## Verify App Import
```bash
python -c "import app; print('✅ Success')"
```
Expected: `✅ Success`

## Example Questions to Try

### Growth Questions:
1. "Why is OBG growing in 2025 vs 2024?"
2. "What's driving OBG growth?"
3. "Show me growing items for OBG"

### Decline Questions:
1. "Why is DUP declining in 2025 vs 2024?"
2. "What are the non-growing items for DUP?"
3. "Show me declining items for DUP"

### Coverage Questions:
1. "What is DUP brand coverage in the last 12 months?"
2. "Which accounts stopped buying DUP?"

### OOS Questions:
1. "Which DUP items had no sales in the last 30 days?"
2. "Supply chain issues for DUP brand"

### Pattern Questions:
1. "Which DUP items show seasonality?"
2. "Show me seasonal items for DUP"

## Expected Results

### ✅ Growth Question Result:
- Title: "📈 Top Items Contributing to Growth"
- Data: Items sorted by highest growth first
- Charts: Green color scheme
- AI: "Focus on what's DRIVING GROWTH"

### ✅ Decline Question Result:
- Title: "📉 Top Items Contributing to Decline"
- Data: Items sorted by highest decline first
- Charts: Red color scheme
- AI: "Focus on what's CAUSING DECLINE"

## Troubleshooting

### If app won't start:
```bash
pip install -r requirements.txt
```

### If database not found:
```bash
python create_database.py
```

### If tests fail:
```bash
python -c "import app; print('Import OK')"
```

## Status Check

Run all tests:
```bash
python test_focus_detection.py && echo "✅ Focus detection OK" && python -c "import app; print('✅ App import OK')"
```

Expected output:
```
Results: 11 passed, 0 failed
✅ Focus detection OK
✅ App import OK
```

## Quick Verification Checklist

- [ ] App starts: `streamlit run app.py`
- [ ] Growth question shows growing items
- [ ] Decline question shows declining items
- [ ] Focus detection: 11/11 tests pass
- [ ] App imports without errors
- [ ] Database has 2.38M records

## All Systems GO! 🚀

If all checks pass, your AI agent is fully operational and ready to use!
