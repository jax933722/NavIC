"""ingestion — raw persistence + polite fetching (spec 03 §4).

The runtime owns the cross-cutting concerns; collectors stay source-specific.
Adapters here follow the interface/adapter pattern so tests run without infra
(InMemory/LocalFile) while production uses httpx + S3/MinIO.
"""

from .fetch import FetchClient, HttpFetchClient, RawResponse, StubFetchClient
from .raw_store import InMemoryRawStore, LocalFileRawStore, RawRef, RawStore

__all__ = [
    "RawResponse",
    "FetchClient",
    "HttpFetchClient",
    "StubFetchClient",
    "RawRef",
    "RawStore",
    "InMemoryRawStore",
    "LocalFileRawStore",
]
