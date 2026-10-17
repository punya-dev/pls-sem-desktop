"""
Standardized issue and diagnostic reporting structures for PLS-SEM.
Rule 6: Issue objects always use:
{code: str, severity: "error"|"warning"|"info", target: {type, id}, message: str, advice: str|null}
"""

from typing import Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


class IssueTarget(BaseModel):
    type: str = Field(..., description="Target entity type, e.g. construct, indicator, path, model, dataset")
    id: str = Field(..., description="Identifier of the target entity")


class Issue(BaseModel):
    code: str = Field(..., description="Machine-readable error/warning code, e.g. SINGULAR_BLOCK")
    severity: Literal["error", "warning", "info"] = Field(..., description="Severity level")
    target: IssueTarget = Field(..., description="Target entity affected by the issue")
    message: str = Field(..., description="Clear human-readable description of the issue")
    advice: Optional[str] = Field(None, description="Actionable recommendation or rule-of-thumb advice")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "target": {"type": self.target.type, "id": self.target.id},
            "message": self.message,
            "advice": self.advice,
        }
