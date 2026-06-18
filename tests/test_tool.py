import json
from unittest.mock import patch

from oabp_langchain_tool import OABPTool, OABPConfig, check_agent_reputation, submit_solution


def test_tool_lists_open_missions_with_mocked_http():
    tool = OABPTool(config=OABPConfig(base_url="https://example.test/api"))
    with patch("oabp_langchain_tool.tool._http_json") as http:
        http.return_value = {"missions": [{"id": "mis_1"}], "total": 1}
        out = json.loads(tool.invoke('{"action":"list_open_missions","limit":1}'))
    assert out["missions"][0]["id"] == "mis_1"
    http.assert_called_once()
    assert http.call_args.args[0] == "GET"
    assert http.call_args.args[1].startswith("/missions?")


def test_submit_solution_payload_contains_required_fields():
    with patch("oabp_langchain_tool.tool._http_json") as http:
        http.return_value = {"submission_id": "sub_1"}
        result = submit_solution(
            "mis_123",
            "https://github.com/acme/repo",
            agent_id="agent-x",
            wallet="0x0000000000000000000000000000000000000001",
            base_url="https://example.test/api",
        )
    assert result["submission_id"] == "sub_1"
    payload = http.call_args.kwargs["payload"]
    assert payload["agent_id"] == "agent-x"
    assert payload["submitter_agent_id"] == "agent-x"
    assert payload["proof"] == "https://github.com/acme/repo"
    assert payload["submitter_wallet"].startswith("0x")


def test_reputation_uses_reputation_endpoint():
    with patch("oabp_langchain_tool.tool._http_json") as http:
        http.return_value = {"agent_id": "agent-x", "reputation": {"elo": 1400}}
        result = check_agent_reputation("agent-x", base_url="https://example.test/api")
    assert result["reputation"]["elo"] == 1400
    assert http.call_args.args[1] == "/agents/agent-x/reputation"


def test_unknown_action_returns_error_json():
    tool = OABPTool()
    out = json.loads(tool.invoke('{"action":"nope"}'))
    assert out["error"] is True
    assert "allowed_actions" in out
