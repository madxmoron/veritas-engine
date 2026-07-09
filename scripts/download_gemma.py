"""Download and test-load Gemma 4 12B in 4-bit on RTX 3090."""
import torch
import os

MODEL_ID = "google/gemma-4-12B-it"
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "gemma-4-12b-it-q4")

def main():
    print(f"PyTorch {torch.__version__} | CUDA {torch.version.cuda}")
    print(f"GPU: {torch.cuda.get_device_name(0)} ({torch.cuda.get_device_properties(0).total_memory/1e9:.1f} GB)")
    
    # Need to authenticate with HF for gated models
    from huggingface_hub import login
    try:
        # Check if already logged in
        from huggingface_hub import whoami
        whoami()
        print("HF: Authenticated")
    except Exception:
        print("HF: Not authenticated. Run `huggingface-cli login` first.")
        return

    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
    )
    
    print(f"\nDownloading {MODEL_ID}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=quant_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )
    
    # Report VRAM
    vram_used = torch.cuda.memory_allocated() / 1e9
    vram_reserved = torch.cuda.memory_reserved() / 1e9
    print(f"\nModel loaded: {vram_used:.1f} GB allocated, {vram_reserved:.1f} GB reserved")
    print(f"Free: {(torch.cuda.get_device_properties(0).total_memory/1e9 - vram_reserved):.1f} GB")
    
    # Quick inference test
    prompt = "In Canadian law, the principle of stare decisis means that"
    print(f"\nTest prompt: '{prompt}'")
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda")
    
    with torch.no_grad():
        outputs = model(**inputs, output_hidden_states=True, return_dict=True)
    
    # Token probabilities (logprobs at last position)
    logits = outputs.logits[0, -1, :]
    probs = torch.softmax(logits, dim=-1)
    top5 = torch.topk(probs, 5)
    
    print("\nTop-5 next token predictions:")
    for i in range(5):
        tok = tokenizer.decode(top5.indices[i])
        print(f"  {tok!r}: {top5.values[i].item():.4f}")
    
    # Generate a small sample
    print("\n--- Generation test ---")
    with torch.no_grad():
        generated = model.generate(
            **inputs,
            max_new_tokens=50,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
        )
    response = tokenizer.decode(generated[0], skip_special_tokens=True)
    print(response)
    
    print("\n✓ Gemma 4 12B loaded and working in 4-bit")

if __name__ == "__main__":
    main()
