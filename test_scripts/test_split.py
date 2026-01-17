import torch
from diffusers import FluxPipeline
from transformers import BitsAndBytesConfig
import gc
from dotenv import load_dotenv

load_dotenv()

def test_split():
    print("Testing Split Pipeline...")
    model_id = "black-forest-labs/FLUX.1-schnell"
    
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True
    )

    # 1. Load Encoders Only
    print("Loading Encoders...")
    try:
        pipe_enc = FluxPipeline.from_pretrained(
            model_id,
            transformer=None,
            vae=None,
            torch_dtype=torch.bfloat16,
        )
        # We need to manually quantize T5 if we want to save space, 
        # but here we just want to see if it loads without transformer.
        # Actually, if we don't quantize T5, it's 9GB. 
        # So we MUST quantize T5 here too for the test to be realistic on 12GB?
        # But for now, let's just check if it errors on init.
        print("Encoders loaded successfully.")
        
        print("Encoding prompt...")
        prompt = "test prompt"
        # encode_prompt returns prompt_embeds, pooled_prompt_embeds
        embeds = pipe_enc.encode_prompt(prompt, prompt_2=prompt)
        print("Encoding successful.")
        
        del pipe_enc
        gc.collect()
        torch.cuda.empty_cache()
        print("Encoders unloaded.")
        
    except Exception as e:
        print(f"Encoder load failed: {e}")
        return

    # 2. Load Transformer Only
    print("Loading Transformer...")
    try:
        # We pass text_encoder=None, etc.
        pipe_gen = FluxPipeline.from_pretrained(
            model_id,
            text_encoder=None,
            text_encoder_2=None,
            tokenizer=None,
            tokenizer_2=None,
            quantization_config=quant_config, # This quantizes transformer
            torch_dtype=torch.bfloat16
        )
        print("Transformer loaded successfully.")
        
        # Try to generate (dry run)
        # We need to pass embeds
        print("Generating (dry run)...")
        # pipe_gen(prompt_embeds=..., pooled_prompt_embeds=..., num_inference_steps=1)
        print("Generation call would go here.")
        
    except Exception as e:
        print(f"Transformer load failed: {e}")

if __name__ == "__main__":
    test_split()
