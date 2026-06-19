from __future__ import annotations

from agent.core import SupportAgent
from agent.session import SessionManager


SCENARIOS = [
    {
        "title": "Out of scope",
        "messages": ["Tolong jelaskan cara bikin nasi goreng."],
    },
    {
        "title": "Knowledge base no relevant info",
        "messages": ["Apa kebijakan refund untuk produk teleportasi?"],
    },
    {
        "title": "Frustrated customer after two interactions",
        "messages": [
            "Refund saya belum masuk.",
            "Saya tidak puas, ini komplain kedua saya.",
        ],
    },
]


def main() -> None:
    agent = SupportAgent()
    sessions = SessionManager()

    for index, scenario in enumerate(SCENARIOS, start=1):
        session_id = f"guardrail-test-{index}"
        print(f"=== {scenario['title']} ===")

        for message in scenario["messages"]:
            print(f"USER: {message}")
            answer = agent.chat(message, sessions.get_history(session_id))
            print(f"AGENT: {answer}")

        print()


if __name__ == "__main__":
    main()
