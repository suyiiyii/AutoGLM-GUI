def test_glm_agent_module_path():
    from AutoGLM_GUI.agents.glm.async_agent import AsyncGLMAgent

    assert AsyncGLMAgent is not None


def test_glm_parser_module_path():
    from AutoGLM_GUI.agents.glm.parser import GLMParser

    assert GLMParser is not None
