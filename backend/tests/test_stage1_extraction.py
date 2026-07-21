from app.services.llm.base import LLMResult
from app.services.quick_scan.schemas import Stage1Extraction
from app.services.quick_scan.stage1_extraction import run_stage1, wrap_untrusted_data


class _FakeLLMProvider:
    """Matches the LLMProvider Protocol (app/services/llm/base.py) -- returns
    a scripted response per call, recording what it was called with so tests
    can assert on the actual request shape."""

    def __init__(self, content: dict):
        self.content = content
        self.last_call_kwargs: dict | None = None

    async def structured_completion(self, **kwargs) -> LLMResult:
        self.last_call_kwargs = kwargs
        return LLMResult(
            content=self.content, raw_content="{}", requested_model=kwargs["model"],
            model_response_identifier="fake-1", prompt_tokens=100, completion_tokens=50,
            total_tokens=150, cost_usd=0.0001, latency_ms=10, finish_reason="stop",
        )


_VALID_CONTENT = {
    "product_name": "Dexcom G7",
    "manufacturer": "Dexcom",
    "aliases": [],
    "intended_use": "Continuous glucose monitoring for people with diabetes",
    "technology_type": "continuous glucose monitor",
    "dev_stage_guess": "commercial",
    "candidate_search_terms": ["continuous glucose monitor"],
}


async def test_run_stage1_returns_validated_extraction():
    fake_llm = _FakeLLMProvider(_VALID_CONTENT)
    result = await run_stage1(fake_llm, "cheap/model", "Dexcom G7 is a CGM sensor worn on the arm.")
    assert isinstance(result, Stage1Extraction)
    assert result.product_name == "Dexcom G7"
    assert result.manufacturer == "Dexcom"


async def test_run_stage1_uses_the_requested_cheap_model():
    fake_llm = _FakeLLMProvider(_VALID_CONTENT)
    await run_stage1(fake_llm, "anthropic/claude-haiku-4.5", "some text")
    assert fake_llm.last_call_kwargs["model"] == "anthropic/claude-haiku-4.5"
    assert fake_llm.last_call_kwargs["max_tokens"] == 500


async def test_run_stage1_wraps_input_in_untrusted_data_tags():
    fake_llm = _FakeLLMProvider(_VALID_CONTENT)
    await run_stage1(fake_llm, "model", "some source text")
    sent_message = fake_llm.last_call_kwargs["messages"][0]["content"]
    assert sent_message.startswith("<untrusted_data>")
    assert sent_message.endswith("</untrusted_data>")
    assert "some source text" in sent_message


async def test_run_stage1_truncates_long_input():
    fake_llm = _FakeLLMProvider(_VALID_CONTENT)
    long_text = "x" * 100_000
    await run_stage1(fake_llm, "model", long_text)
    sent_message = fake_llm.last_call_kwargs["messages"][0]["content"]
    # 8k tokens * ~4 chars/token = 32000 chars, plus the wrapper tags
    assert len(sent_message) < 33_000


def test_wrap_untrusted_data_matches_system_prompt_v2_wording():
    wrapped = wrap_untrusted_data("hello")
    assert wrapped == "<untrusted_data>\nhello\n</untrusted_data>"
