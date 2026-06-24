from __future__ import annotations

import json
import sys
import time
from argparse import ArgumentParser
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import agent.core as core  # noqa: E402
from agent.session import SessionManager  # noqa: E402
from tools import handlers  # noqa: E402


SupportAgent = core.SupportAgent


GOLDEN_SET_PATH = Path(__file__).with_name("golden_set.json")
RESULTS_PATH = Path(__file__).with_name("results.json")
REFUSAL_KEYWORDS = [
    "maaf",
    "tidak bisa",
    "di luar",
    "topik support",
    "customer support",
    "order",
    "refund",
    "shipping",
    "akun",
    "support",
]
QUOTA_ERROR_MARKERS = [
    "quota",
    "rate-limit",
    "rate limit",
    "ResourceExhausted",
    "429",
]


def load_golden_set() -> list[dict[str, Any]]:
    return json.loads(GOLDEN_SET_PATH.read_text(encoding="utf-8"))


def normalize_messages(case_input: str | list[str]) -> list[str]:
    if isinstance(case_input, str):
        return [case_input]
    return case_input


def response_has_refusal(response: str) -> bool:
    normalized = response.lower()
    return any(keyword in normalized for keyword in REFUSAL_KEYWORDS)


def tool_match(expected_tool: str | None, called_tools: list[str], response: str) -> tuple[bool, str]:
    if expected_tool is None:
        if called_tools:
            return False, f"expected no tool call, got {called_tools}"
        if not response_has_refusal(response):
            return False, "response did not contain a clear refusal or support redirect"
        return True, "out-of-scope refusal matched"

    if expected_tool in called_tools:
        return True, f"called expected tool {expected_tool}"

    return False, f"expected tool {expected_tool}, got {called_tools or 'no tool calls'}"


def install_tool_capture(called_tools: list[str]) -> dict[str, Callable[..., Any]]:
    original_tool_map = handlers.TOOL_MAP.copy()

    def wrap_tool(name: str, func: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            called_tools.append(name)
            return func(*args, **kwargs)

        return wrapped

    for tool_name, tool_func in original_tool_map.items():
        handlers.TOOL_MAP[tool_name] = wrap_tool(tool_name, tool_func)

    return original_tool_map


def log_file_offset() -> int:
    path = handlers.agent_log_path()
    if not path.exists():
        return 0
    return path.stat().st_size


def read_logged_tools(offset: int) -> list[str]:
    path = handlers.agent_log_path()
    if not path.exists():
        return []

    tools: list[str] = []
    with path.open("r", encoding="utf-8") as log_file:
        log_file.seek(offset)
        for line in log_file:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            tool_name = record.get("tool")
            if isinstance(tool_name, str):
                tools.append(tool_name)
    return tools


def restore_tool_map(original_tool_map: dict[str, Callable[..., Any]]) -> None:
    handlers.TOOL_MAP.clear()
    handlers.TOOL_MAP.update(original_tool_map)


def run_case(agent: SupportAgent, case: dict[str, Any]) -> dict[str, Any]:
    captured_tools: list[str] = []
    original_tool_map = install_tool_capture(captured_tools)
    log_offset = log_file_offset()
    session_manager = SessionManager()
    session_id = f"eval-{case['id']}"
    messages = normalize_messages(case["input"])
    final_response = ""
    error: str | None = None
    started_at = time.perf_counter()

    try:
        for message in messages:
            history = session_manager.get_history(session_id)
            final_response, _tools_used = agent.chat(message, history)
    except Exception as exc:
        error = str(exc)
    finally:
        restore_tool_map(original_tool_map)

    logged_tools = read_logged_tools(log_offset)
    called_tools = logged_tools or captured_tools
    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    passed, reason = tool_match(case.get("expected_tool"), called_tools, final_response)
    if error is not None:
        passed = False
        reason = f"error: {error}"

    return {
        "id": case["id"],
        "category": case["category"],
        "input": case["input"],
        "expected_tool": case.get("expected_tool"),
        "called_tools": called_tools,
        "logged_tools": logged_tools,
        "captured_tools": captured_tools,
        "latency_ms": latency_ms,
        "response": final_response,
        "passed": passed,
        "reason": reason,
        "error": error,
    }


def is_quota_error(result: dict[str, Any]) -> bool:
    error = str(result.get("error") or "").lower()
    reason = str(result.get("reason") or "").lower()
    return any(marker.lower() in error or marker.lower() in reason for marker in QUOTA_ERROR_MARKERS)


def build_output(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for result in results if result["passed"])
    failed_cases = [result for result in results if not result["passed"]]
    accuracy = round((passed / total) * 100, 2) if total else 0.0
    avg_latency_ms = round(
        sum(result["latency_ms"] for result in results) / total,
        2,
    ) if total else 0.0

    return {
        "summary": {
            "total": total,
            "passed": passed,
            "failed": len(failed_cases),
            "accuracy_percent": accuracy,
            "avg_latency_ms": avg_latency_ms,
        },
        "results": results,
    }


def save_results(results: list[dict[str, Any]]) -> None:
    RESULTS_PATH.write_text(
        json.dumps(build_output(results), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def parse_args() -> Any:
    parser = ArgumentParser(description="Run support-agent golden-set evals.")
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N cases.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    golden_set = load_golden_set()
    if args.limit is not None:
        golden_set = golden_set[: args.limit]

    core.MAX_RATE_LIMIT_RETRIES = 0
    print(f"Loaded {len(golden_set)} eval cases.", flush=True)
    agent = SupportAgent()
    results = []

    for case in golden_set:
        print(f"Running case {case['id']}: {case['category']}", flush=True)
        result = run_case(agent, case)
        results.append(result)
        save_results(results)
        status = "PASS" if result["passed"] else "FAIL"
        print(f"  {status} - {result['reason']} ({result['latency_ms']} ms)", flush=True)
        if is_quota_error(result):
            print("Stopping early because the provider quota/rate limit was reached.", flush=True)
            break

    output = build_output(results)
    summary = output["summary"]
    failed_cases = [result for result in results if not result["passed"]]
    save_results(results)

    print()
    print("=== Eval Summary ===", flush=True)
    print(
        f"Accuracy: {summary['accuracy_percent']}% "
        f"({summary['passed']}/{summary['total']})",
        flush=True,
    )
    print(f"Average latency: {summary['avg_latency_ms']} ms", flush=True)

    if failed_cases:
        print("Failed cases:", flush=True)
        for result in failed_cases:
            print(
                f"- id={result['id']} category={result['category']} "
                f"reason={result['reason']}",
                flush=True,
            )
    else:
        print("All cases passed.", flush=True)

    print(f"Saved details to {RESULTS_PATH}", flush=True)


if __name__ == "__main__":
    main()
