"""Message conversion for the Anthropic client (no SDK or network needed)."""

from cashbooks.llm.base import Message
from cashbooks.llm.claude import to_messages


def test_roles_and_empty_text():
    out = to_messages([Message("user", "Is NS-1048 paid?"), Message("model", ""), Message("user", "And NS-1062?")])
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[1]["content"] == "(no reply)"
