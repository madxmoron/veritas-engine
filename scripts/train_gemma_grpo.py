"""
Train Gemma 4 12B with GRPO self-scaffolding for legal verification.

Usage:
    python scripts/train_gemma_grpo.py --data_path data/training_pairs.jsonl

Hardware: RTX 3090 (24GB) — Unsloth QLoRA 4-bit.
Expected training time: 4-12 hours for 10K-50K examples.

Based on blueprint Section 7.2, Gemma 4 12B subsection.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import torch
from datasets import Dataset
from transformers import TrainingArguments

# Unsloth MUST be imported first
import unsloth
from unsloth import FastLanguageModel, is_bfloat16_supported

from veritas.training.gemma_grpo import (
    format_reward,
    contradiction_reward,
    grounding_reward,
    format_dataset_for_grpo,
    LEGAL_SYSTEM_PROMPT,
)


def load_model():
    """Load Gemma 4 12B in 4-bit with Unsloth."""
    model_name = "google/gemma-4-12B-it"
    max_seq_length = 2048  # Legal texts don't need extreme context for training

    print(f"Loading {model_name} in 4-bit...")

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        load_in_4bit=True,
        fast_inference=False,  # Training mode
        max_lora_rank=64,
        gpu_memory_utilization=0.85,
        trust_remote_code=True,
    )

    # LoRA config for GRPO
    model = FastLanguageModel.get_peft_model(
        model,
        r=64,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    return model, tokenizer


def load_training_data(data_path: str):
    """Load training pairs from JSONL or HuggingFace dataset."""
    path = Path(data_path)

    if not path.exists():
        raise FileNotFoundError(f"Training data not found: {data_path}")

    with open(path) as f:
        examples = [json.loads(line) for line in f if line.strip()]

    print(f"Loaded {len(examples)} training examples")

    dataset = format_dataset_for_grpo(examples)
    return dataset


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_path", required=True, help="Path to training pairs JSONL")
    parser.add_argument("--output_dir", default="models/gemma-4-12b-grpo-legal",
                        help="Where to save the trained LoRA adapter")
    parser.add_argument("--num_generations", type=int, default=4,
                        help="Number of completions per prompt (GRPO group size)")
    parser.add_argument("--max_completion_length", type=int, default=1024,
                        help="Max tokens for completions")
    parser.add_argument("--learning_rate", type=float, default=5e-6,
                        help="Learning rate for GRPO")
    parser.add_argument("--num_train_epochs", type=int, default=1,
                        help="Number of training epochs")
    parser.add_argument("--per_device_train_batch_size", type=int, default=1,
                        help="Batch size per GPU")
    parser.add_argument("--gradient_accumulation_steps", type=int, default=4,
                        help="Gradient accumulation steps")
    parser.add_argument("--dry_run", action="store_true",
                        help="Validate setup without training")
    args = parser.parse_args()

    # Check GPU
    if not torch.cuda.is_available():
        print("ERROR: CUDA not available. This training requires a GPU.")
        sys.exit(1)

    gpu_name = torch.cuda.get_device_name(0)
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"GPU: {gpu_name} ({vram_gb:.1f} GB)")
    print(f"PyTorch: {torch.__version__}, Unsloth: {unsloth.__version__}")

    # Load model
    model, tokenizer = load_model()

    # Print trainable params
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable: {trainable:,} / Total: {total:,} ({100*trainable/total:.1f}%)")

    if args.dry_run:
        print("\n[Dry run] Testing reward functions...")
        test_completions = [
            "<verification_plan>\nCheck citation 2020 ONCA 123\n</verification_plan>\n"
            "<cross_examination>\nCitation found in CanLII. Text matches source exactly.\n"
            "No conflicts detected.\n</cross_examination>\n"
            "<calibrated_output>\nVERIFIED\nsource_id: 2020 ONCA 123\n"
            "exact_text: The court held that...\n</calibrated_output>",
        ]
        fmt = format_reward(completions=test_completions)
        con = contradiction_reward(completions=test_completions)
        grd = grounding_reward(completions=test_completions)
        print(f"  Format reward: {fmt}")
        print(f"  Contradiction reward: {con}")
        print(f"  Grounding reward: {grd}")
        print("Reward functions OK.\n")
        return

    # Load data
    dataset = load_training_data(args.data_path)

    # Import TRL (may need mergekit installed)
    try:
        from trl import GRPOConfig, GRPOTrainer
    except RuntimeError as e:
        print(f"\nERROR importing TRL: {e}")
        print("Try: pip install mergekit")
        print("Then re-run.")
        sys.exit(1)

    # GRPO config
    training_args = GRPOConfig(
        output_dir=args.output_dir,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_train_epochs=args.num_train_epochs,
        num_generations=args.num_generations,
        max_completion_length=args.max_completion_length,
        bf16=is_bfloat16_supported(),
        fp16=not is_bfloat16_supported(),
        logging_steps=10,
        save_steps=500,
        save_total_limit=3,
        report_to="none",  # Set to "wandb" if you want experiment tracking
        remove_unused_columns=False,
        gradient_checkpointing=True,
        dataloader_num_workers=0,  # Windows: 0 workers is more stable
    )

    # Trainer
    trainer = GRPOTrainer(
        model=model,
        processing_class=tokenizer,
        args=training_args,
        train_dataset=dataset,
        reward_funcs=[
            format_reward,
            contradiction_reward,
            grounding_reward,
        ],
    )

    print(f"\nStarting GRPO training...")
    print(f"  Examples: {len(dataset)}")
    print(f"  Generations per prompt: {args.num_generations}")
    print(f"  Max completion length: {args.max_completion_length}")
    print(f"  Epochs: {args.num_train_epochs}")
    print(f"  Output: {args.output_dir}")

    trainer.train()

    # Save final adapter
    print(f"\nSaving LoRA adapter to {args.output_dir}")
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    # Save merged model (optional, larger)
    print("Saving merged model...")
    model.save_pretrained_merged(
        f"{args.output_dir}_merged",
        tokenizer,
        save_method="merged_16bit",
    )

    print("\nTraining complete!")
    print(f"LoRA adapter: {args.output_dir}")
    print(f"Merged model: {args.output_dir}_merged")


if __name__ == "__main__":
    main()
