"""Errors of the summary package (plans/T5-ai-summary.md §1a)."""


class InvalidSummary(Exception):
    """The model's output failed parsing or validation; the service falls back to the template."""
