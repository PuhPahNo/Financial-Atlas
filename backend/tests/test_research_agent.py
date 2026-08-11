from app.assistant import research_agent
from app.core.config import settings
from app.main import app
from auth_helpers import authenticate
from fastapi.testclient import TestClient

client = authenticate(TestClient(app))


def test_research_agent_executes_tools_and_returns_grounded_artifacts(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "fixture-key")
    responses = [
        {
            "id": "resp_tool",
            "output": [{
                "type": "function_call",
                "call_id": "call_1",
                "name": "compare_securities",
                "arguments": '{"tickers":["SPY","QQQ"],"range":"1y"}',
            }],
        },
        {
            "id": "resp_final",
            "output": [{
                "type": "message",
                "content": [{"type": "output_text", "text": "SPY had the better risk-adjusted result in the observed window."}],
            }],
        },
    ]
    requests = []

    def fake_response(payload, *, session_id):
        requests.append(payload)
        return responses.pop(0)

    def fake_execute(name, arguments):
        assert name == "compare_securities"
        assert arguments == {"tickers": ["SPY", "QQQ"], "range": "1y"}
        return {
            "data": {"securities": [{"ticker": "SPY", "total_return": 0.12}]},
            "artifacts": {
                "tables": [{"id": "comparison", "title": "Comparison", "columns": [], "rows": []}],
                "charts": [{"id": "growth", "title": "Growth", "type": "line", "x_key": "date", "value_format": "index", "data": [], "series": []}],
                "sources": [{"label": "SPY prices", "provider": "fixture", "as_of": "2026-08-11"}],
            },
        }

    monkeypatch.setattr(research_agent, "create_response", fake_response)
    monkeypatch.setattr(research_agent, "execute", fake_execute)
    result = research_agent.run(
        [{"role": "user", "content": "Which has held up better, SPY or QQQ, and why?"}],
        session_id=1,
        page_context={"path": "/company/SPY/charts", "ticker": "SPY"},
    )

    assert "risk-adjusted" in result["content"]
    assert result["tool_calls"][0]["tool"] == "compare_securities"
    assert result["artifact"]["tables"][0]["id"] == "comparison"
    assert result["artifact"]["charts"][0]["id"] == "growth"
    assert result["artifact"]["checks"][2]["status"] == "pass"
    assert requests[0]["tools"]
    assert requests[1]["input"][-1] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"ok":true,"securities":[{"ticker":"SPY","total_return":0.12}]}',
    }


def test_output_text_reads_responses_message_shape():
    assert research_agent._output_text({
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "Grounded answer"}]}]
    }) == "Grounded answer"


def test_duplicate_markdown_table_is_removed_for_interactive_artifact():
    content = "## Evidence\n\n| Ticker | Return |\n|---|---:|\n| SPY | 12% |\n\nInterpretation follows."
    assert research_agent._strip_pipe_tables(content) == "## Evidence\n\nInterpretation follows."


def test_global_session_persists_page_context_and_artifact(monkeypatch):
    observed = {}

    def fake_run(messages, *, session_id, page_context):
        observed["messages"] = messages
        observed["session_id"] = session_id
        observed["page_context"] = page_context
        return {
            "content": "AAPL cash conversion improved in the fixture.",
            "tool_calls": [{"tool": "get_cash_flow_analysis", "status": "ok"}],
            "artifact": {
                "tables": [{"id": "aapl-cash", "title": "AAPL cash flow", "columns": [], "rows": []}],
                "charts": [], "sources": [], "checks": [],
            },
        }

    monkeypatch.setattr("app.assistant.service.research_agent.run", fake_run)
    created = client.post("/api/v1/assistant/sessions", json={"title": "Test Global Research", "surface": "global"})
    assert created.status_code == 200
    session_id = created.json()["data"]["session"]["id"]
    assert created.json()["data"]["session"]["surface"] == "global"

    sent = client.post(
        f"/api/v1/assistant/sessions/{session_id}/messages",
        json={"message": "What changed here?", "page_context": {"path": "/company/AAPL/cash-flow", "ticker": "AAPL"}},
    )
    assert sent.status_code == 200
    assistant = sent.json()["data"]["messages"][-1]
    assert assistant["artifact"]["tables"][0]["id"] == "aapl-cash"
    assert observed["page_context"] == {"path": "/company/AAPL/cash-flow", "ticker": "AAPL"}
    assert observed["messages"][-1]["content"] == "What changed here?"

    fetched = client.get(f"/api/v1/assistant/sessions/{session_id}")
    assert fetched.json()["data"]["messages"][-1]["artifact"]["tables"][0]["id"] == "aapl-cash"


def test_assistant_budget_endpoint_is_authenticated_and_bounded():
    response = client.get("/api/v1/assistant/budget")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["limit_usd"] == 25.0
    assert 0 <= data["remaining_usd"] <= 25.0
