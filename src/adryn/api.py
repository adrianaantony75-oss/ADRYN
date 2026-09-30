"""Local prediction service. Deploy behind authenticated infrastructure for shared use."""

import json
import pickle
from datetime import date
from functools import lru_cache
from uuid import UUID

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from adryn.core.customer import FEATURES
from adryn.io import current_output
from adryn.settings import get_settings

app = FastAPI(title="ADRYN Decision Intelligence", version="0.2.0")


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    # Do not echo submitted text or non-JSON numeric values in error responses.
    detail = [{key: error[key] for key in ("loc", "msg", "type")} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": detail})


class ModelMetadata(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    run_id: UUID
    as_of: date
    threshold: float = Field(ge=0, le=1)
    features: list[str]


class ChurnInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    sessions: int = Field(ge=0, le=10000)
    learning_minutes: int = Field(ge=0, le=1000000)
    days_since_activity: int = Field(ge=0, le=3660)
    support_tickets: int = Field(ge=0, le=1000)
    payment_failed: int = Field(ge=0, le=1)
    monthly_price: float = Field(gt=0, le=10000)
    tenure_months: int = Field(ge=1, le=1200)


class VoiceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=3, max_length=10000)

    @field_validator("text")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Provide at least three non-whitespace characters.")
        return value


@lru_cache(maxsize=4)
def _load(path: str, modified: int):
    return joblib.load(path)


def artifact(name: str):
    try:
        root = current_output(get_settings().output_dir) / "models"
        path = root / f"{name}.joblib"
        metadata = ModelMetadata.model_validate_json(
            (root / "metadata.json").read_text(encoding="utf-8")
        ).model_dump(mode="json")
        summary = json.loads((root.parent / "pipeline_summary.json").read_text(encoding="utf-8"))
        if metadata["run_id"] != summary["run_id"] or metadata["features"] != FEATURES:
            raise ValueError("Model metadata does not match the published run contract")
        model = _load(str(path), path.stat().st_mtime_ns)
        if not callable(getattr(model, "predict_proba", None)):
            raise TypeError("Invalid prediction model")
        return model, metadata
    except (
        OSError, ValueError, KeyError, TypeError, EOFError, ImportError,
        IndexError, AttributeError, pickle.UnpicklingError,
    ):
        raise HTTPException(
            503, "Published model artifacts are unavailable. Check the analysis run."
        ) from None


@app.get("/health")
def health():
    try:
        _, metadata = artifact("churn")
        artifact("voice")
    except HTTPException:
        return {"service": "adryn", "model_ready": False, "data_source": "synthetic"}
    return {
        "service": "adryn", "model_ready": True, "data_source": "synthetic",
        "run_id": metadata["run_id"], "as_of": metadata["as_of"],
    }


@app.post("/predict/churn")
def predict_churn(payload: ChurnInput):
    model, metadata = artifact("churn")
    frame = pd.DataFrame([payload.model_dump()])[FEATURES]
    probability = float(model.predict_proba(frame)[0, 1])
    return {
        "churn_probability": probability,
        "review_required": probability >= metadata["threshold"],
        "threshold": metadata["threshold"],
        "run_id": metadata["run_id"],
        "as_of": metadata["as_of"],
        "synthetic_benchmark": True,
    }


@app.post("/predict/support-theme")
def predict_theme(payload: VoiceInput):
    model, metadata = artifact("voice")
    probabilities = model.predict_proba([payload.text])[0]
    return {
        "theme": str(model.classes_[probabilities.argmax()]),
        "confidence": float(probabilities.max()),
        "needs_human_review": bool(probabilities.max() < 0.75),
        "run_id": metadata["run_id"],
        "synthetic_benchmark": True,
    }
