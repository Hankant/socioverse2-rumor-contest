"""Shared primary-first circuit breaker; no model substitution or secret logs."""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from pathlib import Path
from model import dump, read_json

# Explicit provider refusals. Content/parameter/model errors never switch keys.
RATE_CODES = {1002, 1041, 1045, 2045, 2046, 2047, 2056, 2062, 2067}
SWITCH_CODES = RATE_CODES | {1000, 1001, 1004, 1008, 1024, 1033, 2049, 2053, 2064, 2066}
NO_SWITCH_CODES = {1026, 1027, 1039, 1040, 1042, 1046, 2013, 2014, 2022, 2057, 2061, 2068, 2069}


def can_switch(diagnostic):
    code = diagnostic.get("service_status_code")
    if code in NO_SWITCH_CODES:
        return False
    before_dispatch = diagnostic.get("timeout_phase") in {"ConnectTimeout", "PoolTimeout"} or "ConnectError" in diagnostic.get("exception_chain", [])
    # Post-dispatch timeouts may already have consumed tokens; no blind reissue.
    return (code in SWITCH_CODES or diagnostic.get("status_code") in {401, 402, 429, 500, 502, 503, 504, 529}
            or before_dispatch)


@dataclass(frozen=True)
class Route:
    slot: str
    probe: bool
    epoch: int


class KeyRouter:
    """One process shares this router across all agent threads.

    At/after the deadline, exactly one real decision request probes the primary.
    The other threads keep using backup. No idle background traffic or extra
    synthetic request is needed. Deadlines persist across ordinary restarts.
    """

    def __init__(self, path, event, interval=3600, clock=None):
        self.path, self.event = Path(path), event
        self.interval, self.clock = interval, clock or time.time
        self.lock = threading.RLock()
        self.probing = False
        self.epoch = 0
        self.state = read_json(self.path) if self.path.exists() else {
            "active_slot": "primary", "next_primary_probe_at": None, "switch_count": 0}
        if self.state.get("active_slot") not in ("primary", "backup"):
            raise ValueError("Invalid API routing state")
        deadline = self.state.get("next_primary_probe_at")
        if self.state["active_slot"] == "backup" and not isinstance(deadline, (int, float)):
            raise ValueError("Invalid primary probe deadline")

    def acquire(self):
        with self.lock:
            if self.state["active_slot"] == "primary":
                return Route("primary", False, self.epoch)
            if not self.probing and self.clock() >= self.state["next_primary_probe_at"]:
                self.probing = True
                route = Route("primary", True, self.epoch)
            else:
                route = Route("backup", False, self.epoch)
        if route.probe:
            self.event("primary_probe_started", api_key_slot="primary")
        return route

    def abort(self, route):
        """Release a probe that could not be sent; no failed API call is claimed."""
        with self.lock:
            if route.probe and route.epoch == self.epoch:
                self.probing = False

    def succeeded(self, route):
        restored = False
        with self.lock:
            if route.probe and route.epoch == self.epoch:
                self.probing = False
                self.state.update(active_slot="primary", next_primary_probe_at=None)
                self.epoch += 1
                dump(self.path, self.state)
                restored = True
        if restored:
            self.event("primary_restored", api_key_slot="primary")
            print("API router: primary recovered; new requests use primary.", flush=True)

    def failed(self, route, diagnostic):
        """True means retry the same prompt on the currently usable route."""
        changed = False
        with self.lock:
            if route.slot == "backup":
                # A backup call can finish after a successful primary probe.
                # Retry on the recovered primary instead of claiming both are down.
                return self.state["active_slot"] == "primary" and can_switch(diagnostic)
            if not can_switch(diagnostic):
                if route.probe and route.epoch == self.epoch:
                    # A sent probe that failed without a switchable refusal
                    # must not let other threads immediately probe again.
                    self.state["next_primary_probe_at"] = self.clock() + self.interval
                    dump(self.path, self.state)
                self.abort(route)
                return False
            # In-flight primary calls from before the first refusal must not
            # keep postponing the deadline or override a successful later probe.
            if route.epoch == self.epoch:
                self.probing = False
                self.state.update(active_slot="backup", next_primary_probe_at=self.clock() + self.interval)
                self.state["switch_count"] += 1
                self.epoch += 1
                dump(self.path, self.state)
                deadline = self.state["next_primary_probe_at"]
                changed = True
        if changed:
            self.event("primary_unavailable_using_backup", api_key_slot="primary",
                       next_primary_probe_at=deadline,
                       http_status=diagnostic.get("status_code"), service_status_code=diagnostic.get("service_status_code"))
            print("API router: primary unavailable -> backup; primary retry in 3600s.", flush=True)
        return True
