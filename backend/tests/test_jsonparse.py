from app.pipeline.jsonparse import extract_json_array, extract_json_object


def test_array_from_fenced_markdown():
    txt = 'sure:\n```json\n[{"a":1},{"b":2}]\n```\ndone'
    assert extract_json_array(txt) == [{"a": 1}, {"b": 2}]


def test_array_with_leading_reasoning():
    txt = 'The user wants facts. Here: [{"claim":"x"}]'
    assert extract_json_array(txt) == [{"claim": "x"}]


def test_array_none_on_junk():
    assert extract_json_array("no json here") is None
    assert extract_json_array("") is None


def test_object_from_fenced_markdown():
    assert extract_json_object('```json\n{"facts": []}\n```') == {"facts": []}


def test_object_ignores_trailing_prose():
    assert extract_json_object('{"ok": true} thanks!') == {"ok": True}


def test_object_none_on_array_input():
    # an array is not an object
    assert extract_json_object("[1,2,3]") is None
