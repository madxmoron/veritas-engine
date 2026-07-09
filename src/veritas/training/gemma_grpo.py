"""
Gemma 4 12B GRPO Self-Scaffolding Training Pipeline
=====================================================
Ornith-style three-phase scaffold for legal verification:
  <verification_plan> → <cross_examination> → <calibrated_output>

Reward functions (per blueprint Section 7.2):
  - Format: +1.5 for correct tag sequence, -1.0 for missing tags
  - Contradiction: +2.0 for identifying conflicts, -2.0 for merging lies
  - Grounding: +1.0 for real statutory codes/citations

Runs on RTX 3090 (24GB) with Unsloth QLoRA (4-bit).
"""
import re
import torch
from datasets import Dataset

# ============================================================
# REWARD FUNCTIONS
# ============================================================

VERIFICATION_PLAN_TAG = "<verification_plan>"
CROSS_EXAM_TAG = "<cross_examination>"
CALIBRATED_TAG = "<calibrated_output>"
REQUIRED_TAGS = [VERIFICATION_PLAN_TAG, CROSS_EXAM_TAG, CALIBRATED_TAG]

# Known Canadian legal citation patterns
CANLII_CITATION_RE = re.compile(
    r'\b\d{4}\s+(SCC|ONCA|FCA|FC|BCCA|ONSC|NSCA|SCTC)\s+\d+\b',
    re.IGNORECASE
)
# Known Ontario/Canadian statute patterns
STATUTE_RE = re.compile(
    r'\b(R\.?S\.?[OC]\s+\d{4}|S\.?[OC]\s+\d{4}|Criminal Code|'
    r'Charter of Rights|Constitution Act)\b.*?(s\.\s*\d+|section\s+\d+|'
    r'ss\.\s*\d+|subsection\s+\d+)',
    re.IGNORECASE
)
# Patterns that indicate hallucination/merging
LYING_PATTERNS = [
    r'\b(possibly|probably|likely|may have|might have|could have)\s+held\b',
    r'\b(synthesizing|combining|merging|blending)\b',
    r'\b(it appears|it seems|one might argue|arguably)\b',
    r'\b(without reviewing|without checking|to the best of)\b',
]


def format_reward(completions, **kwargs):
    """
    +1.5 for all three tags present in correct order (plan → exam → output)
    +0.5 for at least two tags present
    -1.0 for missing tags or wrong order
    """
    rewards = []
    for completion in completions:
        # Extract content after the prompt
        text = completion if isinstance(completion, str) else completion[0].get("content", "")
        if not isinstance(text, str):
            text = str(text)

        # Find positions of all three tags
        pos_plan = text.find(VERIFICATION_PLAN_TAG)
        pos_exam = text.find(CROSS_EXAM_TAG)
        pos_cal = text.find(CALIBRATED_TAG)

        tags_present = sum(1 for p in [pos_plan, pos_exam, pos_cal] if p >= 0)

        if tags_present == 3 and pos_plan < pos_exam < pos_cal:
            rewards.append(1.5)
        elif tags_present >= 2:
            rewards.append(0.5)
        elif tags_present == 1:
            rewards.append(-0.5)
        else:
            rewards.append(-1.0)

    return rewards


def contradiction_reward(completions, **kwargs):
    """
    +2.0 for identifying conflicts between sources
    -2.0 for merging/lying (hedging, synthesizing, "it appears")
      0.0 for neither
    """
    rewards = []
    for completion in completions:
        text = completion if isinstance(completion, str) else completion[0].get("content", "")
        if not isinstance(text, str):
            text = str(text)

        # Check cross-examination section specifically
        exam_start = text.find(CROSS_EXAM_TAG)
        exam_end = text.find(CALIBRATED_TAG) if CALIBRATED_TAG in text else len(text)
        exam_text = text[exam_start:exam_end] if exam_start >= 0 else text

        # Conflict identification: mentions of "conflict", "contradicts", "disagrees"
        conflict_signals = len(re.findall(
            r'\b(conflict|contradict|inconsistent|disagree|differ|'
            r'not supported|no authority|overturned|distinguished)\b',
            exam_text, re.IGNORECASE
        ))

        # Lying/merging: hedging, synthesizing without checking
        lying_signals = 0
        for pattern in LYING_PATTERNS:
            lying_signals += len(re.findall(pattern, exam_text, re.IGNORECASE))

        if conflict_signals > 0 and lying_signals == 0:
            rewards.append(2.0)
        elif lying_signals > 1:
            rewards.append(-2.0)
        elif lying_signals == 1:
            rewards.append(-1.0)
        else:
            rewards.append(0.0)

    return rewards


