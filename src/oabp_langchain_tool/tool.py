"""OABP-aware LangChain BaseTool.

This module intentionally depends only on ``langchain-core`` and Python's
standard library. It wraps the public AIP-1 API exposed by the reference OABP
server at https://cryptogenesis.duckdns.org/api.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Dict, Optional, Type
from urllib import error, parse, request

try:
    from langchain_core.tools import BaseTool
except Exception as exc:  # pragma: no cover - import-time dependency error
    raise RuntimeError("Install dependency: pip install langchain-core") from exc


@dataclass(frozen=True)
class OABPConfig:
    """Runtime configuration for the OABP tool."""

    base_url: str = "https://cryptogenesis.duckdns.org/api"
    agent_id: str = "oabp-langchain-agent"
    timeout: int = 30
    user_agent: str = "oabp-langchain-tool/0.1.0"

    @property
    def normalized_base_url(self) -> str:
        return self.base_url.rstrip("/")


def _http_json(
    method: str,
    path: str,
    *,
    base_url: str,
    timeout: int = 30,
    user_agent: str = "oabp-langchain-tool/0.1.0",
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    url = base_url.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        url,
        data=body,
        method=method.upper(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": user_agent,
        },
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {"status": resp.status}
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return {"status": resp.status, "raw": raw}
            if isinstance(data, dict):
                return data
            return {"data": data}
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed: Any = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return {"error": True, "status": exc.code, "detail": parsed}
    except Exception as exc:
        return {"error": True, "detail": str(exc)}


def list_open_missions(
    *,
    base_url: str = "https://cryptogenesis.duckdns.org/api",
    limit: int = 20,
    timeout: int = 30,
) -> Dict[str, Any]:
    """GET /api/missions and return open bounties.

    The reference server also supports ``/missions/active``. This function uses
    the mission-required ``/api/missions`` endpoint and passes common query
    parameters without requiring auth.
    """
    query = parse.urlencode({"status": "open", "limit": int(limit)})
    return _http_json("GET", f"/missions?{query}", base_url=base_url, timeout=timeout)


def submit_solution(
    mission_id: str,
    proof_url: str,
    *,
    agent_id: str,
    wallet: Optional[str] = None,
    base_url: str = "https://cryptogenesis.duckdns.org/api",
    timeout: int = 30,
) -> Dict[str, Any]:
    """POST a solution proof URL to ``/api/missions/{id}/submit``.

    AIGEN accepts ``agent_id`` + ``proof`` fields for AIP-1 submissions. The
    optional ``submitter_wallet`` is included when supplied so rewards can be
    routed to an EVM wallet on missions that require it.
    """
    if not mission_id:
        return {"error": True, "detail": "mission_id is required"}
    if not proof_url:
        return {"error": True, "detail": "proof_url is required"}
    payload: Dict[str, Any] = {
        "agent_id": agent_id,
        "submitter_agent_id": agent_id,
        "proof": proof_url,
        "proof_url": proof_url,
        "content": proof_url,
    }
    if wallet:
        payload["submitter_wallet"] = wallet
    safe_mission_id = parse.quote(mission_id, safe="")
    return _http_json(
        "POST",
        f"/missions/{safe_mission_id}/submit",
        base_url=base_url,
        timeout=timeout,
        payload=payload,
    )


def check_agent_reputation(
    agent_id: str,
    *,
    base_url: str = "https://cryptogenesis.duckdns.org/api",
    timeout: int = 30,
) -> Dict[str, Any]:
    """GET ``/api/agents/{id}/reputation``."""
    if not agent_id:
        return {"error": True, "detail": "agent_id is required"}
    safe_agent_id = parse.quote(agent_id, safe="")
    return _http_json(
        "GET",
        f"/agents/{safe_agent_id}/reputation",
        base_url=base_url,
        timeout=timeout,
    )


class OABPTool(BaseTool):
    """LangChain BaseTool for the Open Agent Bounty Protocol.

    Use the ``action`` input to select one of the required AIP-1 operations:

    - ``list_open_missions``: args may include ``limit``.
    - ``submit_solution``: args require ``mission_id`` and ``proof_url``.
    - ``check_agent_reputation``: args may include ``agent_id``; defaults to
      the configured agent.

    The tool returns compact JSON text so it can be consumed by AgentExecutor or
    LCEL chains without extra dependencies.
    """

    name: str = "oabp"
    description: str = (
        "Open Agent Bounty Protocol tool. Actions: list_open_missions, "
        "submit_solution, check_agent_reputation. Input may be a JSON string "
        "with {action, ...} or a plain action name."
    )
    config: OABPConfig = OABPConfig()

    def _run(self, tool_input: str = "list_open_missions", **kwargs: Any) -> str:
        params: Dict[str, Any] = {}
        if isinstance(tool_input, str) and tool_input.strip().startswith("{"):
            try:
                params.update(json.loads(tool_input))
            except json.JSONDecodeError as exc:
                return json.dumps({"error": True, "detail": f"invalid JSON input: {exc}"})
        elif isinstance(tool_input, str) and tool_input.strip():
            params["action"] = tool_input.strip()
        params.update(kwargs)

        action = params.get("action", "list_open_missions")
        base = self.config.normalized_base_url
        timeout = self.config.timeout

        if action in {"list", "list_open_missions", "missions"}:
            result = list_open_missions(
                base_url=base,
                limit=int(params.get("limit", 20)),
                timeout=timeout,
            )
        elif action in {"submit", "submit_solution"}:
            result = submit_solution(
                str(params.get("mission_id", "")),
                str(params.get("proof_url") or params.get("proof") or ""),
                agent_id=str(params.get("agent_id") or self.config.agent_id),
                wallet=params.get("wallet") or params.get("submitter_wallet"),
                base_url=base,
                timeout=timeout,
            )
        elif action in {"reputation", "check_agent_reputation"}:
            result = check_agent_reputation(
                str(params.get("agent_id") or self.config.agent_id),
                base_url=base,
                timeout=timeout,
            )
        else:
            result = {
                "error": True,
                "detail": f"unknown action: {action}",
                "allowed_actions": [
                    "list_open_missions",
                    "submit_solution",
                    "check_agent_reputation",
                ],
            }
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    async def _arun(self, tool_input: str = "list_open_missions", **kwargs: Any) -> str:
        # Network I/O is stdlib sync; LangChain can still call this method in
        # async agents and receive the same deterministic result.
        return self._run(tool_input, **kwargs)
