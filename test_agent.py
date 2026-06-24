from __future__ import annotations

from agent.core import SupportAgent


def run_scenario(agent: SupportAgent, title: str, message: str) -> None:
    print(f"=== {title} ===")
    history: list[dict[str, object]] = []
    answer, _tools_used = agent.chat(message, history)
    print(f"FINAL ANSWER: {answer}")
    print()


def main() -> None:
    agent = SupportAgent()

    run_scenario(agent, "Skenario 1", "Bagaimana cara refund?")
    run_scenario(agent, "Skenario 2", "Status order ORD123?")
    run_scenario(agent, "Skenario 3", "Saya mau bicara dengan manusia")


if __name__ == "__main__":
    main()
