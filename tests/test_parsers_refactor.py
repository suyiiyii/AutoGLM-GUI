"""Test the new parser architecture."""

from AutoGLM_GUI.parsers import GLMParser, MAIParser, PhoneAgentParser


def test_glm_parser_tap():
    parser = GLMParser()
    result = parser.parse('do(action="Tap", coordinate=[500, 500])')
    assert result["_metadata"] == "do"
    assert result["action"] == "Tap"
    assert result["coordinate"] == [500, 500]


def test_glm_parser_finish():
    parser = GLMParser()
    result = parser.parse('finish(message="Done")')
    assert result["_metadata"] == "finish"
    assert result["message"] == "Done"


def test_phone_parser_tap():
    parser = PhoneAgentParser()
    result = parser.parse('do(action="Tap", element=[500, 500])')
    assert result["_metadata"] == "do"
    assert result["action"] == "Tap"
    assert result["element"] == [500, 500]


def test_phone_parser_type():
    parser = PhoneAgentParser()
    result = parser.parse('do(action="Type", text="Hello")')
    assert result["_metadata"] == "do"
    assert result["action"] == "Type"
    assert result["text"] == "Hello"


def test_mai_parser_click():
    parser = MAIParser()
    raw = '<thinking>Click button</thinking><tool_call>{"name": "mobile_use", "arguments": {"action": "click", "coordinate": [0.5, 0.5]}}</tool_call>'
    result = parser.parse(raw)
    assert result["_metadata"] == "do"
    assert result["action"] == "Tap"
    assert result["element"] == [500, 500]


def test_mai_parser_terminate():
    parser = MAIParser()
    raw = '<thinking>Task done</thinking><tool_call>{"name": "mobile_use", "arguments": {"action": "terminate", "status": "success"}}</tool_call>'
    result = parser.parse(raw)
    assert result["_metadata"] == "finish"
    assert result["message"] == "Task completed"


def test_parser_coordinate_scales():
    glm_parser = GLMParser()
    phone_parser = PhoneAgentParser()
    mai_parser = MAIParser()

    assert glm_parser.coordinate_scale == 1000
    assert phone_parser.coordinate_scale == 1000
    assert mai_parser.coordinate_scale == 999
