"""The discovery dispatcher: search / describe / invoke.

Hand-rolled rather than provider-native, so the arm is byte-identical across
providers. A native facility on one provider and not another would make the
cross-provider comparison meaningless — and the whole point of RQ5 is that the
comparison holds.

The standing objection is that this benchmarks our dispatcher rather than the
topology. That is answered by *also* running provider-native tool search as a
separately labelled variant: the delta between them measures how much of the
result is ours. Absorbing the objection would have been the weaker choice.

Ranking is frozen at build time so repeated runs see identical results — real
APIs rank, and omitting ranking would bias against the discovery arms that would
naturally lean on it.

Contract: archive/reference/decisions.md O2; archive/reference/packaging-axes.md#axes
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .generate import ApiSpec, Operation, _json_schema
from .axes import SchemaDetail

SEARCH = "search_operations"
DESCRIBE = "describe_operation"
INVOKE = "invoke_operation"


def _terms(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@dataclass
class OperationIndex:
    """A frozen BM25-ish index over the operation surface.

    Built once from the spec, so ranking is deterministic across runs and
    repeats. Determinism is not a nicety here: if search results drifted, a
    variance measurement would be measuring the index, not the model.
    """

    spec: ApiSpec
    _docs: dict[str, list[str]] = field(default_factory=dict)
    _df: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        for op in self.spec.operations:
            text = " ".join([
                op.operation_id, op.path, op.method,
                op.summary, op.description,
                *[str(p.get("name", "")) for p in op.parameters],
            ])
            terms = _terms(text)
            self._docs[op.operation_id] = terms
            for term in set(terms):
                self._df[term] += 1

    def search(self, query: str, limit: int = 10) -> list[tuple[Operation, float]]:
        q = _terms(query)
        n = len(self._docs) or 1
        scored: list[tuple[Operation, float]] = []

        for op in self.spec.operations:
            terms = self._docs[op.operation_id]
            if not terms:
                continue
            counts = Counter(terms)
            score = 0.0
            for term in q:
                if term not in counts:
                    continue
                idf = math.log(1 + n / (1 + self._df[term]))
                score += idf * counts[term] / len(terms)
            if score > 0:
                scored.append((op, score))

        # Ties broken by operation id, so the order is total and reproducible.
        scored.sort(key=lambda pair: (-pair[1], pair[0].operation_id))
        return scored[:limit]


@dataclass
class MetaToolDispatcher:
    """Implements the triad on top of any per-operation executor.

    Wraps rather than replaces: ``invoke_operation`` delegates to the same
    executor the eager-all arm uses, so the two arms differ *only* in how the
    model finds an operation — which is exactly the comparison RQ2 asks for.
    """

    spec: ApiSpec
    inner: Any
    schema_detail: SchemaDetail = SchemaDetail.STANDARD
    index: OperationIndex | None = None
    #: Operations the model has actually described. Not enforced — a model that
    #: invokes without describing is making a real choice, and the trace records
    #: it as discovery overhead rather than being blocked.
    described: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.index = self.index or OperationIndex(self.spec)

    def handles(self, tool: str | None) -> bool:
        return tool in (SEARCH, DESCRIBE, INVOKE)

    def invoke(self, call: Any) -> Any:
        from .packaging import Call, Result

        if call.tool == SEARCH:
            return self._search(call.args)
        if call.tool == DESCRIBE:
            return self._describe(call.args)
        if call.tool == INVOKE:
            operation_id = call.args.get("operation_id")
            op = self.spec.by_id(operation_id) if operation_id else None
            if op is None:
                # A hallucinated operation id. Reported as a 404 so it lands in
                # the hallucinated-endpoints metric exactly like a bad path would.
                return Result(404, None, 0.0,
                              error=f"no operation {operation_id!r}")
            return self.inner.invoke(Call(
                tool=op.operation_id,
                method=op.method.upper(),
                path=op.path,
                args=call.args.get("arguments") or {},
            ))
        return self.inner.invoke(call)

    def teardown(self) -> None:
        self.inner.teardown()

    # ---- the three meta-tools -------------------------------------------

    def _search(self, args: dict[str, Any]) -> Any:
        from .packaging import Result

        query = args.get("query")
        if not query:
            return Result(422, None, 0.0, error="search_operations needs a query")
        limit = int(args.get("limit") or 10)
        hits = self.index.search(str(query), limit)  # type: ignore[union-attr]
        return Result(200, {
            "matches": [
                {
                    "operation_id": op.operation_id,
                    "summary": op.summary or op.signature,
                    "score": round(score, 4),
                }
                for op, score in hits
            ],
            "total_operations": len(self.spec.operations),
        }, 0.0)

    def _describe(self, args: dict[str, Any]) -> Any:
        from .packaging import Result

        operation_id = args.get("operation_id")
        op = self.spec.by_id(operation_id) if operation_id else None
        if op is None:
            return Result(404, None, 0.0, error=f"no operation {operation_id!r}")
        self.described.add(op.operation_id)
        return Result(200, {
            "operation_id": op.operation_id,
            "method": op.method.upper(),
            "path": op.path,
            "summary": op.summary,
            "description": op.description,
            "parameters": _json_schema(op, self.schema_detail),
            "errors": {
                code: body.get("description", "")
                for code, body in op.responses.items()
                if code.startswith(("4", "5"))
            },
        }, 0.0)


@dataclass
class RetrievalDispatcher:
    """E1: top-k operations retrieved per turn instead of a search tool.

    Different mechanism from the triad: the model never asks. The harness
    retrieves against the task prompt and puts only the top-k schemas in front of
    it, so retrieval quality — not the model's search behaviour — is what varies.

    Recall@k against the gold call sequence is the metric that makes this arm
    interpretable: a low score with poor recall says the retriever failed, not
    the model.
    """

    spec: ApiSpec
    inner: Any
    k: int = 5
    index: OperationIndex | None = None
    retrieved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.index = self.index or OperationIndex(self.spec)

    def retrieve_for(self, prompt: str) -> tuple[Operation, ...]:
        hits = self.index.search(prompt, self.k)  # type: ignore[union-attr]
        ops = tuple(op for op, _ in hits)
        self.retrieved = tuple(op.operation_id for op in ops)
        return ops

    def recall_at_k(self, gold_operation_ids: tuple[str, ...]) -> float | None:
        """Did the retriever even surface the operations the task needs?"""
        if not gold_operation_ids:
            return None
        hit = sum(1 for g in gold_operation_ids if g in self.retrieved)
        return hit / len(gold_operation_ids)

    def invoke(self, call: Any) -> Any:
        return self.inner.invoke(call)

    def teardown(self) -> None:
        self.inner.teardown()
