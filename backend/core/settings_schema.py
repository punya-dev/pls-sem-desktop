"""
Settings Schema for PLS-SEM Pipeline and Algorithms.
Unifies all calculation, weighting, missing value, and inference settings into a single validated Pydantic model.
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field, ConfigDict


class PipelineSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    # Core PLS-SEM Algorithm
    inner_weighting: Literal["path", "factor", "centroid"] = Field(
        default="path",
        description="Inner weighting scheme: 'path' (recommended), 'factor', or 'centroid'",
    )
    max_iter: int = Field(
        default=300,
        ge=0,
        le=5000,
        description="Maximum iterations for Wold algorithm. Set to 0 for sum scores.",
    )
    tolerance: float = Field(
        default=1e-7,
        gt=0,
        le=1e-2,
        description="Convergence stop criterion on outer weight changes.",
    )
    initial_weights: Literal["equal", "lohmoller", "individual", "sum_scores"] = Field(
        default="equal",
        description="Initial outer weights initialization strategy.",
    )
    individual_initial_weights: Optional[Dict[str, float]] = Field(
        default=None,
        description="Explicit user-provided initial weights per indicator ID if initial_weights='individual'.",
    )

    # Missing Value Handling
    missing_treatment: Literal["mean", "listwise", "pairwise", "em", "knn"] = Field(
        default="mean",
        description="Missing data treatment method.",
    )
    missing_codes: List[Any] = Field(
        default_factory=lambda: [-99, "-99"],
        description="Values to be recognized as missing data.",
    )

    # Weighted PLS
    weight_column: Optional[str] = Field(
        default=None,
        description="Name of dataset column used for observation weighting (Weighted PLS).",
    )

    # Consistent PLS (PLSc)
    consistent: bool = Field(
        default=False,
        description="Whether to execute Consistent PLS (PLSc) disattenuation for reflective constructs.",
    )

    # Sign convention for latent variable scores
    sign_convention: Literal["dominant", "none"] = Field(
        default="dominant",
        description="Sign convention for point estimation ('dominant' flips construct to positive dominant loading).",
    )

    # Moderation method
    moderation_method: Literal["two_stage", "product_indicator", "orthogonalizing"] = Field(
        default="two_stage",
        description="Method used for computing interaction terms in moderation analysis.",
    )

    # Hierarchical Component Models (HCM)
    hcm_method: Literal["repeated_indicators", "two_stage"] = Field(
        default="repeated_indicators",
        description="Estimation approach for Higher-Order Components (HOC).",
    )

    # Statistical Inference & Bootstrapping
    significance_level: float = Field(
        default=0.05,
        gt=0,
        lt=0.5,
        description="Nominal significance level alpha (e.g. 0.05, 0.01, 0.10).",
    )
    tails: Literal["two", "one"] = Field(
        default="two",
        description="Tails for hypothesis testing ('two' or 'one').",
    )
    ci_method: Literal["percentile", "bias_corrected", "bca", "studentized"] = Field(
        default="percentile",
        description="Confidence interval computation method.",
    )
    sign_change: Literal["none", "individual", "construct"] = Field(
        default="none",
        description="Sign indeterminacy correction method in bootstrapping ('none' recommended by book).",
    )

    # Data Source
    dataset_id: Optional[str] = Field(
        default=None,
        description="Identifier of the dataset inside the project.",
    )
