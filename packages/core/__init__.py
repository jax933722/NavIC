"""core — cross-cutting foundations for the platform.

Config, IDs, errors, logging, and the event-bus interface. Every other
package may import from `core`; `core` imports from nothing in the domain.
See docs/specs/... and docs/FOLDER_STRUCTURE.md.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
