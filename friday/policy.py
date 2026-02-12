from __future__ import annotations

from friday.config import Settings
from friday.schemas import PlanStep, PolicyDecision, RiskLevel


class PolicyEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def evaluate(self, step: PlanStep) -> PolicyDecision:
        if step.tool is None:
            return PolicyDecision(
                allowed=True,
                risk=RiskLevel.LOW,
                needs_approval=False,
                reason="Direct answer only.",
            )

        if step.tool not in self.settings.allowed_tools:
            return PolicyDecision(
                allowed=False,
                risk=RiskLevel.HIGH,
                needs_approval=True,
                reason=f"Tool '{step.tool}' is not allowlisted.",
            )

        if step.tool == "open_app":
            app_name = str(step.args.get("app_name", "")).strip().lower()
            if app_name not in self.settings.allowed_apps:
                return PolicyDecision(
                    allowed=False,
                    risk=RiskLevel.HIGH,
                    needs_approval=True,
                    reason=f"App '{app_name}' is not allowlisted.",
                )
            return PolicyDecision(
                allowed=True,
                risk=RiskLevel.LOW,
                needs_approval=False,
                reason="Allowlisted app launch.",
            )

        if step.tool == "media_control":
            return PolicyDecision(
                allowed=True,
                risk=RiskLevel.LOW,
                needs_approval=False,
                reason="Media control is low risk.",
            )

        if step.tool == "reminder":
            return PolicyDecision(
                allowed=True,
                risk=RiskLevel.LOW,
                needs_approval=False,
                reason="Reminder operations are low risk.",
            )

        if step.tool == "code_agent":
            write_files = bool(step.args.get("write_files", False))
            run_shell = bool(step.args.get("run_shell", False))

            if run_shell:
                return PolicyDecision(
                    allowed=False,
                    risk=RiskLevel.HIGH,
                    needs_approval=True,
                    reason="Code agent shell execution is blocked by policy.",
                )
            if write_files:
                return PolicyDecision(
                    allowed=True,
                    risk=RiskLevel.MEDIUM,
                    needs_approval=True,
                    reason="File writes require explicit approval.",
                )
            return PolicyDecision(
                allowed=True,
                risk=RiskLevel.MEDIUM,
                needs_approval=True,
                reason="Code generation requires approval by default.",
            )

        if step.tool == "safe_shell":
            command = str(step.args.get("command", "")).strip()
            if not command:
                return PolicyDecision(
                    allowed=False,
                    risk=RiskLevel.HIGH,
                    needs_approval=True,
                    reason="Shell command is missing.",
                )
            for prefix in self.settings.allowed_shell_prefixes:
                if command.lower().startswith(prefix.lower()):
                    return PolicyDecision(
                        allowed=True,
                        risk=RiskLevel.MEDIUM,
                        needs_approval=True,
                        reason="Allowlisted shell command requires explicit approval.",
                    )
            return PolicyDecision(
                allowed=False,
                risk=RiskLevel.HIGH,
                needs_approval=True,
                reason="Shell command prefix is not allowlisted.",
            )

        return PolicyDecision(
            allowed=False,
            risk=RiskLevel.HIGH,
            needs_approval=True,
            reason="No policy rule available.",
        )
