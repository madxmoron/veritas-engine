# The Veritas Engine: Version 0 Trial Blueprint
## Zero-Hallucination Canadian Legal AI
### July 8, 2026 — Final Architecture

---

**Status:** Active Development
**Version:** 0.1 (Trial Phase)
**Next Milestone:** V0 working prototype → V1 production launch
**Verification:** All numerical claims cross-referenced. Known errors in original archive fixed below.

---

## ERRATA: Fixed From Original Archive

| Claim | Original | Corrected | Source |
|---|---|---|---|
| Harvey valuation | $3 billion | **$11 billion** (March 2026) | Harvey blog, TechCrunch, Forbes |
| RTX 6000 FP16 tensor (dense) | 503.8 TFLOPS | **251.90 TFLOPS** | WareDB, NVIDIA specs |
| RTX 6000 FP8 tensor (dense) | 1007.6 TFLOPS | **503.80 TFLOPS** | WareDB, NVIDIA specs |
| RTX 6000 FP16 sparse | Not specified separately | 503.80 TFLOPS | WareDB |
| RTX 6000 FP8 sparse | Not specified separately | 1007.61 TFLOPS | WareDB |
| Harvey 12.6% all-pass | Attributed to Harvey | Harvey LAB leaderboard shows **Claude Fable 5 at 14.2%** | Artificial Analysis |

---

# PART 1: CORE THESIS (VERIFIED)

## 1.1 The Reasoning Tax

Long reasoning chains increase hallucinations. Verified by:

- **arXiv:2509.06861** (USC/Meta AI, Sep 2025): "Test-Time Scaling in Reasoning Models Is Not Effective for Knowledge-Intensive Tasks Yet"
- **Vectara HHEM Leaderboard (April 2026)**: DeepSeek-R1 (reasoning model): 14.3% hallucination vs DeepSeek-V3 base: ~6.1%

Every reasoning step is a generation step with non-zero error probability. For legal work: one wrong citation = malpractice.

## 1.2 The Hallucination Ceiling

Legal AI has plateaued at 15-33% hallucination since 2024:

| Year | Models | Rate | Source |
|---|---|---|---|
| 2023 | General models (GPT-3.5 era) | 58-88% | Stanford "Large Legal Fictions", 800K+ queries |
| 2024 | Lexis+ AI, Westlaw AI | 17-33% | Stanford HAI, Magesh et al. |
| 2025 | Same tools, follow-up | ~same | Stanford follow-up |
| 2026 | Vincent AI (RAG-based) | Same as no AI | 127 law students, Feb 2026 |
| 2026 | Harvey LAB-AA (Claude Fable 5) | 14.2% all-pass | Artificial Analysis, May 2026 |

## 1.3 Vectara HHEM Rankings (April 2026)

| Model | Hallucination | Domain |
|---|---|---|
| antgroup/finix_s1_32b | **1.8%** | Fintech domain-finetuned |
| openai/gpt-5.4-nano | 3.1% | General (tiny) |
| google/gemma-3-12b-it | 4.4% | General |
| qwen/qwen3-8b | 4.8% | General |
| openai/gpt-5.5 | 9.3% | Frontier |
| zai-org/GLM-4.5-AIR-FP8 | 9.3% | Harvey's base |
| deepseek-ai/DeepSeek-R1 | **14.3%** | Reasoning model (worst) |

**Key insight**: Domain-finetuned models (finix 1.8%) beat general models. Reasoning models (R1 14.3%) are worse than bases.

---

# PART 2: BASE MODELS (OUR CHOICES)

## 2.1 Primary: Qwen AgentWorld 35B-A3B

**Model Card (verified from HuggingFace):**
- Type: Language World Model
- Base: Qwen3.5-35B-A3B-Base
- Training: CPT → SFT → RL (GSPO)
- Parameters: 35B total, 3B activated
- Layers: 40
- Architecture: 10 × (3 × Gated DeltaNet → MoE → 1 × Gated Attention → MoE)
- Experts: 256 total, 9 active per token (8 routed + 1 shared)
- Context: 262,144 tokens
- CPT domains include Law
- RL uses rule-based verifiers for exact correctness
- Apache 2.0, open weights
- Outperforms GPT-5.4 and Claude Opus 4.8 on agent benchmarks

