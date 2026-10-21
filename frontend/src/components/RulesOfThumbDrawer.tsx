import React, { useState } from 'react';

interface RulesOfThumbDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const RulesOfThumbDrawer: React.FC<RulesOfThumbDrawerProps> = ({ isOpen, onClose }) => {
  const [activeExhibit, setActiveExhibit] = useState<string>('exhibit_2_9');

  if (!isOpen) return null;

  const EXHIBITS: Record<string, { title: string; subtitle: string; content: React.ReactNode }> = {
    exhibit_2_9: {
      title: 'Exhibit 2.9: CTA-PLS Rules of Thumb',
      subtitle: 'Confirmatory Tetrad Analysis for Model Specification (Ch. 2)',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>1. Pre-Analysis Condition</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              All indicator pairs of the construct must have substantial bivariate correlations (<strong>|r| ≥ 0.10</strong>). Indicators with negligible correlations do not share sufficient covariance to evaluate vanishing tetrad equations.
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>2. Model-Implied Tetrads</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              For <em>M</em> indicators, compute only the <strong>R = M(M - 3) / 2</strong> nonredundant tetrads. For 4 indicators, R = 2; for 5 indicators, R = 5; for 6 indicators, R = 9.
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>3. Statistical Decision</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Use <strong>Bias-Corrected Bonferroni Confidence Intervals</strong> (standard α = 0.05 or α = 0.10).
              <br />• <strong>Reflective Model:</strong> If <em>all</em> nonredundant tetrad CIs contain zero, the reflective measurement model is supported.
              <br />• <strong>Formative / Causal Model:</strong> If <em>at least one</em> nonredundant tetrad CI excludes zero, reject the reflective specification and specify formative indicators.
            </p>
          </div>
        </div>
      ),
    },
    exhibit_2_20: {
      title: 'Exhibit 2.20: HCM Rules of Thumb',
      subtitle: 'Higher-Order Constructs Evaluation (Ch. 2)',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>1. Reflective-Reflective Models</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Evaluate Lower-Order Constructs (LOCs) first (indicator reliability, CR, AVE). At the HOC level, evaluate HOC–LOC relationships as loadings (indicator reliability = l_i²). Compute manual AVE (≥ 0.50), Composite Reliability (≥ 0.70), and standardized Cronbach's alpha (≥ 0.70).
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>2. Formative HOCs</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Evaluate LOC weights on HOC, VIF collinearity (ceiling 3.0), and outer weight significance via bootstrapping.
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>3. Algorithm Recommendation</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              <strong>Factor weighting</strong> is the textbook recommendation for repeated-indicators estimation. Path weighting may experience premature Lohmöller convergence due to identical indicators shared across LOCs and HOCs.
            </p>
          </div>
        </div>
      ),
    },
    exhibit_3_5: {
      title: 'Exhibit 3.5: Mediation Analysis Rules of Thumb',
      subtitle: 'Indirect Effects & Classification (Ch. 3; Zhao et al. 2010)',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>1. Significance Testing</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Do not rely on the Baron &amp; Kenny (1986) step-down or Sobel test (low statistical power). Use <strong>5,000 bootstrap resamples with BCa confidence intervals</strong> to evaluate the indirect path (a × b).
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>2. Classification Framework</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              • <strong>Complementary Mediation:</strong> Both indirect effect (a × b) and direct effect (c') are significant and point in the same direction (a × b × c' &gt; 0).
              <br />• <strong>Competitive Mediation:</strong> Both indirect and direct effects are significant but point in opposite directions (a × b × c' &lt; 0).
              <br />• <strong>Indirect-Only (Full) Mediation:</strong> Indirect effect is significant, direct effect is non-significant.
              <br />• <strong>Direct-Only Non-Mediation:</strong> Direct effect is significant, indirect effect is non-significant.
              <br />• <strong>No-Effect Non-Mediation:</strong> Neither indirect nor direct effect is significant.
            </p>
          </div>
        </div>
      ),
    },
    exhibit_3_21: {
      title: 'Exhibit 3.21: Quadratic Effects Rules of Thumb',
      subtitle: 'Nonlinear Modeling Decision (Ch. 3; Kenny 2015)',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>1. Kenny (2015) Effect Size Benchmark</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Because interaction terms in structural equations have lower variance, Cohen's traditional thresholds underestimate effects. Use Kenny's benchmarks:
              <br />• <strong>f² = 0.01:</strong> Small interaction effect
              <br />• <strong>f² = 0.05:</strong> Medium interaction effect
              <br />• <strong>f² = 0.10:</strong> Large interaction effect
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>2. Model Specification Decision</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              If the quadratic path is not statistically significant (p ≥ 0.05) or the effect size is negligible (f² &lt; 0.01), <strong>retain the linear model</strong>. Only retain the quadratic specification when both significance and meaningful effect size are established.
            </p>
          </div>
        </div>
      ),
    },
    exhibit_4_7: {
      title: 'Exhibit 4.7: MICOM & MGA Rules of Thumb',
      subtitle: 'Measurement Invariance & Multigroup Testing (Ch. 4)',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>1. Sequential Invariance Testing</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              • <strong>Step 1 Configural:</strong> Same constructs, indicators, algorithm, and missing data coding across groups.
              <br />• <strong>Step 2 Compositional:</strong> Composite correlation c ≥ 5% quantile of permutation distribution (p ≥ 0.05).
              <br />• <strong>Step 3 Equality:</strong> Equal composite means and variances across groups (p ≥ 0.05).
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>2. Analysis Permissions</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              • <strong>Partial Invariance (Steps 1 &amp; 2):</strong> Comparing standardized path coefficients in MGA is fully valid.
              <br />• <strong>Full Invariance (Steps 1, 2, &amp; 3):</strong> Pooling data for joint estimation is permitted.
              <br />• <strong>No Invariance (Step 2 failed):</strong> Do not run MGA; path differences may simply reflect measurement differences.
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>3. More than 2 Groups (K &gt; 2)</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Execute the <strong>Omnibus Test of Group Differences (OTG)</strong> first to control the inflated Family-Wise Error Rate (FWER = 1 - (1 - α)^m), followed by post-hoc pairwise testing with Šidák or Bonferroni adjustments.
            </p>
          </div>
        </div>
      ),
    },
    exhibit_5_7: {
      title: 'Exhibit 5.7: Unobserved Heterogeneity Rules of Thumb',
      subtitle: 'FIMIX-PLS and PLS-POS Segmentation (Ch. 5)',
      content: (
        <div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>1. Segment Number Selection (FIMIX-PLS)</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Inspect AIC, AIC₃, AIC₄, BIC, CAIC, and MDL₅ across K = 1 to K_max segments.
              <br />• <strong>CAIC and BIC</strong> are the most reliable criteria, pointing to the true segment count in &gt; 90% of empirical scenarios.
              <br />• <strong>Normed Entropy (EN):</strong> Values &gt; 0.80 indicate clean segment classification; 0.50–0.80 indicates moderate separation; &lt; 0.50 indicates ambiguous segments.
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>2. Statistical Power Verification</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Verify that the smallest segment size satisfies the 80% statistical power threshold (<strong>N_k ≥ 54</strong> for 2 predictors at α = 0.05 and R² = 0.25).
            </p>
          </div>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ margin: '0 0 6px', fontSize: 14, fontWeight: 700, color: '#0f172a' }}>3. Ex Post Matching Requirement</h4>
            <p style={{ margin: 0, fontSize: 13, color: '#334155', lineHeight: 1.6 }}>
              Observable market characteristics or demographic variables are only suitable explanatory factors if their cross-tabulation overlap with latent segment assignments is <strong>≥ 60%</strong> (Exhibit 5.16).
            </p>
          </div>
        </div>
      ),
    },
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      right: 0,
      bottom: 0,
      width: '460px',
      maxWidth: '90vw',
      backgroundColor: '#ffffff',
      boxShadow: '-4px 0 24px rgba(0, 0, 0, 0.15)',
      zIndex: 10000,
      display: 'flex',
      flexDirection: 'column',
      borderLeft: '1px solid var(--color-border-subtle, #e2e8f0)',
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
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: 'var(--color-text-primary, #0f172a)' }}>
            Methodological Rules of Thumb
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'var(--color-text-muted, #64748b)' }}>
            Hair, Sarstedt, Ringle, &amp; Gudergan (2018) Advanced Issues
          </p>
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '18px',
            color: 'var(--color-text-muted, #94a3b8)',
            padding: '4px 8px',
            borderRadius: '6px',
          }}
        >
          ✕
        </button>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex',
        overflowX: 'auto',
        borderBottom: '1px solid var(--color-border-subtle, #e2e8f0)',
        backgroundColor: '#fff',
        padding: '0 12px',
      }}>
        {Object.keys(EXHIBITS).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveExhibit(key)}
            style={{
              padding: '10px 12px',
              border: 'none',
              borderBottom: activeExhibit === key ? '2px solid var(--color-accent, #2563eb)' : '2px solid transparent',
              background: 'none',
              fontSize: '12px',
              fontWeight: activeExhibit === key ? 700 : 500,
              color: activeExhibit === key ? 'var(--color-accent, #2563eb)' : '#64748b',
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {key.replace('exhibit_', 'Ex. ').replace('_', '.')}
          </button>
        ))}
      </div>

      {/* Body */}
      <div style={{ padding: '24px', overflowY: 'auto', flex: 1 }}>
        <h4 style={{ margin: '0 0 4px', fontSize: '15px', fontWeight: 700, color: 'var(--color-text-primary)' }}>
          {EXHIBITS[activeExhibit]?.title}
        </h4>
        <p style={{ margin: '0 0 20px', fontSize: '12px', color: 'var(--color-text-muted)' }}>
          {EXHIBITS[activeExhibit]?.subtitle}
        </p>
        {EXHIBITS[activeExhibit]?.content}
      </div>
    </div>
  );
};
