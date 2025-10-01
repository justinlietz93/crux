Short answer: **Yes—add them as event-driven reducers next to `ColdMap`.**
They should **never scan `W`**; they should fold only what the walkers/step loop already announce (e.g., `vt_touch`, edge samples, spikes/ΔW), keeping “void-faithful” guarantees for ADC/cartography and metrics. This matches your blueprint and the current Cold-Scout scaffolding. &#x20;

Below is a concrete, production-level plan + drop-in code.

---

## What to build (tell the agent)

**Create three reducers under `fum_rt/core/cortex/maps/`:**

1. **`HeatMap`** – short-half-life activity (recency-weighted usage).
2. **`ExcitationMap`** – same as `HeatMap` but integrates **only excitatory** activity.
3. **`InhibitionMap`** – same as `HeatMap` but integrates **only inhibitory** activity.

**Strict constraints (void-faithful):**

* **Input = events only.** No global reads of `W`, CSR, or adjacency (ADC and reducers are event-driven).&#x20;
* **Bounded memory/time.** Keep a capped working set (`keep_max`) and sample-based pruning (same discipline as `ColdMap`).&#x20;
* **Wire into engine loop.** Fold on the same bus events you already drain; do not introduce new global passes.&#x20;

**File worklist (exact):**

* `core/cortex/maps/base_decay_map.py` – shared bounded, exponential-decay map base (head/p95/p99).
* `core/cortex/maps/heatmap.py` – concrete `HeatMap`.
* `core/cortex/maps/excitationmap.py` – filters excitatory events only.
* `core/cortex/maps/inhibitionmap.py` – filters inhibitory events only.
* `core/proprioception/events.py` – ensure we have `SpikeEvent` (node, sign, amp) and optional `DeltaWEvent` (node, dW).
* `core/cortex/maps/__init__.py` – re-export the four: `ColdMap`, `HeatMap`, `ExcitationMap`, `InhibitionMap`.
* `core/engine.py` – instantiate + fold each tick; expose `evt_heat_*`, `evt_exc_*`, `evt_inh_*` in `snapshot()`.
* `runtime/loop.py` – no behavior change; keep bus-drain → reducers → metrics, consistent with your event-driven ADC rule.&#x20;

**Rationale & alignment**

* You already have **`ColdMap`** (monotonic in idle time, bounded, top-K head). We copy its bounded design and add exponential **decay-on-touch** maps to represent “heat.”&#x20;
* This honors your doc rule: cartography/metrics are **event-driven only; no global scans**.&#x20;
* E/I polarity is explicitly preserved in your TODO and system notes; `ExcitationMap`/`InhibitionMap` make this visible to the runtime without scanning.&#x20;

---

## Code — shared base (bounded decay map)

```python
# fum_rt/core/cortex/maps/base_decay_map.py
from __future__ import annotations
from typing import Dict, Iterable, List, Tuple
import math, random

class BaseDecayMap:
    """
    Bounded, per-node exponentially decaying accumulator.
    Void-faithful: fold() only consumes events; never scans global state.

    Score_t(node) = Score_{t-Δ} * 2^(-Δ/half_life_ticks) + sum(increments at t)

    Snapshot:
      - head_k top entries as [node, score] pairs (descending)
      - p95, p99, max summaries

    Blueprint tie-in: ADC/event-driven reducers (Rule 7); no W scans.  # see 09_First_Run_Prefixes.md
    """
    __slots__ = ("head_k", "half_life", "keep_max", "rng", "_val", "_last_tick")

    def __init__(self, head_k: int = 256, half_life_ticks: int = 200,
                 keep_max: int | None = None, seed: int = 0) -> None:
        self.head_k   = int(max(8, head_k))
        self.half_life = int(max(1, half_life_ticks))
        km = int(keep_max) if keep_max is not None else self.head_k * 16
        self.keep_max = int(max(self.head_k, km))
        self.rng = random.Random(int(seed))
        self._val: Dict[int, float] = {}
        self._last_tick: Dict[int, int] = {}

    # ----- core updates -----

    def _decay_to(self, node: int, tick: int) -> None:
        lt = self._last_tick.get(node)
        if lt is None:
            self._last_tick[node] = tick
            return
        dt = max(0, int(tick) - int(lt))
        if dt > 0:
            factor = 2.0 ** (-(dt / float(self.half_life)))
            self._val[node] *= factor
            self._last_tick[node] = tick

    def add(self, node: int, tick: int, inc: float) -> None:
        try:
            n = int(node); t = int(tick)
        except Exception:
            return
        if n < 0:
            return
        if n in self._val:
            self._decay_to(n, t)
            self._val[n] += float(inc)
        else:
            # initialize lazily with decay context
            self._val[n] = float(max(0.0, inc))
            self._last_tick[n] = t