**Why it fits the Veritas thesis:**
- World model: predicts environment outcomes before acting. This IS the "simulate CanLII retrieval outcome" capability.
- Rule-based verifiers in RL: already trained to output exact-correctness answers.
- Cross-domain generalization proven: zero-shot on 4K unseen OpenClaw environments.
- GSPO-native: uses sequence-level RL (not token-level GRPO), stabilizes MoE training.

**Critical finding: AgentWorld uses GSPO, not GRPO.**
- GRPO: token-level importance ratios. Unstable on MoE architectures.
- GSPO (arXiv:2507.18071): sequence-level ratios. Designed for MoE stability.
- Using GRPO on AgentWorld would conflict with its native GSPO training.
- **V0 approach: Use GSPO continuation for GRPO-like rewards, or use F-DPO (preference-based, no RL stability issues).**

## 2.2 Cross-Examiner: Gemma 4 12B (GRPO-Trained)

- Google DeepMind, Apache 2.0
- Dense 12B, fits RTX 3090 at Q4 (~6GB)
- Different architecture family from Qwen — ensures ensemble divergence
- 256K context, multimodal (text + audio + vision)
- BenchLM overall: 52, IFBench: 73.5

**Role in ensemble:** INDEPENDENTLY TRAINED — not frozen. Receives same GRPO self-scaffolding treatment with Ornith-style three-phase scaffold:
```
<verification_plan> → <cross_examination> → <calibrated_output>
```
Model generates explicit verification plan, cross-examines inputs against plan, outputs calibrated result. No zero-chain constraint — Gemma's role IS to think out loud so its reasoning is auditable.
- Format reward: +1.5 for correct tag sequence
- Contradiction reward: +2.0 for identifying conflicts
- Grounding reward: +1.0 for real statutory codes

**Why both models are trained:**
AgentWorld (Alibaba, MoE, 35B) and Gemma 4 (Google, dense, 12B) have completely different architectures, tokenizers, and pretraining data. They hallucinate different things. Both independently trained to verify — when they disagree, one of them is probably wrong. Suprmind principle: 99.1% multi-model divergence catches errors.

---

# PART 3: TECHNIQUES (VERIFIED PAPERS)

## 3.1 F-DPO: Factuality-Aware DPO
- arXiv:2601.03027, ACL 2026 Findings
- Vector Institute (Toronto) + U Cincinnati + U Calgary
- Adds factuality margin to DPO loss function
- Qwen3-8B: hallucination 0.424 → **0.084** (5x)
- Qwen2.5-14B: → **0.008** (near zero)
- Works on 7 models, 1B-14B, three model families
- No auxiliary reward model needed

## 3.2 RL's Razor: RL Forgets Less Than SFT
- "Retaining by Doing" (Princeton, arXiv:2510.18874): SFT average 54%, forgetting -10.4%. GRPO: 60%, forgetting -2.3%
- "RL's Razor" (MIT, arXiv:2509.04259): On-policy RL converges to KL-minimal solutions
- Implication: Further training AgentWorld (already RL-trained) preserves existing capabilities

## 3.3 Counterfactual Routing (ACL 2026)
- arXiv:2604.14246
- MoE router contextually disadvantages knowledge retrieval
- Offline causal analysis → redistribution of expert compute budget
- Budget-neutral, causally-grounded

## 3.4 MeZO: Memory-Efficient Zeroth-Order Optimization
- NeurIPS 2023, Princeton
- Forward passes only, no backprop, no gradient storage
- 30B on A100 80GB vs Adam's 2.7B limit
- 12× memory reduction, but 10-100× slower convergence
- SFT-style only — cannot do RL with MeZO

## 3.5 Suprmind Divergence Index (March-April 2026)
- 1,324 multi-model turns, 299 users, 10 domains
- **99.1%** of turns produced contradiction/correction/unique insight
- Legal domain: 0% "silent agreement" rate
- This IS our ensemble architecture's detection mechanism

---

# PART 4: THE A2AJ DATASET (VERIFIED)

**Source:** a2aj/canadian-case-law on HuggingFace
**Rows:** 223,000+
**License:** MIT (code), upstream varies (data)
**Languages:** English + French

**Structure (verified by sampling):**

