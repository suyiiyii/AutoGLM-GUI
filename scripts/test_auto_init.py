#!/usr/bin/env python3
"""测试 PhoneAgentManager 的自动初始化功能"""

from AutoGLM_GUI.phone_agent_manager import PhoneAgentManager


def test_auto_initialize_parameter():
    """测试 auto_initialize 参数是否正确传递"""
    manager = PhoneAgentManager.get_instance()

    # 检查 acquire_device 方法签名
    import inspect

    sig = inspect.signature(manager.acquire_device)
    params = list(sig.parameters.keys())

    print("✓ acquire_device 参数:")
    for param in params:
        print(f"  - {param}")

    # 验证 auto_initialize 参数存在
    assert "auto_initialize" in params, "auto_initialize 参数不存在"
    default_value = sig.parameters["auto_initialize"].default
    assert default_value is False, (
        f"auto_initialize 默认值应该是 False，实际是 {default_value}"
    )
    print(f"✓ auto_initialize 参数默认值: {default_value}")

    # 检查 use_agent 方法签名
    sig = inspect.signature(manager.use_agent)
    params = list(sig.parameters.keys())

    print("\n✓ use_agent 参数:")
    for param in params:
        print(f"  - {param}")

    # 验证 auto_initialize 参数存在
    assert "auto_initialize" in params, "use_agent 的 auto_initialize 参数不存在"
    default_value = sig.parameters["auto_initialize"].default
    assert default_value is True, (
        f"use_agent auto_initialize 默认值应该是 True，实际是 {default_value}"
    )
    print(f"✓ use_agent auto_initialize 参数默认值: {default_value}")

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！自动初始化参数已正确添加")
    print("=" * 60)


if __name__ == "__main__":
    test_auto_initialize_parameter()
