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


class SaveModelRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    
    project_path: str
    spec: ModelSpec
    diagram_layout: Optional[Dict[str, Any]] = None
