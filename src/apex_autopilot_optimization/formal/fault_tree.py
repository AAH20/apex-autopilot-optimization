"""Fault tree analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FaultTree:
    """A fault tree with gates and basic events."""

    id: str
    name: str
    top_event: str
    gates: list[dict[str, Any]]
    basic_events: list[dict[str, Any]]

    def evaluate_tree(self, inputs: dict[str, bool]) -> bool:
        """Evaluate the top gate given boolean inputs for events."""
        event_values = {e["id"]: inputs.get(e["id"], False) for e in self.basic_events}

        def eval_gate(gate: dict[str, Any]) -> bool:
            gate_inputs = []
            for i in gate.get("inputs", []):
                sub = next((g for g in self.gates if g.get("id") == i), None)
                if sub is not None:
                    gate_inputs.append(eval_gate(sub))
                else:
                    gate_inputs.append(inputs.get(i, event_values.get(i, False)))
            gate_type = gate.get("type", "AND").upper()
            if gate_type == "AND":
                return all(gate_inputs)
            if gate_type == "OR":
                return any(gate_inputs)
            return all(gate_inputs)

        top_gate = self.gates[0] if self.gates else None
        return eval_gate(top_gate) if top_gate else False

    def get_minimal_cuts(self) -> list[set[str]]:
        """Compute minimal cut sets of the fault tree."""
        event_ids = {e["id"] for e in self.basic_events}

        def cuts(gate: dict[str, Any]) -> list[set[str]]:
            gate_inputs = gate.get("inputs", [])
            gate_type = gate.get("type", "AND").upper()
            input_cuts: list[list[set[str]]] = []
            for i in gate_inputs:
                if i in event_ids:
                    input_cuts.append([{i}])
                else:
                    sub = next((g for g in self.gates if g.get("id") == i), None)
                    input_cuts.append(cuts(sub) if sub else [{i}])
            if gate_type == "AND":
                return [set().union(*combo) for combo in _combinations(input_cuts)]
            if gate_type == "OR":
                return [c for cuts_list in input_cuts for c in cuts_list]
            return []

        top_gate = self.gates[0] if self.gates else None
        return cuts(top_gate) if top_gate else []

    def get_probability(self, inputs: dict[str, float]) -> float:
        """Compute top-event probability given event probabilities."""
        event_probs = {e["id"]: inputs.get(e["id"], 0.0) for e in self.basic_events}

        def gate_prob(gate: dict[str, Any]) -> float:
            gate_type = gate.get("type", "AND").upper()
            probs = []
            for i in gate.get("inputs", []):
                sub = next((g for g in self.gates if g.get("id") == i), None)
                probs.append(gate_prob(sub) if sub else event_probs.get(i, 0.0))
            if gate_type == "OR":
                # Exact P(A OR B) via inclusion-exclusion for small sets
                result = 0.0
                for r in range(1, len(probs) + 1):
                    for combo in _combinations([probs], r=r):
                        term = 1.0
                        for p in combo:
                            term *= p
                        result += term if r % 2 == 1 else -term
                return result
            result = 1.0
            for p in probs:
                result *= p
            return result

        top_gate = self.gates[0] if self.gates else None
        return gate_prob(top_gate) if top_gate else 0.0


def _combinations(lists: list[list[Any]], r: int | None = None) -> Any:
    """Cartesian product helper (or r-combinations of a single list)."""
    if r is not None:
        from itertools import combinations as comb

        return comb(lists[0], r)
    from itertools import product

    return product(*lists)
