from ally.events import (
    AttentionClass,
    DefaultAttentionPolicy,
    EventImportance,
    NewEvent,
)


def test_default_attention_policy_maps_importance_conservatively() -> None:
    policy = DefaultAttentionPolicy()

    expected: dict[EventImportance, AttentionClass] = {
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
            importance=importance,
        )
        assert policy.classify(event) == attention
