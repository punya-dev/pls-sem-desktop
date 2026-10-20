import React, { useState, useMemo } from 'react';

interface GlossaryModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface GlossaryEntry {
  term: string;
  category: string;
  definition: string;
  citation?: string;
}

const GLOSSARY_TERMS: GlossaryEntry[] = [
  {
    term: 'Average Variance Extracted (AVE)',
    category: 'Measurement Model',
    definition: 'A measure of convergent validity representing the degree to which a latent construct explains the variance of its indicators. A value of 0.50 or higher indicates that, on average, the construct explains more than half of the variance of its indicators.',
    citation: 'Fornell & Larcker (1981); Hair et al. (2018)',
  },
  {
    term: 'Becker et al. Total Effects Decomposition',
    category: 'Higher-Order Constructs',
    definition: 'Collect-type analytical framework for calculating direct, indirect, and total effects of higher-order constructs (HOC) and their lower-order constructs (LOC) on downstream endogenous targets.',
    citation: 'Becker, Klein, & Wetzels (2012)',
  },
  {
    term: 'Blindfolding',
    category: 'Structural Model',
    definition: 'A sample-reuse cross-validation technique that systematically omits data points and uses the resulting model estimates to predict omitted parts, yielding Stone-Geisser Q² values.',
    citation: 'Stone (1974); Geisser (1974)',
  },
  {
    term: 'Bonferroni Correction',
    category: 'Multiple Testing',
    definition: 'A family-wise error rate control method where the overall significance level α is divided by the total number of nonredundant hypothesis tests (m): α_bonf = α / m.',
    citation: 'Bonferroni (1936)',
  },
  {
    term: 'CAIC (Consistent AIC)',
    category: 'Latent Class Segmentation',
    definition: 'An information criterion for model selection in FIMIX-PLS that penalizes model complexity using both sample size and parameter count: CAIC = -2 ln L + K(ln N + 1). Together with BIC, it is recommended for determining the true number of segments.',
    citation: 'Bozdogan (1987); Sarstedt et al. (2011)',
  },
  {
    term: 'Compositional Invariance (MICOM Step 2)',
    category: 'Invariance Testing',
    definition: 'The requirement that composite scores created across different groups share identical weights and loadings, verified when the composite correlation c is greater than or equal to the 5% quantile of the empirical permutation distribution.',
    citation: 'Henseler et al. (2016)',
  },
  {
    term: 'Configural Invariance (MICOM Step 1)',
    category: 'Invariance Testing',
    definition: 'The qualitative requirement that identical constructs, identical indicators, identical data treatments, and identical algorithmic settings are applied across all groups.',
    citation: 'Henseler et al. (2016)',
  },
  {
    term: 'Confirmatory Tetrad Analysis (CTA-PLS)',
    category: 'Measurement Model',
    definition: 'A statistical test for distinguishing between reflective and formative measurement models using model-implied vanishing tetrad equations and bias-corrected Bonferroni confidence intervals.',
    citation: 'Gudergan et al. (2008); Hair et al. (2018)',
  },
  {
    term: 'Composite Reliability (ρ_c)',
    category: 'Measurement Model',
    definition: 'A measure of internal consistency reliability that takes into account the different loadings of indicators. Values between 0.70 and 0.90 are regarded as satisfactory to good.',
    citation: 'Jöreskog (1971)',
  },
  {
    term: 'Dijkstra-Henseler ρ_A',
    category: 'Consistent PLS',
    definition: 'A consistent reliability measure that estimates the exact reliability of construct scores when the underlying construct is conceptualized as a common factor.',
    citation: 'Dijkstra & Henseler (2015)',
  },
  {
    term: 'Disjoint Two-Stage Approach',
    category: 'Higher-Order Constructs',
    definition: 'An HCM estimation method where first-stage construct scores of lower-order constructs are extracted and subsequently used as single-item indicators of the higher-order construct in the second stage.',
    citation: 'Hair et al. (2018)',
  },
  {
    term: 'Effect Size (f²)',
    category: 'Structural Model',
    definition: 'The change in R² when a specific exogenous construct is omitted from the structural model: f² = (R²_incl - R²_excl) / (1 - R²_incl). Values of 0.02, 0.15, and 0.35 represent small, medium, and large effects.',
    citation: 'Cohen (1988)',
  },
  {
    term: 'Entropy / Normed Entropy (EN)',
    category: 'Latent Class Segmentation',
    definition: 'A measure of classification certainty in finite mixture models ranging from 0 to 1. Values exceeding 0.80 indicate clean separation into distinct segments.',
    citation: 'Ramaswamy et al. (1993); Sarstedt et al. (2011)',
  },
  {
    term: 'Ex Post Segmentation Analysis',
    category: 'Unobserved Heterogeneity',
    definition: 'The analytical step of matching unobserved latent segments (from FIMIX or POS) with observable customer or respondent characteristics using cross-tabulation and logistic regression.',
    citation: 'Hair et al. (2018 Ch. 5)',
  },
  {
    term: 'Family-Wise Error Rate (FWER)',
    category: 'Multigroup Analysis',
    definition: 'The probability of making one or more Type I errors (false positives) when performing multiple pairwise hypothesis tests: FWER = 1 - (1 - α)^m.',
    citation: 'Hair et al. (2018 Ch. 4)',
  },
  {
    term: 'FIMIX-PLS (Finite Mixture PLS)',
    category: 'Latent Class Segmentation',
    definition: 'A model-based clustering approach for PLS path models that simultaneously estimates segment proportions and segment-specific structural path coefficients.',
    citation: 'Hahn, Johnson, Herrmann, & Frank (2002)',
  },
  {
    term: 'Formative Measurement Model',
    category: 'Measurement Model',
    definition: 'A construct operationalization where indicators cause or form the construct; indicators are not assumed to be interchangeable or highly correlated.',
    citation: 'Bollen & Lennox (1991); Hair et al. (2017)',
  },
  {
    term: 'Gaussian Copula Endogeneity Test',
    category: 'Endogeneity Assessment',
    definition: 'An instrument-free econometric technique that constructs a non-normal copula term from the empirical distribution function of a regressor to test for omitted variable bias.',
    citation: 'Park & Gupta (2012); Hult et al. (2018)',
  },
  {
    term: 'Henseler PLS-MGA',
    category: 'Multigroup Analysis',
    definition: 'A non-parametric significance test for comparing path coefficients between two groups based on the proportion of bootstrap estimates in group 1 exceeding those in group 2.',
    citation: 'Henseler, Ringle, & Sinkovics (2009)',
  },
  {
    term: 'Higher-Order Construct (HCM)',
    category: 'Model Specification',
    definition: 'A multidimensional construct consisting of two or more lower-order component constructs (LOCs) configured in reflective-reflective, reflective-formative, or formative-reflective structures.',
    citation: 'Becker et al. (2012); Hair et al. (2018)',
  },
  {
    term: 'HTMT (Heterotrait-Monotrait Ratio)',
    category: 'Discriminant Validity',
    definition: 'An estimate of the true correlation between two latent constructs based on the average heterotrait-heteromethod correlations relative to monotrait-heteromethod correlations. Thresholds: < 0.85 (conservative) or < 0.90 (liberal).',
    citation: 'Henseler, Ringle, & Sarstedt (2015)',
  },
  {
    term: 'Importance-Performance Map Analysis (IPMA)',
    category: 'Diagnostics & Actionability',
    definition: 'A graphical prioritization tool contrasting the total unstandardized effect (importance) against the rescaled 0–100 mean performance score of constructs and indicators.',
    citation: 'Höck et al. (2010); Hair et al. (2018)',
  },
  {
    term: 'Kenny (2015) Nonlinear f² Benchmarks',
    category: 'Nonlinear Effects',
    definition: 'Adjusted effect size benchmarks tailored for polynomial and interaction terms in structural equations: 0.01 (small), 0.05 (medium), and 0.10 (large).',
    citation: 'Kenny (2015)',
  },
  {
    term: 'Lohmöller Inner Weighting',
    category: 'Algorithm',
    definition: 'Iterative scheme in PLS-SEM that calculates inner proxy scores using centroid, factor, or path weighting schemes.',
    citation: 'Lohmöller (1989)',
  },
  {
    term: 'Marginal Slope',
    category: 'Nonlinear Effects',
    definition: 'The instantaneous rate of change of the endogenous construct with respect to the predictor: ∂Y/∂X = β₁ + 2β₂X.',
    citation: 'Hair et al. (2018 Ch. 3)',
  },
  {
    term: 'Measurement Invariance of Composite Models (MICOM)',
    category: 'Invariance Testing',
    definition: 'A 3-step sequential non-parametric permutation procedure testing configural invariance (Step 1), compositional invariance (Step 2), and equality of composite means and variances (Step 3).',
    citation: 'Henseler, Ringle, & Sarstedt (2016)',
  },
  {
    term: 'Multigroup Analysis (MGA)',
    category: 'Group Differences',
    definition: 'Statistical testing of whether structural path coefficients differ significantly between observed subgroups of respondents.',
    citation: 'Hair et al. (2018 Ch. 4)',
  },
  {
    term: 'Necessary Condition Analysis (NCA)',
    category: 'Causal Complexity',
    definition: 'A data analysis approach testing whether a condition is bottleneck-necessary for an outcome to exist (necessity logic) rather than sufficient (additive regression logic).',
    citation: 'Dul (2016)',
  },
  {
    term: 'Nonredundant Tetrad',
    category: 'Measurement Model',
    definition: 'An independent four-indicator difference equation τ_ijkl = r_ij * r_kl - r_ik * r_jl. A construct with M indicators has exactly M(M-3)/2 nonredundant tetrads.',
    citation: 'Bollen & Ting (1993); Gudergan et al. (2008)',
  },
  {
    term: 'Omnibus Test of Group Differences (OTG)',
    category: 'Multigroup Analysis',
    definition: 'A permutation-based F-statistic variance ratio test for simultaneously testing path differences across K > 2 groups while maintaining nominal family-wise error rates.',
    citation: 'Sarstedt, Henseler, & Ringle (2011)',
  },
  {
    term: 'Orthogonalizing Approach',
    category: 'Interaction Effects',
    definition: 'An estimation technique where product indicators are regressed on first-order linear indicators, and the resulting orthogonalized residuals are used to create the interaction term without inflating collinearity.',
    citation: 'Little, Bovaird, & Widaman (2006)',
  },
  {
    term: 'PLS-POS (Prediction-Oriented Segmentation)',
    category: 'Latent Class Segmentation',
    definition: 'A distance-based iterative reallocation algorithm that sequentially moves single observations across segments to maximize the weighted R² of endogenous constructs.',
    citation: 'Squillacciotti (2005); Hair et al. (2018)',
  },
  {
    term: 'PLSpredict',
    category: 'Out-of-Sample Prediction',
    definition: 'A k-fold cross-validation procedure evaluating whether a PLS-SEM model can accurately predict new, unseen cases compared against a naive linear model (LM) benchmark.',
    citation: 'Shmueli et al. (2016, 2019)',
  },
  {
    term: 'Product-Indicator Approach',
    category: 'Interaction Effects',
    definition: 'A method for estimating moderating and quadratic effects where each indicator of the predictor is multiplied by each indicator of the moderator (or itself for quadratic terms).',
    citation: 'Chin, Marcolin, & Newsted (2003)',
  },
  {
    term: 'Quadratic Effect',
    category: 'Nonlinear Effects',
    definition: 'A nonlinear relationship where the effect of X on Y increases or decreases at an accelerating or diminishing rate, modeled via Y = β₁X + β₂X².',
    citation: 'Hair et al. (2018 Ch. 3)',
  },
  {
    term: 'Reflective Measurement Model',
    category: 'Measurement Model',
    definition: 'A measurement model where indicators are assumed to be caused by the latent construct and share a common core; indicators are interchangeable and highly correlated.',
    citation: 'Hair et al. (2017)',
  },
  {
    term: 'Repeated Indicators Approach',
    category: 'Higher-Order Constructs',
    definition: 'An HCM operationalization where all indicators of the lower-order constructs are simultaneously assigned as indicators of the higher-order construct.',
    citation: 'Wold (1982); Becker et al. (2012)',
  },
  {
    term: 'Šidák Correction',
    category: 'Multiple Testing',
    definition: 'A slightly less conservative family-wise error rate adjustment than Bonferroni: α_sidak = 1 - (1 - α)^(1/m).',
    citation: 'Šidák (1967)',
  },
  {
    term: 'Ten-Times Rule',
    category: 'Sample Size Planning',
    definition: 'A rule-of-thumb heuristic suggesting that minimum sample size must be at least 10 times the maximum number of structural paths directed at any construct, or 10 times the maximum number of formative indicators.',
    citation: 'Barclay, Higgins, & Thompson (1995)',
  },
  {
    term: 'Vanishing Tetrad',
    category: 'Measurement Model',
    definition: 'A tetrad difference that equals zero in the population under the assumption of a single-factor reflective measurement model.',
    citation: 'Spearman (1904); Bollen & Ting (1993)',
  },
  {
    term: 'Welch-Satterthwaite Test',
    category: 'Multigroup Analysis',
    definition: 'A parametric t-test variant that adjusts degrees of freedom to account for unequal variances between the two groups being compared.',
    citation: 'Satterthwaite (1946); Welch (1947)',
  },
  {
    term: 'Zhao, Lynch & Chen Mediation Framework',
    category: 'Mediation Analysis',
    definition: 'The definitive contemporary mediation classification system replacing Baron & Kenny, classifying models into complementary, competitive, indirect-only, direct-only, or no-effect.',
    citation: 'Zhao, Lynch, & Chen (2010)',
  },
];

