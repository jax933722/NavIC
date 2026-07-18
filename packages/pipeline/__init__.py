"""pipeline — wires candidates through resolution, signals, and opportunities.

The M0 pipeline is a synchronous orchestrator over repositories (blueprint §14).
When the durable log + workers land it becomes event-driven consumers, but the
stage logic is identical — this is the reference implementation of the spine.
"""

from .m0 import M0Pipeline, PipelineResult

__all__ = ["M0Pipeline", "PipelineResult"]