| Field | Content |
|---|---|
| citation_en | "2018 BCCA 111" |
| name_en | "R. v. Gill" |
| dataset | Court abbreviation (BCCA, ONCA, etc.) |
| unofficial_text_en | Full text of decision |
| cases_cited_en | List of citations referenced |
| cases_citing_en | List of citations that reference this case |
| url_en | Source URL on court website |
| upstream_license | Per-document license terms |

**Courts verified from dataset siblings (26 folders):**
BCCA, BCSC, CHRT, CIRB, CITT, CMAC, CT, FC, FCA, FPSLREB, NSCA, NSFC, NSPC, NSSC, NSSM, OHSTC, OIC, ONCA, PSDPT, RAD, RLLR, RPD, SCC, SST, TCC, YKCA

**Critical: upstream_license varies per court.** Some restrict commercial use. For V0 trial: use freely. For V1 production: source clean data with verified licenses.

---

# PART 5: SECOND OPINION SYNTHESIS

## 5.1 Zero-Chain Enforcement (From Second Opinion)

The merged approach: F-DPO first (weight-level truth preference), then zero-chain GRPO/GSPO (behavior enforcement). No reasoning tokens emitted — max_completion_length=128, -3.0 penalty for any reasoning marker.

```
def zero_chain_factual_reward(prompts, completions):
    for completion in completions:
        if any(m in completion.lower() for m in ["thinking", "verifying", "step", "because"]):
            rewards.append(-3.0)  # Kill reasoning chains
        elif citation_verified(completion):
            rewards.append(2.5)   # Direct verified output
        else:
            rewards.append(0.0)
```

## 5.2 Dual-Index RAG (From Second Opinion)

Separate institutional memory from factual verification:
- **Graph Layer (Neo4j/GraphRAG):** Facts — client names, corporate structures, jurisdictions, precedents. Deterministic graph traversal, no semantic drift.
- **Vector Layer (Qdrant/Milvus):** Style — memo formats, email tones, boilerplate clauses. Restricted to formatting only.

Prompt fencing:
```
[INSTITUTIONAL FACTS - DO NOT ALTER]: <Graph Data>
[STYLE SPECIFICATION - FOR FORMATTING ONLY]: <Vector Data>
[TASK]: Extract and verify against registry.
```

## 5.3 In-Memory A2AJ Registry (From Second Opinion)

Bloom filter + MurmurHash3 for sub-millisecond citation lookup during training. 223K cases in <200MB RAM. Pattern:
- Bloom filter: instant negative rejection
- Hash registry: exact positive confirmation
- Used during GRPO/GSPO training only — NOT shipped at inference

## 5.4 MoE-Aware Router Hooking (From Second Opinion)

Hook AgentWorld's wg (gate) modules to capture expert routing decisions per forward pass. Train probes to check if specific experts handle verification. Currently speculative — expert-to-function mapping unknown, requires post-training discovery.

## 5.5 SIVP Rejected (Consensus)

The Search-Interleaved Vocabulary Pruning (external LogitsProcessor + Bloom filter at inference) was rejected. It's a commodity — anyone can build it. The moat is the model's weights learning to refuse hallucination internally, not an external filter.

---

# PART 6: HARDWARE

## 6.1 RTX 3090 (Development)
- 24GB VRAM, 32GB RAM
- Gemma 4 12B at Q4: ~6GB
- AgentWorld 35B-A3B at Q4: ~20GB (tight, fits for inference only)
- F-DPO on 8-9B models: QLoRA fits
- Full training: not enough. Inference only for 35B.

## 6.2 RTX PRO 6000 Blackwell (Training — Rented)
- 96GB GDDR7, 1792 GB/s bandwidth
- PCIe 5.0 x16
- FP16 tensor: 251.90 TFLOPS (dense), 503.80 (sparse)
- FP8 tensor: 503.80 TFLOPS (dense), 1007.61 (sparse)
- 5th Gen Tensor Cores, 2nd Gen Transformer Engine
- Unsloth MoE LoRA confirmed working on this card
- Rental: ~$3-6/hr via JarvisLabs/Lambda Labs
- 3-day training: ~$200-400

**Training approach:** Unsloth MoE LoRA (FP16, QLoRA not supported for MoE). Qwen3-30B-A3B reference: 63GB VRAM with Unsloth LoRA. AgentWorld 35B-A3B estimated 70-75GB — fits in 96GB with headroom for activations.

