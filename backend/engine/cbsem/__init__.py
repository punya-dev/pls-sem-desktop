"""
CB-SEM Engine Package (Phase 6)
Implements Covariance-Based Structural Equation Modeling:
- RAM (Reticular Action Model) parameterization
- Maximum Likelihood (ML) estimation via scipy.optimize
- Model-implied covariance matrix Σ(θ)
- Degrees of freedom, model identification check
- Asymptotic standard errors, z-scores, p-values via numerical information matrix
- Fit indices: Chi-Square, p-value, CFI, TLI, RMSEA (with 90% CI), SRMR, AIC, BIC
- Standardized parameter estimates & Heywood case detection
"""
from engine.cbsem.algorithm import CBSEMAlgorithm, run_cbsem

__all__ = ["CBSEMAlgorithm", "run_cbsem"]
