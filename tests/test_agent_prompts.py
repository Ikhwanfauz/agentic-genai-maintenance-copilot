from app.agent.prompts import DIAGNOSIS_SYNTHESIS_PROMPT


def test_diagnosis_prompt_defines_work_order_action_classification() -> None:
    prompt = DIAGNOSIS_SYNTHESIS_PROMPT

    assert "controlled physical inspection" in prompt
    assert "state_changing=true" in prompt
    assert "requires_human_approval=true" in prompt
    assert "monitoring" in prompt
    assert "work-order proposal" in prompt
