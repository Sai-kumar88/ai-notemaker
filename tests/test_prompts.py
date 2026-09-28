from app.prompts.summary_prompt import (
    FAITHFUL_SUMMARY_SYSTEM_PROMPT,
    CHUNK_SUMMARY_SYSTEM_PROMPT,
    COMBINE_SUMMARIES_SYSTEM_PROMPT,
    build_direct_summary_prompt,
    build_chunk_summary_prompt
)


def test_faithful_summary_prompt_constraints():
    # Prompt must explicitly prohibit hallucination, external knowledge, and inventing information
    assert "ABSOLUTE GROUNDING" in FAITHFUL_SUMMARY_SYSTEM_PROMPT
    assert "ZERO HALLUCINATION" in FAITHFUL_SUMMARY_SYSTEM_PROMPT
    assert "STRICTLY AND EXCLUSIVELY" in FAITHFUL_SUMMARY_SYSTEM_PROMPT
    assert "PRESERVE ORIGINAL TERMINOLOGY" in FAITHFUL_SUMMARY_SYSTEM_PROMPT


def test_chunk_prompts_constraints():
    assert "STRICTLY" in CHUNK_SUMMARY_SYSTEM_PROMPT
    assert "Do NOT introduce external knowledge" in CHUNK_SUMMARY_SYSTEM_PROMPT


def test_build_direct_summary_prompt():
    text = "Photosynthesis converts light into chemical energy."
    prompt = build_direct_summary_prompt(text, context_label="Biology Chapter 1")
    assert "<<<BEGIN SOURCE TEXT>>>" in prompt
    assert text in prompt
    assert "<<<END SOURCE TEXT>>>" in prompt
    assert "do NOT include or invent it" in prompt
