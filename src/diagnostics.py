"""
QuantMap — diagnostics.py

Core diagnostic infrastructure.
Defines shared readiness models, status enums, and check result structures
used by 'init', 'doctor', and 'self-test'.
"""

from __future__ import annotations

from enum import Enum, auto
from dataclasses import dataclass
from typing import List

class Status(Enum):
    PASS = auto()
    WARN = auto()
    FAIL = auto()
    SKIP = auto()
    INFO = auto()

class Readiness(Enum):
    READY = auto()
    WARNINGS = auto()
    BLOCKED = auto()

@dataclass
class CheckResult:
    label: str
    status: Status
    message: str = ""
    why_it_matters: str = ""
    recommendation: str = ""
    is_fixable: bool = False

    def to_rich_line(self) -> str:
        """Internal helper for CLI rendering."""
        from src import ui
        sym = {
            Status.PASS: f"[green]{ui.SYM_OK}[/green]",
            Status.WARN: f"[yellow]{ui.SYM_WARN}[/yellow]",
            Status.FAIL: f"[red]{ui.SYM_FAIL}[/red]",
            Status.SKIP: "[dim]-[/dim]",
            Status.INFO: "[cyan]i[/cyan]"
        }.get(self.status, " ")
        
        color = {
            Status.PASS: "green",
            Status.WARN: "yellow",
            Status.FAIL: "red",
            Status.SKIP: "dim",
            Status.INFO: "cyan"
        }.get(self.status, "white")
        
        return f"  {sym} [{color}]{self.label}[/{color}]: {self.message}"

class DiagnosticReport:
    """A collection of CheckResults that collapses into a final Readiness state."""
    
    def __init__(self, title: str):
        self.title = title
        self.results: List[CheckResult] = []

    def add(self, result: CheckResult):
        self.results.append(result)

    @property
    def readiness(self) -> Readiness:
        """Determine final readiness state based on children."""
        if any(r.status == Status.FAIL for r in self.results):
            return Readiness.BLOCKED
        if any(r.status == Status.WARN for r in self.results):
            return Readiness.WARNINGS
        return Readiness.READY

    def print_summary(
        self,
        *,
        ready_label: str = "ENVIRONMENT READY",
        warnings_label: str = "READY WITH WARNINGS",
        blocked_label: str = "BLOCKED",
    ):
        """Standardized CLI summary rendering."""
        from src import ui
        console = ui.get_console()
        
        ui.print_banner(self.title)
        
        # Print results grouped by status (optional, but let's do linear for now)
        for r in self.results:
            console.print(r.to_rich_line())
            if r.status in (Status.WARN, Status.FAIL):
                if r.why_it_matters:
                    console.print(f"    [dim]Why it matters: {r.why_it_matters}[/dim]")
                if r.recommendation:
                    console.print(f"    [blue]Recommendation: {r.recommendation}[/blue]")

        console.print("\n" + ui.SYM_DIVIDER * 60)
        
        final = self.readiness
        if final == Readiness.READY:
            console.print(f"[bold green]{ui.SYM_OK} {ready_label}[/bold green]")
        elif final == Readiness.WARNINGS:
            console.print(f"[bold yellow]{ui.SYM_WARN} {warnings_label}[/bold yellow]")
        else:
            console.print(f"[bold red]{ui.SYM_FAIL} {blocked_label}[/bold red]")
        console.print("")