export const GlossaryModal: React.FC<GlossaryModalProps> = ({ isOpen, onClose }) => {
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');

  const categories = useMemo(() => {
    const cats = Array.from(new Set(GLOSSARY_TERMS.map(t => t.category)));
    return ['All', ...cats.sort()];
  }, []);

  const filteredTerms = useMemo(() => {
    return GLOSSARY_TERMS.filter(item => {
      const matchesSearch = item.term.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.definition.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesCat = selectedCategory === 'All' || item.category === selectedCategory;
      return matchesSearch && matchesCat;
    });
  }, [searchTerm, selectedCategory]);

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(15, 23, 42, 0.65)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 10000,
      padding: '20px',
    }}>
      <div style={{
        backgroundColor: '#ffffff',
        borderRadius: '12px',
        width: '760px',
        maxWidth: '100%',
        maxHeight: '85vh',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
      }}>
        {/* Header */}
        <div style={{
          padding: '18px 24px',
          borderBottom: '1px solid var(--color-border-subtle, #f1f5f9)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          backgroundColor: 'var(--color-bg-surface, #f8fafc)',
        }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 700, color: '#0f172a' }}>
              Advanced PLS-SEM Glossary
            </h3>
            <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#64748b' }}>
              Definitions and benchmarks from Hair, Sarstedt, Ringle, &amp; Gudergan (2018)
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              fontSize: '18px',
              color: '#94a3b8',
              padding: '4px 8px',
              borderRadius: '6px',
            }}
          >
            ✕
          </button>
        </div>

        {/* Search & Filter Bar */}
        <div style={{
          padding: '14px 24px',
          borderBottom: '1px solid #e2e8f0',
          display: 'flex',
          gap: '12px',
          backgroundColor: '#fff',
        }}>
          <input
            type="text"
            placeholder="Search terms, equations, authors, or concepts..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
            }}
          />
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            style={{
              padding: '8px 12px',
              borderRadius: '8px',
              border: '1px solid #cbd5e1',
              fontSize: '13px',
              backgroundColor: '#fff',
            }}
          >
            {categories.map(c => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        {/* Term List */}
        <div style={{ padding: '20px 24px', overflowY: 'auto', flex: 1 }}>
          <div style={{ fontSize: '12px', color: '#64748b', marginBottom: '14px' }}>
            Showing {filteredTerms.length} of {GLOSSARY_TERMS.length} methodological terms
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {filteredTerms.map((entry, idx) => (
              <div
                key={idx}
                style={{
                  padding: '16px',
                  borderRadius: '8px',
                  border: '1px solid #e2e8f0',
                  backgroundColor: '#f8fafc',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>
                    {entry.term}
                  </h4>
                  <span style={{
                    fontSize: '11px',
                    fontWeight: 600,
                    padding: '2px 8px',
                    borderRadius: '4px',
                    backgroundColor: '#e0e7ff',
                    color: '#3730a3',
                  }}>
                    {entry.category}
                  </span>
                </div>
                <p style={{ margin: '0 0 8px', fontSize: '13px', color: '#334155', lineHeight: '1.6' }}>
                  {entry.definition}
                </p>
                {entry.citation && (
                  <span style={{ fontSize: '11px', color: '#64748b', fontStyle: 'italic' }}>
                    Source: {entry.citation}
                  </span>
                )}
              </div>
            ))}
            {filteredTerms.length === 0 && (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: '#94a3b8' }}>
                No terms found matching "{searchTerm}".
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
