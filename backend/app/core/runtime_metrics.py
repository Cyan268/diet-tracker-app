from collections import Counter, defaultdict, deque
from collections.abc import Callable, Collection
from dataclasses import dataclass
from threading import Lock

LATENCY_BUCKETS_MS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000)
MAX_SAMPLES = 10_000


@dataclass(frozen=True)
class HistogramSnapshot:
    count: int
    sum_ms: int
    buckets: dict[str, int]


class RuntimeMetrics:
    """Process-local, low-cardinality metrics.

    Database-backed operational metrics are collected separately. Keeping this
    registry process-local makes request instrumentation unable to break a
    business request when the monitoring stack is unavailable.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._http_requests: Counter[tuple[str, str, int]] = Counter()
        self._http_latency: dict[tuple[str, str], deque[int]] = defaultdict(
            lambda: deque(maxlen=MAX_SAMPLES)
        )
        self._db_wait: deque[int] = deque(maxlen=MAX_SAMPLES)
        self._sync_results: deque[int] = deque(maxlen=MAX_SAMPLES)
        self._sync_conflicts = 0

    def record_http(self, method: str, endpoint: str, status_code: int, latency_ms: int) -> None:
        with self._lock:
            self._http_requests[(method, endpoint, status_code)] += 1
            self._http_latency[(method, endpoint)].append(max(latency_ms, 0))

    def record_db_pool_wait(self, duration_ms: int) -> None:
        with self._lock:
            self._db_wait.append(max(duration_ms, 0))

    def record_sync_page(self, result_count: int) -> None:
        with self._lock:
            self._sync_results.append(max(result_count, 0))

    def record_sync_conflict(self) -> None:
        with self._lock:
            self._sync_conflicts += 1

    @staticmethod
    def _histogram(values: Collection[int]) -> HistogramSnapshot:
        return HistogramSnapshot(
            count=len(values),
            sum_ms=sum(values),
            buckets={
                str(bound): sum(value <= bound for value in values) for bound in LATENCY_BUCKETS_MS
            }
            | {"+Inf": len(values)},
        )

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            requests = [
                {
                    "method": method,
                    "endpoint": endpoint,
                    "status_code": status_code,
                    "count": count,
                }
                for (method, endpoint, status_code), count in sorted(self._http_requests.items())
            ]
            latency = [
                {
                    "method": method,
                    "endpoint": endpoint,
                    **self._histogram(values).__dict__,
                }
                for (method, endpoint), values in sorted(self._http_latency.items())
            ]
            return {
                "scope": "current_process_since_start",
                "http_requests": requests,
                "http_latency_ms": latency,
                "db_pool_wait_ms": self._histogram(self._db_wait).__dict__,
                "sync": {
                    "pages": len(self._sync_results),
                    "results": sum(self._sync_results),
                    "conflicts": self._sync_conflicts,
                },
            }

    def reset_for_tests(self) -> None:
        with self._lock:
            self._http_requests.clear()
            self._http_latency.clear()
            self._db_wait.clear()
            self._sync_results.clear()
            self._sync_conflicts = 0


runtime_metrics = RuntimeMetrics()


def record_safely(recorder: Callable[..., None], *args: object) -> None:
    """Make best-effort telemetry incapable of failing a business operation."""

    try:
        recorder(*args)
    except Exception:  # Monitoring must remain fail-open and has no business side effects.
        return
