import json
import pytest
from unittest.mock import MagicMock, patch


def _make_response(text):
    response = MagicMock()
    response.content = [MagicMock(text=text)]
    return response


def test_chat_returns_filters_on_valid_json():
    payload = '{"specialty": "Cardiology", "gender": "F", "radius": 25, "profile_choice": "Balanced"}'
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.return_value = _make_response(payload)

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "female cardiologist"}], ["Cardiology"])

    assert result["type"] == "filters"
    assert result["data"]["specialty"] == "Cardiology"
    assert result["data"]["gender"] == "F"
    assert result["data"]["radius"] == 25
    assert result["data"]["profile_choice"] == "Balanced"


def test_chat_returns_followup_on_plain_text():
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.return_value = _make_response(
            "How far are you willing to travel?"
        )

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "I need a doctor"}], ["Cardiology"])

    assert result["type"] == "followup"
    assert result["data"] == "How far are you willing to travel?"


def test_chat_returns_error_when_api_key_missing():
    with patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = None

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "test"}], ["Cardiology"])

    assert result["type"] == "error"
    assert "ANTHROPIC_API_KEY" in result["data"]


def test_chat_returns_error_on_api_exception():
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_cls.return_value.messages.create.side_effect = Exception("network error")

        from src.utils.llm import chat
        result = chat([{"role": "user", "content": "test"}], ["Cardiology"])

    assert result["type"] == "error"


def test_chat_passes_full_message_history():
    payload = '{"specialty": "Cardiology", "gender": null, "radius": null, "profile_choice": null}'
    messages = [
        {"role": "user", "content": "I need a cardiologist"},
        {"role": "assistant", "content": "How far are you willing to travel?"},
        {"role": "user", "content": "Within 25 miles"},
    ]
    with patch("src.utils.llm.Anthropic") as mock_cls, patch("src.utils.llm.st") as mock_st:
        mock_st.secrets.get.return_value = "test-key"
        mock_create = mock_cls.return_value.messages.create
        mock_create.return_value = _make_response(payload)

        from src.utils.llm import chat
        chat(messages, ["Cardiology"])

    called_messages = mock_create.call_args.kwargs["messages"]
    assert len(called_messages) == 3
    assert called_messages[2]["content"] == "Within 25 miles"
