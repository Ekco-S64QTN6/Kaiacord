# Kaia Vision Feature - Image Analysis

## Overview

Kaia can now "see" and analyze images uploaded to Discord! She uses the **llama3.2-vision:11b** model running locally via Ollama to provide commentary on images in her characteristic blunt, grounded style.

---

## Features

### What Kaia Can Do

1. **Describe Images**: Detailed descriptions of objects, people, actions, and settings
2. **Read Text**: Identify and read visible text in images
3. **Provide Commentary**: Give blunt, Kaia-style observations about images
4. **Answer Questions**: Respond to specific queries about image content

---

## How to Use

### Basic Usage

Simply upload an image and mention "kaia" in your message:

```
kaia [upload image]
kaia what's in this image?
kaia describe this
kaia look at this
```

### Example Conversations

**Example 1: Simple Description**
```
User: kaia [uploads photo of a cat]
Kaia: looking...
Kaia: black and white cat sitting on a mechanical keyboard. 
      looks like it's judging your typing speed. probably is.
```

**Example 2: Specific Question**
```
User: kaia what objects are in this image? [uploads photo]
Kaia: looking...
Kaia: laptop, coffee mug (looks like it's been there a while), 
      stack of books, desk lamp. standard late-night setup.
```

**Example 3: Text Reading**
```
User: kaia what does the sign say? [uploads photo of sign]
Kaia: looking...
Kaia: says "no parking 8am-6pm weekdays". someone's getting towed.
```

---

## Supported Image Formats

- PNG (`.png`)
- JPEG (`.jpg`, `.jpeg`)
- GIF (`.gif`)
- WebP (`.webp`)

---

## Technical Details

### Architecture

1. **Image Detection**: Discord bot detects image attachments
2. **Download**: Image is downloaded from Discord CDN to temporary file
3. **Vision Analysis**: Ollama's llama3.2-vision model analyzes the image
4. **Response**: Kaia provides commentary in her voice
5. **Cleanup**: Temporary file is deleted
6. **Logging**: Interaction is logged to user's log with `[IMAGE: filename]` tag

### Files

- **`kaia_vision.py`**: Vision module handling image download and analysis
- **`Kaiacord.py`**: Discord bot integration (image detection and handling)

### Vision Model

- **Model**: `llama3.2-vision:11b`
- **Size**: ~7.8 GB
- **Provider**: Ollama (local)
- **Capabilities**: 
  - Object detection and recognition
  - Scene understanding
  - Text recognition (OCR)
  - Spatial reasoning
  - Action detection

---

## Response Modes

### Mode 1: User Asks Questions
When the message contains words like "describe", "what", "see", "look":

```python
prompt = "Describe what you see in this image. 
          Be direct and specific. No fluff."
```

**Result**: Detailed 3-5 sentence description

### Mode 2: User Just Uploads
When user uploads without specific questions:

```python
prompt = "Give a brief, blunt observation about this image. 
          1-2 sentences. Be direct and grounded."
```

**Result**: Short 1-2 sentence commentary

---

## Memory Integration

All vision interactions are logged to the user's log:

```
Message: "kaia what's in this? [IMAGE: screenshot.png]"
Response: "code editor with a bunch of errors. looks like 
           someone's debugging session went south..."
```

This feeds into Kaia's RAG system for persistent memory.

---

## Performance

### Timing (Approximate)
- **Image Download**: 0.5-2 seconds (depends on size/network)
- **Vision Analysis**: 5-15 seconds (depends on GPU/CPU)
- **Total**: ~5-20 seconds

### Resource Usage
- **VRAM**: ~4-6 GB (vision model)
- **RAM**: ~2-3 GB (image processing)
- **Disk**: Temporary files auto-deleted after analysis

---

## Error Handling

If vision fails, Kaia responds:
```
can't process that image. something broke.
```

Common causes:
- Vision model not loaded/available
- Image download failed
- Corrupted image file
- Out of memory

---

## Example Use Cases

### 1. Code Review
```
User: kaia what's wrong with this code? [uploads screenshot]
Kaia: variable shadowing on line 15. also that loop looks 
      like it's going to run forever. check your exit condition.
```

### 2. Meme Analysis
```
User: kaia [uploads meme]
Kaia: classic distracted boyfriend meme template. the labeling 
      is about javascript frameworks. accurate.
```

### 3. Hardware Troubleshooting
```
User: kaia why isn't this working? [uploads photo of circuit board]
Kaia: capacitor at the top right looks blown. the bulge is a dead 
      giveaway. replace it before you power this on again.
```

### 4. Screenshot Help
```
User: kaia what does this error mean? [uploads error screenshot]
Kaia: segmentation fault at address 0x0. null pointer dereference. 
      check your pointers before you dereference them.
```

---

## Configuration

### Change Vision Model

Edit `kaia_vision.py`:
```python
# Options:
# - llama3.2-vision:11b (default, 7.8 GB)
# - llama3.2-vision:90b (larger, more accurate, 55 GB)
# - llava:latest (older, 4.7 GB)

VISION_MODEL = "llama3.2-vision:11b"
```

### Adjust Response Style

Edit prompts in `kaia_vision.py` function `kaia_sees_image()`:
- Make more verbose: Increase sentences in prompt
- Make more brief: Decrease sentences in prompt
- Change tone: Modify descriptive language

---

## Limitations

1. **No video analysis** (yet)
2. **Single image per message** (processes first image only)
3. **No image comparison** (can't compare multiple images)
4. **Limited fine details** (model-dependent accuracy)
5. **No image generation from vision** (separate feature)

---

## Future Enhancements

Potential improvements:
- Multi-image analysis and comparison
- Video frame extraction and analysis
- Image-to-image generation based on vision input
- Vision-guided web search
- OCR extraction and text indexing for RAG

---

## Troubleshooting

### Vision model not found
```bash
# Install the vision model
ollama pull llama3.2-vision:11b
```

### Out of memory during vision
- Close other GPU applications
- Use smaller vision model: `llama3.2-vision:11b` instead of `90b`
- Ensure image generation (`kaia draw`) is not running simultaneously

### "looking..." but no response
- Check console for errors
- Verify vision model is loaded: `ollama list`
- Check if model is running: `ollama ps`

---

## Testing

### Quick Test
```
1. Upload any image to Discord
2. Message: "kaia describe this"
3. Wait for "looking..." then response
4. Verify response is relevant and in Kaia's voice
```

### Integration Test
```python
# Run from command line
cd /home/ekco/github/Kaiacord
./venv/bin/python kaia_vision.py
```

---

## Privacy & Security

- **Images are temporary**: Downloaded to temp directory and deleted after analysis
- **Local processing**: All analysis happens locally via Ollama
- **No external APIs**: Images are not sent to external services
- **Logging**: Image filenames (not content) are logged to user logs

---

## Performance Tips

1. **GPU Priority**: Vision uses GPU if available, falls back to CPU
2. **Memory Management**: Vision model loads on-demand and can coexist with text model
3. **Concurrent Requests**: Vision requests are processed sequentially (no parallel processing)
4. **Image Size**: Large images are handled by the model; no pre-processing needed
