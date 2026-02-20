from __future__ import annotations

from friday.assistant_engine.interfaces import IntentClassifier
from friday.assistant_engine.models import AssistantMode, IntentResult, IntentType


class RuleBasedIntentClassifier(IntentClassifier):
    async def classify(self, text: str) -> IntentResult:
        lowered = text.lower().strip()
        if not lowered:
            return IntentResult(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                mode=AssistantMode.CHAT,
                extracted_command="",
            )

        if any(token in lowered for token in ("code", "function", "python", "bug", "refactor")):
            return IntentResult(
                intent=IntentType.CODE,
                confidence=0.81,
                mode=AssistantMode.CODE,
                extracted_command=text.strip(),
            )

        if any(
            token in lowered
            for token in (
                "open ",
                "launch ",
                "play ",
                "set reminder",
                "remind me",
                "run ",
                "execute ",
            )
        ):
            return IntentResult(
                intent=IntentType.AUTOMATION,
                confidence=0.86,
                mode=AssistantMode.ACTION,
                extracted_command=text.strip(),
            )

        return IntentResult(
            intent=IntentType.CHAT,
            confidence=0.75,
            mode=AssistantMode.CHAT,
            extracted_command=text.strip(),
        )
