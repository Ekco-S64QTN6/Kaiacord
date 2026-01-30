# Quick Reference - Kaia Vision Commands

## Basic Commands

### View/Describe Image
```
kaia [upload image]
kaia look at this [upload]
kaia describe this [upload]
kaia what do you see? [upload]
```

### Ask Specific Questions
```
kaia what objects are in this image? [upload]
kaia what is happening in this image? [upload]
kaia what does the text say? [upload]
kaia is there a cat in this picture? [upload]
```

### Get Brief Commentary
```
kaia [upload]  
# (just upload with "kaia" mention - she'll give a quick observation)
```

---

## Response Format

All vision responses are wrapped in code blocks:
```
looking...
[Kaia's analysis in her blunt, grounded style]
```

---

## Supported Formats
✅ PNG, JPEG, JPG, GIF, WebP

---

## Expected Response Time
⏱️ 5-20 seconds (depending on GPU/model)

---

## Common Uses

**Code Review**
```
kaia what's wrong with this code? [screenshot]
```

**Error Debugging**  
```
kaia what does this error mean? [screenshot]
```

**Meme Analysis**
```
kaia [meme upload]
```

**Hardware Troubleshooting**
```
kaia why isn't this working? [circuit board photo]
```

**Text Extraction**
```
kaia what does the sign say? [photo]
```

---

## Tips

- **Be specific**: "what objects" vs "describe" gives different detail levels
- **One image at a time**: Kaia processes the first image only
- **Include context**: Your message helps Kaia understand what you're asking
- **Wait for "looking..."**: Confirms Kaia is processing the image

---

## Troubleshooting

**No response?**
- Check if vision model is installed: `ollama list | grep vision`
- Verify file format is supported (PNG, JPG, etc.)

**"can't process that image"?**
- File may be corrupted
- Model may be out of memory
- Check console logs for details

**Too slow?**
- Normal for first use (model loading)
- Subsequent uses should be faster
- Large images take longer

---

## Integration with Other Features

### Works with RAG
Vision interactions are logged:
```
[IMAGE: screenshot.png] "lots of errors in that console..."
```
Kaia can reference past images in future conversations.

### Separate from Image Generation
- **Vision** (this): Kaia SEES images you upload
- **Generation** (`kaia draw`): Kaia CREATES images

---

## Model Info

**Current Model**: llama3.2-vision:11b  
**Size**: ~7.8 GB  
**Location**: Local (Ollama)  
**Privacy**: All processing happens locally
