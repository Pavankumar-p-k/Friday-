from __future__ import annotations

import asyncio
import contextlib
import os
import signal

from friday.assistant_engine.runtime import build_default_engine


async def _event_printer(engine, *, enabled: bool) -> None:
    async for event in engine.events():
        if enabled:
            print(f"[{event.event_type.value}] {event.session_id} -> {event.payload}")


async def run_service(*, print_events: bool = True) -> None:
    engine = build_default_engine()
    stop_signal = asyncio.Event()

    def _request_stop() -> None:
        stop_signal.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_stop)

    await engine.start()
    printer_task = asyncio.create_task(
        _event_printer(engine, enabled=print_events),
        name="assistant-engine-event-printer",
    )
    try:
        await stop_signal.wait()
    finally:
        await engine.stop()
        printer_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await printer_task


def main() -> None:
    print_events = os.getenv("FRIDAY_ENGINE_PRINT_EVENTS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    asyncio.run(run_service(print_events=print_events))


if __name__ == "__main__":
    main()
