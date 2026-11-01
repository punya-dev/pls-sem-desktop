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
    attach_to_mod_id: Optional[str] = Field(default=None, alias="attachToModId")

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
            if "attachToModId" in d and "attach_to_mod_id" not in d:
                d["attach_to_mod_id"] = d["attachToModId"]
            elif "attach_to_mod_id" in d and "attachToModId" not in d:
                d["attachToModId"] = d["attach_to_mod_id"]
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
    predictor_construct: str = Field(..., alias="predictorConstruct")
    target_construct: str = Field(..., alias="targetConstruct")
    node_x: Optional[float] = Field(default=None, alias="nodeX")
    node_y: Optional[float] = Field(default=None, alias="nodeY")

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            pred = (
                d.get("predictor_construct")
                or d.get("predictorConstruct")
                or d.get("construct_id")
                or d.get("construct")
                or d.get("predictor")
                or d.get("source")
                or d.get("source_construct")
                or d.get("sourceConstruct")
            )
            tgt = (
                d.get("target_construct")
                or d.get("targetConstruct")
                or d.get("target")
                or d.get("outcome")
            )
            if pred:
                d["predictor_construct"] = pred
                d["predictorConstruct"] = pred
            if tgt:
                d["target_construct"] = tgt
                d["targetConstruct"] = tgt
            if "nodeX" in d and "node_x" not in d:
                d["node_x"] = d["nodeX"]
            elif "node_x" in d and "nodeX" not in d:
                d["nodeX"] = d["node_x"]
            if "nodeY" in d and "node_y" not in d:
                d["node_y"] = d["nodeY"]
            elif "node_y" in d and "nodeY" not in d:
                d["nodeY"] = d["node_y"]
            return d
        return data

    @property
    def construct_id(self) -> str:
        return self.predictor_construct

    @property
    def source(self) -> str:
        return self.predictor_construct

    @property
    def predictor(self) -> str:
        return self.predictor_construct

    @property
    def target(self) -> str:
        return self.target_construct

    @property
    def outcome(self) -> str:
        return self.target_construct



class GaussianCopula(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    source_construct: str = Field(..., alias="sourceConstruct")
    target_construct: str = Field(..., alias="targetConstruct")
    node_x: Optional[float] = Field(default=None, alias="nodeX")
    node_y: Optional[float] = Field(default=None, alias="nodeY")

    @model_validator(mode="before")
    @classmethod
    def _normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "source" in d and "source_construct" not in d and "sourceConstruct" not in d:
                d["source_construct"] = d["source"]
            if "target" in d and "target_construct" not in d and "targetConstruct" not in d:
                d["target_construct"] = d["target"]
            if "sourceConstruct" in d and "source_construct" not in d:
                d["source_construct"] = d["sourceConstruct"]
            elif "source_construct" in d and "sourceConstruct" not in d:
                d["sourceConstruct"] = d["source_construct"]
            if "targetConstruct" in d and "target_construct" not in d:
                d["target_construct"] = d["targetConstruct"]
            elif "target_construct" in d and "targetConstruct" not in d:
                d["targetConstruct"] = d["target_construct"]
            if "nodeX" in d and "node_x" not in d:
                d["node_x"] = d["nodeX"]
            elif "node_x" in d and "nodeX" not in d:
                d["nodeX"] = d["node_x"]
            if "nodeY" in d and "node_y" not in d:
                d["node_y"] = d["nodeY"]
            elif "node_y" in d and "nodeY" not in d:
                d["nodeY"] = d["node_y"]
            return d
        return data

    @property
    def source(self) -> str:
        return self.source_construct

    @property
    def target(self) -> str:
        return self.target_construct


class ModelSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    constructs: List[Construct] = Field(default_factory=list)
    indicators: List[Indicator] = Field(default_factory=list)
    paths: List[Path] = Field(default_factory=list)
    dataset_id: Optional[str] = None
    moderating_effects: List[ModeratingEffect] = Field(default_factory=list)
    quadratic_effects: List[QuadraticEffect] = Field(default_factory=list)
    gaussian_copulas: List[GaussianCopula] = Field(default_factory=list)
    spec_version: str = "2.0"
    settings: Optional[Dict[str, Any]] = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_spec_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            if "gaussianCopulas" in d and "gaussian_copulas" not in d:
                d["gaussian_copulas"] = d["gaussianCopulas"]
            elif "gaussian_copulas" in d and "gaussianCopulas" not in d:
                d["gaussianCopulas"] = d["gaussian_copulas"]
            if "moderatingEffects" in d and "moderating_effects" not in d:
                d["moderating_effects"] = d["moderatingEffects"]
            elif "moderating_effects" in d and "moderatingEffects" not in d:
                d["moderatingEffects"] = d["moderating_effects"]
            if "quadraticEffects" in d and "quadratic_effects" not in d:
                d["quadratic_effects"] = d["quadraticEffects"]
            elif "quadratic_effects" in d and "quadraticEffects" not in d:
                d["quadraticEffects"] = d["quadratic_effects"]
            return d
        return data


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
    settings: Optional[Dict[str, Any]] = None


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
    settings: Optional[Dict[str, Any]] = None
