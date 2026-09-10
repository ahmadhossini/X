from billing.metering import TokenUsage, gemini_flash_cost


def test_gemini_flash_cost_uses_input_and_output_rates():
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000)
    cost = gemini_flash_cost(usage)
    assert cost.input_usd == 0.30
    assert cost.output_usd == 2.50
    assert cost.total_usd == 2.80


def test_total_tokens_falls_back_to_component_sum():
    usage = TokenUsage(input_tokens=120, output_tokens=80)
    assert usage.normalized_total == 200


def test_negative_token_counts_are_rejected():
    try:
        TokenUsage(input_tokens=-1)
    except ValueError as exc:
        assert "negative" in str(exc)
    else:
        raise AssertionError("negative token counts must be rejected")
