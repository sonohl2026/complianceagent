from app.services.quick_scan.source_divergence import check_source_divergence


class _FakeDivergenceLLM:
    def __init__(self, response_content: dict):
        self.response_content = response_content
        self.last_kwargs = None

    async def structured_completion(self, **kwargs):
        from app.services.llm.base import LLMResult

        self.last_kwargs = kwargs
        return LLMResult(
            content=self.response_content, raw_content="{}", requested_model=kwargs["model"],
            model_response_identifier="fake", prompt_tokens=0, completion_tokens=0,
            total_tokens=0, cost_usd=0.0, latency_ms=1, finish_reason="stop",
        )


async def test_no_divergence_when_sources_describe_the_same_product():
    llm = _FakeDivergenceLLM({
        "diverges": False,
        "groups": [{"product_name": "Impella", "manufacturer": "Abiomed, Inc.", "source_indices": [0, 1]}],
    })
    result = await check_source_divergence(llm, "fake-model", ["Impella web page text", "Impella academic paper text"])
    assert result.diverges is False
    assert len(result.groups) == 1
    assert result.groups[0].source_indices == [0, 1]


async def test_diverges_when_sources_describe_different_products():
    llm = _FakeDivergenceLLM({
        "diverges": True,
        "groups": [
            {"product_name": "SonoHL", "manufacturer": "", "source_indices": [0]},
            {"product_name": "Impella", "manufacturer": "Abiomed, Inc.", "source_indices": [1]},
        ],
    })
    result = await check_source_divergence(llm, "fake-model", ["SonoHL web page text", "Impella academic paper text"])
    assert result.diverges is True
    assert len(result.groups) == 2
    assert {g.product_name for g in result.groups} == {"SonoHL", "Impella"}


async def test_each_source_is_labeled_by_index_in_the_prompt():
    llm = _FakeDivergenceLLM({
        "diverges": False,
        "groups": [{"product_name": "X", "manufacturer": "", "source_indices": [0, 1, 2]}],
    })
    await check_source_divergence(llm, "fake-model", ["first source", "second source", "third source"])
    user_message = llm.last_kwargs["messages"][0]["content"]
    assert "--- Source 0 ---" in user_message
    assert "first source" in user_message
    assert "--- Source 1 ---" in user_message
    assert "second source" in user_message
    assert "--- Source 2 ---" in user_message
    assert "third source" in user_message


async def test_records_usage_when_callback_given():
    calls = []

    async def on_usage(stage_name, result):
        calls.append(stage_name)

    llm = _FakeDivergenceLLM({
        "diverges": False,
        "groups": [{"product_name": "X", "manufacturer": "", "source_indices": [0, 1]}],
    })
    await check_source_divergence(llm, "fake-model", ["a", "b"], on_usage=on_usage)
    assert calls == ["source_divergence_check"]
