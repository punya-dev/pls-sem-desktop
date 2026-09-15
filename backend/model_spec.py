from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ConstructType(str, Enum):
    REFLECTIVE = "reflective"
    FORMATIVE = "formative"


class Construct(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: str
    name: str
    type: ConstructType = ConstructType.REFLECTIVE
    indicators: List[str] = Field(default_factory=list)


class Indicator(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    id: str
    column: str


class Path(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    from_node: str = Field(..., alias="from")
    to_node: str = Field(..., alias="to")


class ModelSpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    constructs: List[Construct] = Field(default_factory=list)
    indicators: List[Indicator] = Field(default_factory=list)
    paths: List[Path] = Field(default_factory=list)


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


class RunPlsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    project_path: str
    spec: Optional[ModelSpec] = None
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


class BootstrapStartRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_path: str
    spec: Optional[ModelSpec] = None
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


