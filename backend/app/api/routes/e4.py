from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.schemas.common import Quantity
from app.services.compute import ledger as ledger_service
from app.services.report.renderer import ensure_report_inputs_current
from app.state import session_manager

router = APIRouter(prefix="/api/experiments/e4", tags=["experiments"])
_ALLOWED_MODES = {"none", "full", "direct", "recursive"}


class ChangeRequest(BaseModel):
    session_id: UUID
    symbol: str = Field(min_length=1)
    value: float
    unit: str = ""
    propagation_mode: str = "recursive"


class ProbeRequest(BaseModel):
    session_id: UUID
    symbols: list[str] = Field(default_factory=list)
    record_ids: list[str] = Field(default_factory=list)


def _session(session_id: UUID):
    session = session_manager.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.post("/change")
def change_parameter(req: ChangeRequest) -> dict:
    session = _session(req.session_id)
    entry = session.ledger.get(req.symbol)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"parameter not found: {req.symbol}")
    mode = req.propagation_mode.strip().lower()
    if mode not in _ALLOWED_MODES:
        raise HTTPException(status_code=400, detail=f"invalid propagation mode: {mode}")
    was_frozen = session.ledger.is_frozen
    if was_frozen:
        session.ledger.unfreeze("E4 controlled change on cloned baseline")
    try:
        updated = ledger_service.commit_parameter(
            session,
            symbol=req.symbol,
            value=Quantity(value=req.value, unit=req.unit or entry.value.unit),
            source=entry.source,
            name=entry.name,
            basis=list(entry.basis),
            rationale=entry.rationale,
            group=entry.group,
            propagation_mode=mode,
        )
    except ledger_service.LedgerError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session_manager.update(session)
    return {
        "status": "ok",
        "session_id": str(session.session_id),
        "symbol": updated.symbol,
        "value": updated.value.model_dump(mode="json"),
        "revision": updated.revision,
        "baseline_was_frozen": was_frozen,
        "propagation_mode": mode,
        "stale": ledger_service.stale_summary(session),
    }


@router.post("/probe")
def probe_downstream(req: ProbeRequest) -> dict:
    session = _session(req.session_id)
    entries: list[dict] = []
    for symbol in req.symbols:
        entry = session.ledger.get(symbol)
        if entry is None:
            entries.append({"symbol": symbol, "status": "missing", "accepted": False})
            continue
        try:
            ledger_service.resolve_for_geometry(session, symbol)
        except ledger_service.LedgerError as exc:
            entries.append({
                "symbol": symbol,
                "status": entry.status.value,
                "stale": entry.status.value == "stale",
                "accepted": False,
                "error": str(exc),
            })
        else:
            entries.append({
                "symbol": symbol,
                "status": entry.status.value,
                "stale": entry.status.value == "stale",
                "accepted": True,
            })

    records: list[dict] = []
    for record_id in req.record_ids:
        record = session.calculations.get(record_id)
        records.append({
            "record_id": record_id,
            "status": "missing" if record is None else ("stale" if record.stale else "current"),
            "stale": bool(record and record.stale),
            "exists": record is not None,
        })

    try:
        ensure_report_inputs_current(session)
    except ValueError as exc:
        report = {"accepted": False, "error": str(exc)}
    else:
        report = {"accepted": True, "error": ""}

    return {
        "status": "ok",
        "session_id": str(session.session_id),
        "entries": entries,
        "records": records,
        "report": report,
        "stale": ledger_service.stale_summary(session),
    }