def grounding_reward(completions, **kwargs):
    """
    +1.0 for real citation (CanLII format) or real statute reference
    +0.5 for plausible citation format
    -0.5 for unsupported claims
    """
    rewards = []
    for completion in completions:
        text = completion if isinstance(completion, str) else completion[0].get("content", "")
        if not isinstance(text, str):
            text = str(text)

        # Check calibrated_output section specifically
        cal_start = text.find(CALIBRATED_TAG)
        cal_text = text[cal_start:] if cal_start >= 0 else text

        canlii_citations = len(CANLII_CITATION_RE.findall(cal_text))
        statute_refs = len(STATUTE_RE.findall(cal_text))

        if canlii_citations > 0 or statute_refs > 0:
            rewards.append(1.0)
        elif re.search(r'\b\d{4}\b.*\b(court|appeal|supreme|federal)\b',
                       cal_text, re.IGNORECASE):
            rewards.append(0.5)  # Has year + court mention, plausible
        else:
            rewards.append(-0.5)

    return rewards


# ============================================================
# DATASET FORMATTING
# ============================================================

LEGAL_SYSTEM_PROMPT = """You are a Canadian legal verification engine. Your role is to verify legal claims against authoritative sources.

For EVERY query, you MUST structure your response with these three phases:

<verification_plan>
List what you need to verify:
- Which citations to check
- Which jurisdiction rules apply
- What facts need cross-referencing
- What sources are relevant (CanLII, statute databases)
</verification_plan>

<cross_examination>
Compare the claim against your verification plan:
- Does the citation exist in the source database?
- Does the exact text match the source?
- Are there any conflicts between sources?
- Is the jurisdiction correct?
- Flag any discrepancies explicitly.
</cross_examination>

<calibrated_output>
Output ONLY one of:
- VERIFIED: citation + exact source text
- ABSENT: citation not found in sources
- UNVERIFIABLE: cannot confirm or deny with available sources
Include the source_id and exact_text when VERIFIED.
</calibrated_output>

RULES:
- NEVER paraphrase legal text — only exact quotations
- NEVER synthesize holdings from memory
- If sources conflict, flag it
- If uncertain, output UNVERIFIABLE
- Do not explain outside the three-phase structure"""


def format_legal_query(case_text: str, query_type: str = "citation") -> str:
    """
    Format a legal case into a verification query.
    
    Args:
        case_text: The full text of a legal decision
        query_type: "citation", "holding", or "statute"
    
    Returns:
        A prompt asking the model to verify a legal claim
    """
    if query_type == "citation":
        return f"""Verify this legal claim against CanLII:

Claim: The following case exists in Canadian law and its text is accurate.

{case_text[:2000]}

Output your three-phase verification."""

    elif query_type == "holding":
        return f"""Verify this legal holding against the source case:

A lawyer claims the following holding is from Canadian case law:

{case_text[:2000]}

Output your three-phase verification."""

    else:  # statute
        return f"""Verify this statutory reference against authoritative Canadian sources:

{case_text[:2000]}

Output your three-phase verification."""


def format_dataset_for_grpo(examples: list[dict]) -> Dataset:
    """
    Convert raw legal examples into GRPO training format.
    
    Each example needs a "prompt" field. The model generates completions
    which are then scored by the reward functions.
    
    Args:
        examples: List of {"text": ..., "citation": ..., "type": ...}
    
    Returns:
        HuggingFace Dataset with "prompt" column
    """
    prompts = []
    for ex in examples:
        query = format_legal_query(ex.get("text", ""), ex.get("type", "citation"))
        # For GRPO with chat models, format as conversation
        prompt = [
            {"role": "system", "content": LEGAL_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ]
        prompts.append({"prompt": prompt})

    return Dataset.from_list(prompts)
