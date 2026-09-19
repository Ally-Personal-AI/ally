from ally.tools.builtin import SystemInfoTool, build_default_tool_registry


def test_default_registry_exposes_only_safe_system_info() -> None:
    registry = build_default_tool_registry()

    assert [tool.spec.name for tool in registry.list()] == ["system.info"]
    assert registry.get("system.info") is not None


def test_system_info_is_read_only_and_rejects_arguments() -> None:
    tool = SystemInfoTool()

    assert tool.spec.risk == "read_only"
    result = tool.run({})

    assert isinstance(result, dict)
    assert "python_version" in result
