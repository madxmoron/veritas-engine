"""Quick-start GRPO training for Gemma 4 12B on A2AJ pairs."""
import json, torch, os, sys
from pathlib import Path

import unsloth
from unsloth import FastLanguageModel, is_bfloat16_supported
from datasets import Dataset

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.veritas.training.gemma_grpo import (
    format_reward, contradiction_reward, grounding_reward,
    format_dataset_for_grpo, LEGAL_SYSTEM_PROMPT,
)

# Config
MODEL_SNAPSHOT = str(Path.home() / '.cache/huggingface/hub/models--google--gemma-4-12B-it/snapshots/5926caa4ec0cac5cbfadaf4077420520de1d5205')
DATA_PATH = 'data/grpo_pairs.jsonl'
OUTPUT_DIR = 'models/gemma-4-12b-grpo-legal'
MAX_PAIRS = None  # Set to eg 5000 for quick test, None for all

print(f'GPU: {torch.cuda.get_device_name(0)}')
print(f'Data: {DATA_PATH}')
print(f'Output: {OUTPUT_DIR}')

# Load data
with open(DATA_PATH) as f:
    examples = [json.loads(line) for line in f if line.strip()]

if MAX_PAIRS:
    examples = examples[:MAX_PAIRS]

print(f'Training pairs: {len(examples):,}')

# Format for GRPO
dataset = format_dataset_for_grpo(examples)
print(f'Dataset ready: {len(dataset)} prompts')

# Load model
print('Loading model...')
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_SNAPSHOT,
    max_seq_length=2048, load_in_4bit=True,
    fast_inference=False, max_lora_rank=64, gpu_memory_utilization=0.85,
)
model = FastLanguageModel.get_peft_model(
    model, r=64,
    target_modules=['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],
    lora_alpha=16, lora_dropout=0, bias='none',
    use_gradient_checkpointing='unsloth', random_state=3407,
)

vram = torch.cuda.memory_allocated()/1e9
print(f'VRAM: {vram:.1f} GB')

# GRPO Config
from trl import GRPOConfig, GRPOTrainer

training_args = GRPOConfig(
    output_dir=OUTPUT_DIR,
    learning_rate=5e-6,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=4,
    num_train_epochs=1,
    num_generations=4,
    max_completion_length=1024,
    bf16=is_bfloat16_supported(),
    fp16=not is_bfloat16_supported(),
    logging_steps=10,
    save_steps=500,
    save_total_limit=2,
    report_to='none',
    remove_unused_columns=False,
    gradient_checkpointing=True,
)

# Trainer
trainer = GRPOTrainer(
    model=model,
    processing_class=tokenizer,
    args=training_args,
    train_dataset=dataset,
    reward_funcs=[format_reward, contradiction_reward, grounding_reward],
)

print(f'\n=== STARTING GRPO TRAINING ===')
print(f'Examples: {len(dataset):,}')
print(f'Gen per prompt: 4')
print(f'Max completion: 1024 tokens')
print(f'Epochs: 1')
print(f'Effective batch: {training_args.per_device_train_batch_size * training_args.gradient_accumulation_steps}')
print()

trainer.train()

# Save
print(f'\nSaving to {OUTPUT_DIR}...')
model.save_pretrained(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print('Done!')
