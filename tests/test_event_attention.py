from ally.events import DefaultAttentionPolicy, NewEvent


def test_default_attention_policy_maps_importance_conservatively() -> None:
    policy = DefaultAttentionPolicy()

    expected = {
        "noise": "ignore",
        "routine": "remember",
        "important": "mention_later",
        "urgent": "notify",
        "critical": "interrupt",
    }

    for importance, attention in expected.items():
        event = NewEvent(
            type="test.event",
            source="synthetic",
            importance=importance,  # type: ignore[arg-type]
        )
        assert policy.classify(event) == attention
