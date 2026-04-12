"""Observability baseline.

Provides:
- In-process metrics counters / histograms (thread-safe)
- OpenTelemetry-compatible span seam (no-op until a real OTel SDK is wired in)
- Prometheus text-format export via ``prometheus_text_export()``
- JSON summary via ``get_metrics_summary()``

Design
------
- No heavy dependency: all metrics are in-process Python data structures.
- Thread-safe writes via ``threading.Lock``.
- Prometheus text format is generated on demand from the in-process store.
- The ``trace_span`` context manager is syntactically OTel-compatible; it can
  be replaced with a real ``opentelemetry.trace.get_tracer(...)`` call later.

Metrics tracked
---------------
analysis_requests_total        (counter)   labels: symbol, status
analysis_latency_seconds       (histogram) labels: symbol
execution_attempts_total       (counter)   labels: intent, outcome
halt_blocked_total             (counter)
risk_blocked_total             (counter)
tool_gateway_calls_total       (counter)   labels: tool, outcome
job_runs_total                 (counter)   labels: job_type, status
ai_overlay_latency_seconds     (histogram) labels: source
paper_orders_total             (counter)   labels: status
strategy_evaluations_total     (counter)   labels: instrument, status
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from typing import Any


# ---------------------------------------------------------------------------
# Internal metric classes
# ---------------------------------------------------------------------------

class _Counter:
    def __init__(self) -> None:
        self._counts: dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()

    def inc(self, value: int = 1, **labels: Any) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            self._counts[key] += value

    def collect(self) -> dict[tuple, int]:
        with self._lock:
            return dict(self._counts)


class _Histogram:
    _DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

    def __init__(self, buckets: list[float] | None = None) -> None:
        self.buckets = sorted(buckets or self._DEFAULT_BUCKETS)
        self._obs: dict[tuple, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def observe(self, value: float, **labels: Any) -> None:
        key = tuple(sorted(labels.items()))
        with self._lock:
            buf = self._obs[key]
            buf.append(float(value))
            # Ring buffer: keep last 1000 per label set
            if len(buf) > 1000:
                self._obs[key] = buf[-1000:]

    def collect(self) -> dict[tuple, list[float]]:
        with self._lock:
            return {k: list(v) for k, v in self._obs.items()}


# ---------------------------------------------------------------------------
# Global metric registry
# ---------------------------------------------------------------------------

_METRICS: dict[str, _Counter | _Histogram] = {
    "analysis_requests_total": _Counter(),
    "analysis_latency_seconds": _Histogram(),
    "execution_attempts_total": _Counter(),
    "halt_blocked_total": _Counter(),
    "risk_blocked_total": _Counter(),
    "tool_gateway_calls_total": _Counter(),
    "job_runs_total": _Counter(),
    "ai_overlay_latency_seconds": _Histogram(),
    "ai_overlay_calls_total": _Counter(),
    "paper_orders_total": _Counter(),
    "strategy_evaluations_total": _Counter(),
}

_APP_START_SECONDS: float = time.time()


# ---------------------------------------------------------------------------
# Public instrumentation API
# ---------------------------------------------------------------------------

def record_analysis(
    symbol: str,
    status: str = "ok",
    latency_seconds: float | None = None,
) -> None:
    _METRICS["analysis_requests_total"].inc(symbol=symbol, status=status)  # type: ignore[union-attr]
    if latency_seconds is not None:
        _METRICS["analysis_latency_seconds"].observe(latency_seconds, symbol=symbol)  # type: ignore[union-attr]


def record_execution_attempt(intent: str, outcome: str) -> None:
    _METRICS["execution_attempts_total"].inc(intent=intent, outcome=outcome)  # type: ignore[union-attr]


def record_halt_blocked() -> None:
    _METRICS["halt_blocked_total"].inc()  # type: ignore[union-attr]


def record_risk_blocked() -> None:
    _METRICS["risk_blocked_total"].inc()  # type: ignore[union-attr]


def record_tool_call(tool: str, outcome: str = "ok") -> None:
    _METRICS["tool_gateway_calls_total"].inc(tool=tool, outcome=outcome)  # type: ignore[union-attr]


def record_job_run(job_type: str, status: str) -> None:
    _METRICS["job_runs_total"].inc(job_type=job_type, status=status)  # type: ignore[union-attr]


def record_ai_overlay_latency(source: str, latency_seconds: float) -> None:
    _METRICS["ai_overlay_latency_seconds"].observe(latency_seconds, source=source)  # type: ignore[union-attr]
    _METRICS["ai_overlay_calls_total"].inc(source=source)  # type: ignore[union-attr]


def record_paper_order(status: str = "created") -> None:
    _METRICS["paper_orders_total"].inc(status=status)  # type: ignore[union-attr]


def record_strategy_evaluation(instrument: str, status: str = "completed") -> None:
    _METRICS["strategy_evaluations_total"].inc(instrument=instrument, status=status)  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# OpenTelemetry-compatible span seam
# ---------------------------------------------------------------------------

class _NoOpSpan:
    """No-op span.  Replace the body of ``trace_span`` with a real OTel call later."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._start = time.monotonic()

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self._start


