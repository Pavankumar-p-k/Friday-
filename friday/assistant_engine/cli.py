from __future__ import annotations

import asyncio

from friday.assistant_engine.runtime import build_default_engine


async def _print_events(engine_session) -> None:
    async for event in engine_session.events():
        print(f"[{event.event_type.value}] {event.session_id} -> {event.payload}")


async def run_interactive() -> None:
    engine = build_default_engine()
    await engine.start()
    printer_task = asyncio.create_task(_print_events(engine))
    print("Assistant engine started. Type text, or '/quit' to exit.")
    try:
        while True:
            line = await asyncio.to_thread(input, "assistant> ")
            if not line:
                continue
            if line.strip().lower() in {"/quit", "quit", "exit"}:
                break
            await engine.submit_text(session_id="cli-session", text=line, is_final=True)
    finally:
        await engine.stop()
        await asyncio.wait_for(printer_task, timeout=2)


def main() -> None:
    asyncio.run(run_interactive())


if __name__ == "__main__":
    main()
