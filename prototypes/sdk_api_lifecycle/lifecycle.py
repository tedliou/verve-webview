"""PROTOTYPE: pure lifecycle model for the minimal WebView SDK interface."""

from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    HIDDEN = "initialized / surface closed"
    OPENING = "opening / navigating"
    VISIBLE = "surface visible"
    CLOSING = "closing"
    DISPOSING = "disposing (terminal path)"
    DISPOSED = "disposed"


class OperationKind(str, Enum):
    INITIALIZE = "initialize"
    OPEN = "open"
    CLOSE = "close"
    DISPOSE = "dispose"


@dataclass(frozen=True)
class PendingOperation:
    identifier: int
    kind: OperationKind
    previous_phase: Phase
    previous_url: str | None
    requested_url: str | None = None


@dataclass(frozen=True)
class ImmediateResult:
    accepted: bool
    code: str
    operation_id: int | None = None


@dataclass
class Model:
    phase: Phase = Phase.UNINITIALIZED
    visible_url: str | None = None
    pending: PendingOperation | None = None
    retired_operation_ids: set[int] = field(default_factory=set)
    next_operation_id: int = 1
    last_result: str = "No command issued."
    last_event: str = "No completion event emitted."
    diagnostics: list[str] = field(default_factory=list)

    def initialize(self) -> ImmediateResult:
        if rejection := self._common_rejection():
            return rejection
        if self.phase is not Phase.UNINITIALIZED:
            return self._reject("already_initialized")
        return self._begin(OperationKind.INITIALIZE, Phase.INITIALIZING)

    def open(self, url: str) -> ImmediateResult:
        if rejection := self._common_rejection():
            return rejection
        if self.phase not in (Phase.HIDDEN, Phase.VISIBLE):
            return self._reject("not_initialized")
        if not url.startswith(("https://", "http://")):
            return self._reject("invalid_url")
        return self._begin(OperationKind.OPEN, Phase.OPENING, url)

    def close(self) -> ImmediateResult:
        if rejection := self._common_rejection():
            return rejection
        if self.phase is Phase.HIDDEN:
            return self._reject("surface_not_open")
        if self.phase is not Phase.VISIBLE:
            return self._reject("not_initialized")
        return self._begin(OperationKind.CLOSE, Phase.CLOSING)

    def dispose(self) -> ImmediateResult:
        if self.phase in (Phase.DISPOSING, Phase.DISPOSED):
            return self._reject("disposed")

        # Candidate contract: Dispose is the sole pre-emptive command. Once accepted,
        # an older completion may diagnose but can no longer mutate state or emit.
        if self.pending:
            self.retired_operation_ids.add(self.pending.identifier)
            self.diagnostics.append(
                f"operation {self.pending.identifier} retired by dispose"
            )
            self.pending = None
        return self._begin(OperationKind.DISPOSE, Phase.DISPOSING)

    def complete(self, success: bool) -> None:
        if not self.pending:
            self.last_event = "No active operation to complete."
            return

        operation = self.pending
        self.pending = None
        if operation.kind is OperationKind.DISPOSE:
            self.phase = Phase.DISPOSED
            self.visible_url = None
            outcome = "ok" if success else "backend_error (resources invalidated)"
        elif success:
            outcome = "ok"
            if operation.kind is OperationKind.INITIALIZE:
                self.phase = Phase.HIDDEN
            elif operation.kind is OperationKind.OPEN:
                self.phase = Phase.VISIBLE
                self.visible_url = operation.requested_url
            elif operation.kind is OperationKind.CLOSE:
                self.phase = Phase.HIDDEN
                self.visible_url = None
        else:
            outcome = "backend_error"
            self.phase = operation.previous_phase
            self.visible_url = operation.previous_url

        self.last_event = (
            f"operation_completed(id={operation.identifier}, result={outcome})"
        )

    def deliver_late_completion(self) -> None:
        if not self.retired_operation_ids:
            self.last_event = "No retired operation is available."
            return
        identifier = min(self.retired_operation_ids)
        self.retired_operation_ids.remove(identifier)
        self.diagnostics.append(f"ignored stale completion for operation {identifier}")
        self.last_event = "No Engine Adapter event emitted for stale completion."

    def _common_rejection(self) -> ImmediateResult | None:
        if self.phase in (Phase.DISPOSING, Phase.DISPOSED):
            return self._reject("disposed")
        if self.pending:
            return self._reject("operation_in_progress")
        return None

    def _begin(
        self,
        kind: OperationKind,
        in_flight_phase: Phase,
        requested_url: str | None = None,
    ) -> ImmediateResult:
        identifier = self.next_operation_id
        self.next_operation_id += 1
        self.pending = PendingOperation(
            identifier=identifier,
            kind=kind,
            previous_phase=self.phase,
            previous_url=self.visible_url,
            requested_url=requested_url,
        )
        self.phase = in_flight_phase
        result = ImmediateResult(True, "accepted", identifier)
        self.last_result = f"accepted(operation_id={identifier})"
        return result

    def _reject(self, code: str) -> ImmediateResult:
        self.last_result = f"rejected(error={code})"
        return ImmediateResult(False, code)
