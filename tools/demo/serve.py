"""Serve the NavIC API pre-seeded with the demo dataset (used by the Docker demo).

    python -m tools.demo.serve            # serves on 0.0.0.0:8000

Forces the in-memory backend, seeds it from tools/demo/data, then serves the same
FastAPI app the production entrypoint uses. Host/port come from HOST/PORT env vars.
"""

from __future__ import annotations

import os
from collections import Counter


def main() -> None:
    os.environ["NAVIC_API_BACKEND"] = "memory"
    import uvicorn
    from apps.api.main import app

    from .seed import seed

    totals = seed(app.state.provider._bundle.pipeline)
    tiers = Counter(o.tier for o in app.state.provider._bundle.opportunities.list())
    print(f"[demo] seeded {totals} | tiers={dict(tiers)}", flush=True)

    uvicorn.run(app, host=os.environ.get("HOST", "0.0.0.0"),
                port=int(os.environ.get("PORT", "8000")), log_level="info")


if __name__ == "__main__":
    main()
