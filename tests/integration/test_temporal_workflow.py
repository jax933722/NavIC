"""Live Temporal: run a CrawlWorkflow through a real worker against a real dev
server, crawling a local fixture. Skips if temporalio or the temporal binary is
absent. This exercises the SAME activity the InProcessExecutor runs — only the
execution substrate differs."""

from __future__ import annotations

import asyncio
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("temporalio")

_HTML = (
    b"<html><head><title>Acme</title>"
    b"<meta property='og:site_name' content='Acme'/></head>"
    b"<body>We are hiring SDRs across sales. Careers.</body></html>"
)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_HTML)

    def log_message(self, *args):
        pass


@pytest.fixture
def fixture_site():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/"
    srv.shutdown()


def test_crawl_workflow_runs_on_real_temporal(fixture_site):
    temporal_bin = shutil.which("temporal")
    if not temporal_bin:
        pytest.skip("temporal dev-server binary not on PATH")

    from temporalio.client import Client
    from temporalio.testing import WorkflowEnvironment
    from temporalio.worker import Worker

    from scheduler.workflows import CrawlWorkflow, run_crawl_activity

    async def _run() -> int:
        env: WorkflowEnvironment = await WorkflowEnvironment.start_local(
            dev_server_existing_path=temporal_bin
        )
        try:
            client: Client = env.client
            async with Worker(
                client,
                task_queue="navic-crawls",
                workflows=[CrawlWorkflow],
                activities=[run_crawl_activity],
            ):
                return await client.execute_workflow(
                    CrawlWorkflow.run,
                    args=["company_web", fixture_site],
                    id="crawl-test-1",
                    task_queue="navic-crawls",
                )
        finally:
            await env.shutdown()

    candidates = asyncio.run(_run())
    # The fixture page yields a company + a hiring signal (>= 2 candidates).
    assert candidates >= 2
