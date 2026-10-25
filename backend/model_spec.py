from enum import Enum
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator


class ConstructType(str, Enum):
    REFLECTIVE = "reflective"
    FORMATIVE = "formative"

    def __str__(self) -> str:
        return str(self.value)


class Construct(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    type: ConstructType = ConstructType.REFLECTIVE
    indicators: List[str] = Field(default_factory=list)
    weighting: Optional[Literal["estimated", "sum_scores", "predefined"]] = "estimated"
    predefined_weights: Optional[Dict[str, float]] = None
    outer_mode: Optional[Literal["A", "B", "a", "b"]] = None
    order: Optional[Literal["first", "higher"]] = "first"
    components: Optional[List[str]] = Field(default_factory=list)
    hoc_type: Optional[Literal["RR", "RF", "FR", "FF", "rr", "rf", "fr", "ff"]] = None


class Indicator(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    column: str


class Path(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")


class ModeratingEffect(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: Optional[str] = None
    moderator: str
    source: str
    target: str
    method: Optional[Literal["two_stage", "product_indicator", "orthogonalizing"]] = "two_stage"
    standardize: bool = True

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "moderator_lv" in d and "moderator" not in d:
                d["moderator"] = d["moderator_lv"]
            if "predictor_lv" in d and "source" not in d:
                d["source"] = d["predictor_lv"]
            elif "predictor" in d and "source" not in d:
                d["source"] = d["predictor"]
            if "outcome_lv" in d and "target" not in d:
                d["target"] = d["outcome_lv"]
            elif "outcome" in d and "target" not in d:
                d["target"] = d["outcome"]
            return d
        return data

    @property
    def moderator_lv(self) -> str:
        return self.moderator

    @property
    def predictor_lv(self) -> str:
        return self.source

    @property
    def outcome_lv(self) -> str:
        return self.target

    @property
    def predictor(self) -> str:
        return self.source

    @property
    def outcome(self) -> str:
        return self.target


class QuadraticEffect(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    construct_id: str = Field(..., alias="construct")
    target: str


class ModelSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    constructs: List[Construct] = Field(default_factory=list)
    indicators: List[Indicator] = Field(default_factory=list)
    paths: List[Path] = Field(default_factory=list)
    dataset_id: Optional[str] = None
    moderating_effects: List[ModeratingEffect] = Field(default_factory=list)
    quadratic_effects: List[QuadraticEffect] = Field(default_factory=list)
    spec_version: str = "2.0"
    settings: Optional[Dict[str, Any]] = None


class ValidateModelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    spec: ModelSpec
    project_path: Optional[str] = None
    dataset_columns: Optional[List[str]] = None
    columns: Optional[List[str]] = None


class SaveModelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_path: str
    spec: ModelSpec
    diagram_layout: Optional[Dict[str, Any]] = None
    model_id: Optional[str] = None


class RunPlsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_path: str
    spec: Optional[ModelSpec] = None
    dataset_id: Optional[str] = None
    columns: Optional[List[str]] = None
    rows: Optional[List[List[Any]]] = None
    dataset_name: Optional[str] = None
    scheme: str = "path"
    max_iter: int = 300
    tol: float = 1e-7
    bootstrap: bool = False
    n_boot: int = 500
    missing_treatment: str = "mean"
    missing_values: Optional[List[str]] = None
    model_id: Optional[str] = None
    diagram_layout: Optional[Dict[str, Any]] = None


class BootstrapStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_path: str
    spec: Optional[ModelSpec] = None
    dataset_id: Optional[str] = None
    columns: Optional[List[str]] = None
    rows: Optional[List[List[Any]]] = None
    dataset_name: Optional[str] = None
    scheme: str = "path"
    max_iter: int = 300
    tol: float = 1e-7
    n_boot: int = 500
    seed: Optional[int] = 42
    sign_alignment: bool = True
    missing_treatment: str = "mean"
    missing_values: Optional[List[str]] = None
    model_id: Optional[str] = None
    diagram_layout: Optional[Dict[str, Any]] = None
