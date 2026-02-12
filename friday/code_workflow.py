from __future__ import annotations

from pathlib import Path
import subprocess

from friday.code_context import CodeContextIndex
from friday.config import Settings
from friday.llm import LocalLLMClient


class CodeWorkflow:
    def __init__(self, settings: Settings, llm: LocalLLMClient) -> None:
        self.settings = settings
        self.llm = llm
        self.index = CodeContextIndex(settings)
        self.root = settings.workspace_root.resolve()

    async def propose_patch(self, task: str, path: str | None = None) -> dict[str, object]:
        task = task.strip()
        if not task:
            return {"ok": False, "message": "task is required", "proposal": "", "citations": []}

        citations: list[str] = []
        context_parts: list[str] = []

        if path:
            candidate = self._resolve_candidate(path)
            if candidate and candidate.exists() and candidate.is_file():
                content = candidate.read_text(encoding="utf-8", errors="ignore")
                citations.append(self._to_citation(candidate))
                context_parts.append(f"FILE: {self._to_citation(candidate)}\n{content[:4000]}")
        else:
            matches = self.index.search(task)
            for match in matches:
                citations.append(match.path)
                context_parts.append(f"FILE: {match.path}\n{match.snippet}")

        context_blob = "\n\n".join(context_parts) if context_parts else "(no local context)"
        prompt = (
            "You are a code patch generator.\n"
            "Return a unified diff only.\n"
            "Task:\n"
            f"{task}\n\n"
            "Repository context:\n"
            f"{context_blob}\n\n"
            "Rules:\n"
            "- Use git unified diff format.\n"
            "- Keep changes minimal and safe.\n"
            "- If uncertain, include TODO comments in patch.\n"
        )
        proposal = await self.llm.generate(prompt, max_tokens=900)
        return {
            "ok": True,
            "proposal": proposal,
            "citations": citations,
        }

    async def apply_patch(self, patch: str, dry_run: bool = True) -> dict[str, object]:
        patch = patch.strip()
        if not patch:
            return {"ok": False, "applied": False, "dry_run": dry_run, "message": "patch is empty"}
        if len(patch) > 200_000:
            return {
                "ok": False,
                "applied": False,
                "dry_run": dry_run,
                "message": "patch too large",
            }

        check = self._run_git_apply_check(patch)
        if not check["ok"]:
            return {
                "ok": False,
                "applied": False,
                "dry_run": dry_run,
                "message": str(check["message"]),
            }

        if dry_run:
            return {
                "ok": True,
                "applied": False,
                "dry_run": True,
                "message": "patch check passed (dry run)",
            }

        apply_result = self._run_git_apply(patch)
        if not apply_result["ok"]:
            return {
                "ok": False,
                "applied": False,
                "dry_run": False,
                "message": str(apply_result["message"]),
            }
        return {
            "ok": True,
            "applied": True,
            "dry_run": False,
            "message": "patch applied",
        }

    def _resolve_candidate(self, path: str) -> Path | None:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = (self.root / candidate).resolve()
        else:
            candidate = candidate.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError:
            return None
        return candidate

    def _to_citation(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root))
        except ValueError:
            return str(path)

    def _run_git_apply_check(self, patch: str) -> dict[str, object]:
        try:
            result = subprocess.run(
                ["git", "apply", "--check", "-"],
                input=patch,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=25,
            )
            if result.returncode == 0:
                return {"ok": True, "message": "ok"}
            return {"ok": False, "message": (result.stderr or result.stdout or "apply check failed")}
        except Exception as exc:
            return {"ok": False, "message": f"apply check error: {exc}"}

    def _run_git_apply(self, patch: str) -> dict[str, object]:
        try:
            result = subprocess.run(
                ["git", "apply", "--whitespace=fix", "-"],
                input=patch,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return {"ok": True, "message": "ok"}
            return {"ok": False, "message": (result.stderr or result.stdout or "apply failed")}
        except Exception as exc:
            return {"ok": False, "message": f"apply error: {exc}"}