def trace_span(name: str) -> _NoOpSpan:
    """Return an OTel-compatible context-manager span.
    Replace this with ``opentelemetry.trace.get_tracer(__name__).start_as_current_span(name)``
    when a real OTel SDK is configured.
    """
    return _NoOpSpan(name)


# ---------------------------------------------------------------------------
# Prometheus text export
# ---------------------------------------------------------------------------

def _fmt_labels(key: tuple) -> str:
    if not key:
        return ""
    return "{" + ",".join(f'{k}="{v}"' for k, v in key) + "}"


def prometheus_text_export() -> str:
    """Render all metrics in Prometheus text exposition format."""
    lines: list[str] = []
    now_ms = int(time.time() * 1000)

    # Uptime gauge
    lines.append("# TYPE process_uptime_seconds gauge")
    lines.append(f"process_uptime_seconds {round(time.time() - _APP_START_SECONDS, 1)} {now_ms}")

    for name, metric in _METRICS.items():
        if isinstance(metric, _Counter):
            lines.append(f"# TYPE {name} counter")
            for labels, count in metric.collect().items():
                lines.append(f"{name}{_fmt_labels(labels)} {count} {now_ms}")

        elif isinstance(metric, _Histogram):
            lines.append(f"# TYPE {name} histogram")
            for labels, obs in metric.collect().items():
                if not obs:
                    continue
                count = len(obs)
                total = sum(obs)
                fmt = _fmt_labels(labels)
                lines.append(f"{name}_count{fmt} {count} {now_ms}")
                lines.append(f"{name}_sum{fmt} {round(total, 6)} {now_ms}")
                for bucket in metric.buckets:
                    bc = sum(1 for v in obs if v <= bucket)
                    blabels = dict(labels)
                    blabels["le"] = str(bucket)
                    bfmt = "{" + ",".join(f'{k}="{v}"' for k, v in sorted(blabels.items())) + "}"
                    lines.append(f"{name}_bucket{bfmt} {bc} {now_ms}")
                ilabels = dict(labels)
                ilabels["le"] = "+Inf"
                ifmt = "{" + ",".join(f'{k}="{v}"' for k, v in sorted(ilabels.items())) + "}"
                lines.append(f"{name}_bucket{ifmt} {count} {now_ms}")

    return "\n".join(lines) + "\n"


def get_metrics_summary() -> dict:
    """Return a JSON-friendly summary for the /metrics/summary endpoint."""
    summary: dict[str, Any] = {
        "uptime_seconds": round(time.time() - _APP_START_SECONDS, 1),
    }
    for name, metric in _METRICS.items():
        if isinstance(metric, _Counter):
            counts = metric.collect()
            summary[name] = {
                "type": "counter",
                "total": sum(counts.values()),
                "by_label": {str(k): v for k, v in counts.items()},
            }
        elif isinstance(metric, _Histogram):
            obs_data = metric.collect()
            summary[name] = {"type": "histogram", "label_sets": []}
            for labels, obs in obs_data.items():
                if obs:
                    summary[name]["label_sets"].append({
                        "labels": dict(labels),
                        "count": len(obs),
                        "mean_seconds": round(sum(obs) / len(obs), 4),
                        "max_seconds": round(max(obs), 4),
                        "p50": round(sorted(obs)[len(obs) // 2], 4),
                    })
    return summary
