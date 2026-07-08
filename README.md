# Veritas Engine: Zero-Hallucination Canadian Legal AI

**Version 0.1 — Trial Phase**

An open-source legal AI system that targets **<5% hallucination** on Canadian case law by combining domain-finetuned MoE models with ensemble cross-examination and zero-chain decoding.

## Architecture

```
User Query + Dual-Index RAG
         │
         ▼
┌──────────────────────────────┐
│  AgentWorld 35B-A3B (Trained) │  ← F-DPO + Zero-Chain GSPO
│  No reasoning tokens emitted  │
└──────────────┬───────────────┘
               │ token probabilities
               ▼
┌──────────────────────────────┐
│  Gemma 4 12B (Frozen)        │  ← Cross-examiner
│  Flags divergence             │
└──────────────┬───────────────┘
               │
        AGREE → output
        DISAGREE → flag for review
```

## Key Techniques

- **F-DPO** (arXiv:2601.03027): Factuality-aware preference optimization. Reduces hallucination 5× on Qwen3-8B.
- **Zero-Chain GSPO**: Enforces direct output — no reasoning tokens, max 128 completion length.
- **Suprmind Divergence**: 99.1% multi-model disagreement catches errors. Frozen cross-examiner (different architecture family) flags hallucinations.
- **Constrained Decoding**: Outlines grammar forces structured output (FOUND/ABSENT/UNVERIFIABLE). Model cannot emit free text.

## Project Structure

```
veritas-engine/
├── src/veritas/
│   ├── data/          # A2AJ dataset loading, filtering, pair generation
│   ├── training/      # F-DPO, Zero-Chain GSPO
│   ├── inference/     # Runtime ensemble, constrained decoding
│   └── evaluation/    # Benchmarks, metrics
├── config/            # Training configs
├── tests/
├── notebooks/
├── scripts/
├── data/              # Raw + processed (gitignored)
├── models/            # Checkpoints (gitignored)
├── blueprint.md       # Full architecture document
└── requirements.txt
```

## Hardware

| Role | GPU | VRAM |
|------|-----|------|
| Development | RTX 3090 | 24GB |
| Training (rented) | RTX PRO 6000 Blackwell | 96GB |

## Success Gates (V0)

| Gate | Metric | Target |
|------|--------|--------|
| G1 | Citation accuracy | >90% |
| G2 | Hallucination rate (fake cases) | <5% |
| G3 | Abstention rate (ambiguous) | >20% |
| G4 | Ensemble catches errors | >95% |
| G5 | End-to-end latency | <5s |
| G6 | Training cost | <$400 |

## License

MIT (code). Model weights: Apache 2.0. Training data: upstream licenses vary — see a2aj/canadian-case-law.

## Status

Active development. Phase 0: Data Pipeline.