---

# PART 7: VERSION 0 ARCHITECTURE

## 7.1 Runtime Ensemble

```
Same Query + Dual-Index RAG Context
              │
        ┌─────┴─────┐
        ▼           ▼
┌──────────────┐ ┌──────────────────────┐
│ AgentWorld   │ │ Gemma 4 12B          │
│ 35B-A3B      │ │ (GRPO-Trained)       │
│ (F-DPO+GSPO) │ │                      │
│              │ │ Explicit scaffold:    │
│ Zero-chain:  │ │ <verification_plan>  │
│ hidden-state │ │ → <cross_examination>│
│ world-model  │ │ → <calibrated_output>│
│ prediction.  │ │                      │
│ Direct       │ │ Auditable reasoning. │
│ output only. │ │                      │
└──────┬───────┘ └──────────┬───────────┘
       │                    │
       ▼                    ▼
  token probs          token probs
       │                    │
       └────────┬───────────┘
                ▼
         COMPARE outputs
                │
          AGREE → output
          DISAGREE → flag hallucination
```

## 7.2 Training Pipeline (V0 on RTX 6000)

### AgentWorld 35B-A3B

**Stage 1: F-DPO (Weight-Level Truth Preference)**
- Data: 50K-100K preference pairs from A2AJ
- Chosen: real citation + verbatim text
- Rejected: corrupted citation (wrong court, wrong year, paraphrased)
- Method: Unsloth MoE LoRA (16-bit)
- Outcome: weights prefer real citations over fluent fabrications

**Stage 2: Zero-Chain GSPO (Behavioral Lock)**
- Continuation of AgentWorld's native GSPO training
- Reward: +2.5 verified, -2.0 hallucinated, -3.0 reasoning token, +0.5 abstention
- max_completion_length=128
- In-memory A2AJ Bloom registry as training-time reward scorer
- Model runs standalone at inference

### Gemma 4 12B

**GRPO Self-Scaffolding Training**
- Ornith-style three-phase scaffold:
  - `<verification_plan>`: what entities/citations to check
  - `<cross_examination>`: compare inputs against plan, flag conflicts
  - `<calibrated_output>`: final verified result
- Reward functions:
  - Format: +1.5 for correct tag sequence, -1.0 for missing tags
  - Contradiction trapping: +2.0 for identifying conflicts, -2.0 for merging lies
  - Grounding: parse plan tokens for real statutory codes
- Unsloth QLoRA (dense 12B, fits)
- No zero-chain constraint — Gemma's reasoning IS the audit trail

## 7.3 Constrained Decoding (Inference Only)

Outlines/LMQL grammar at inference:
```
STATUS = "FOUND" | "ABSENT" | "UNVERIFIABLE"
OUTPUT = {"status": STATUS, "source_id": CITATION, "exact_text": TEXT}
```
Model cannot emit free text. Cannot explain reasoning. Only structured, verifiable facts or refusal.

---

# PART 8: VERSION 0 TRIAL PLAN

## 8.1 Phase 0: Data Pipeline (Week 1)

### Day 1: Environment
- Python 3.10+, PyTorch CUDA, HuggingFace datasets/transformers
- Unsloth for MoE training, Outlines for constrained decoding
- Git repo, project structure

### Day 2: Dataset Download + Filter
- Download a2aj/canadian-case-law from HuggingFace
- Filter: ONCA + SCC + FCA courts, English, >1000 chars
- Target: 35K-50K decisions
- Generate stats: court/year/text distributions

### Day 3-4: F-DPO Pair Generation
- Type 1 (Citation): "What case is [citation]?" → real vs fake
- Type 2 (Holding): "What did [court] hold about [principle]?" → exact vs synthesized
- Type 3 (Statute): "What statute governs [topic]?" → real vs invented
- Corruption strategies: swap court, perturb year, paraphrase text, invent holdings
- Target: 50K pairs minimum

### Day 5: F-DPO Training
- Unsloth MoE LoRA on AgentWorld 35B-A3B
- RTX 6000 rental (96GB)
- Hyperparameters: r=16, lora_alpha=16, target_modules=[q_proj, k_proj, v_proj, o_proj, wg]
- Learning rate 3e-5, batch 1, grad accum 4
- Expected: 6-12 hours

