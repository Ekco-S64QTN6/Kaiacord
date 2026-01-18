# Testing Guide for Kaia Improvements

## Quick Test Commands

### 1. Image Generation (Both formats should work now)
```
kaia, draw a cat sitting on a keyboard
kaia draw a sunset over mountains
kaia  draw a hacker in a dark room (multiple spaces)
```

### 2. Quip System Monitoring
Watch the console output for:
- `Generating idle quip #1 (Idle: Xm)...` 
- Max should be `#3` before stopping
- Should reset to `#1` after user interaction

### 3. Check Kaia's Own Logs
```bash
# After a few quips, check if Kaia logged her own quips
ls -la /home/ekco/github/Kaiacord/knowledge_base/user_logs/
# Look for a directory with Kaia's user ID
# Inside should be logs with [IDLE_QUIP: topic] entries
```

## Expected Behavior Changes

### Before → After Comparison

| Aspect | Before | After |
|--------|--------|-------|
| **Image command** | Only "kaia, draw" | "kaia, draw" OR "kaia draw" |
| **Quip frequency** | 8 in 4 hours | ~1-2 per hour max |
| **Consecutive quips** | No limit | Max 3 |
| **Quip length** | 1 sentence | 2-4 sentences |
| **Quip variety** | Very repetitive | 8 topic categories |
| **Quip logging** | Not logged | Logged to Kaia's user log |
| **CUDA OOM** | Frequent failures | Should be resolved |

## Monitoring Commands

### GPU Memory Usage
```bash
# Watch GPU memory in real-time
watch -n 1 nvidia-smi

# Expected: ~10GB max usage during image generation
```

### Check Logs
```bash
# Monitor Kaia's output
tail -f /path/to/kaia/logs  # or wherever you're logging

# Look for:
# - "Step 1/2: Loading encoders..."
# - "Step 2/2: Loading transformer..."
# - "Generating idle quip #X (Idle: Ym)..."
# - "Max consecutive quips (3) reached..."
```

### Check Quip Logs
```bash
# Find Kaia's user ID directory
find /home/ekco/github/Kaiacord/knowledge_base/user_logs/ -name "Kaia_*"

# Check the log file inside
cat /home/ekco/github/Kaiacord/knowledge_base/user_logs/Kaia_*/interactions.log
```

## Troubleshooting

### If CUDA OOM still occurs:
1. Check `nvidia-smi` before generation - is something else using VRAM?
2. Try lowering `torch.cuda.set_per_process_memory_fraction(0.86)` to `0.80` in `kaia_image.py`
3. Verify Ollama models are being unloaded (check logs)

### If image command doesn't work:
1. Verify the regex pattern is matching: check console for "Generating image for prompt: X"
2. Try with comma first: "kaia, draw test"
3. Check for typos or special characters

### If quips are still too frequent:
1. Lower the probabilities in `idle_quip_task`:
   - Change `0.15` to `0.10` (30-60 min)
   - Change `0.25` to `0.15` (60-120 min)
   - Change `0.40` to `0.25` (120+ min)

### If quips are still repetitive:
1. Increase `temperature` to `1.0` or `1.1`
2. Increase `repeat_penalty` to `1.3`
3. Add more topics to the `topics` list

## Timeline for Testing

**Hour 0-1**:
- Test image generation with both command formats
- Verify CUDA memory usage stays under 10GB

**Hour 1-3**:
- Monitor quip frequency (should see 1-2 quips max)
- Check quip variety (different topics, 2-4 sentences)
- Verify consecutive quips stop at 3

**Hour 3+**:
- Interact with Kaia to reset quip counter
- Verify quip counter resets
- Check Kaia's user logs for quip entries