### Day 6-7: Zero-Chain GSPO
- Native GSPO continuation (not GRPO — matches AgentWorld's training)
- Reward: A2AJ in-memory registry
- max_completion_length=128
- -3.0 penalty any reasoning token
- Expected: 12-24 hours

## 8.2 Phase 1: Evaluation (Week 2)

### Day 8: Benchmark Construction
- Hold out 1,000 decisions
- Generate test queries:
  - 100: citation extraction (real cases)
  - 100: hallucination test (non-existent cases — must output UNVERIFIABLE)
  - 50: ambiguous queries (must appropriately abstain)
  - 50: jurisdiction test (mixed courts)
  - 50: French queries (bilingual test)

### Day 9-10: Model Evaluation
- Run trained AgentWorld on all test queries
- Metrics:
  - Citation accuracy: >90% target
  - Exact text fidelity: >85% target
  - Hallucination rate: <5% target (on non-existent cases)
  - Abstention rate: >20% target (on ambiguous queries)
  - Jurisdiction accuracy: >90%
  - Bilingual accuracy: >80%

### Day 11: Ensemble Testing
- Load frozen Gemma 4 12B
- Run dual-model pipeline
- Measure disagreement rate
- Verify disagreement = hallucination detection

### Day 12: Constrained Decoding
- Implement Outlines grammar
- Verify model cannot output free text
- Measure latency overhead (<1%)

### Day 13: Documentation
- Write results + publish model weights to HF (PeppX/Veritas-AgentWorld-Canadian-Legal)
- Publish benchmark and methodology

### Day 14: Iterate
- Analyze failure modes
- Adjust hyperparameters, regenerate pairs, retrain
- V0 complete when targets met

## 8.3 Success Gates

| Gate | Metric | Target |
|---|---|---|
| G1 | Citation accuracy | >90% |
| G2 | Hallucination rate (fake cases) | <5% |
| G3 | Abstention rate (ambiguous) | >20% |
| G4 | Ensemble disagreement catches errors | >95% of hallucinations flagged |
| G5 | End-to-end latency | <5s per query |
| G6 | Training cost | <$400 |

**V0 ships when all gates pass. V1 launches with production data, UI, and deployment.**

---

# PART 9: KNOWN GAPS AND RISKS

## 9.1 Unresolved Technical Gaps

1. **F-DPO on MoE untested.** Paper tested dense models 1B-14B. 35B MoE with Unsloth LoRA is uncharted.
2. **GSPO continuation stability.** Using GSPO on an F-DPO-primed model — interaction effects unknown.
3. **Expert-to-function mapping.** Which MoE experts handle legal verification? Unknown — requires post-training probing.
4. **Bilingual coverage.** French decisions in A2AJ have limited fields. Civil law (Quebec) vs common law (rest of Canada) difference unaddressed.
5. **CanLII API metadata-only.** Full-text verification at runtime may need alternative sources.

## 9.2 Licensing Risk
A2AJ data has per-document upstream licenses. Some restrict commercial use. V0 trial uses freely. V1 production needs clean data.

## 9.3 The SIVP Temptation
If internal weight-level verification doesn't converge, the fallback is an external LogitsProcessor + Bloom filter. This works but is not a moat. Only use if training fails.

---

# APPENDIX: COMPLETE CITATION INDEX

- F-DPO: arXiv:2601.03027, ACL 2026 Findings
- RL's Razor: arXiv:2509.04259, MIT
- Retaining by Doing: arXiv:2510.18874, Princeton
- Test-Time Compute: arXiv:2509.06861, USC/Meta AI
- Counterfactual Routing: arXiv:2604.14246, ACL 2026
- AgentWorld: arXiv:2606.24597, Qwen Team
- GSPO: arXiv:2507.18071
- MeZO: arXiv:2305.17333, NeurIPS 2023
- Suprmind Divergence Index: Academia.edu, April 2026
- Stanford Legal Hallucination: Magesh et al., 2024/2025
- Harvey LAB: harvey.ai/blog, May 2026
- A2AJ Dataset: huggingface.co/datasets/a2aj/canadian-case-law
- Vectara HHEM: github.com/vectara/hallucination-leaderboard
- ChatLaw: arXiv:2306.16092
- Lawyer LLaMA: arXiv:2305.15062
