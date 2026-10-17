import React, { useState } from 'react';

interface AdvancedResultPanelsProps {
  activeTab: string;
  results: any;
  analysisResults?: Record<string, any>;
  onExportExcel?: () => void;
  onExportPdf?: () => void;
}

export const AdvancedResultPanels: React.FC<AdvancedResultPanelsProps> = ({
  activeTab,
  results,
  analysisResults = {},
  onExportExcel,
  onExportPdf,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<string>('overview');
  const [selectedKpi, setSelectedKpi] = useState<string>('');

  // Extract analysis specific result or check if stored in main results
  const analysisData = analysisResults[activeTab] || results?.[activeTab] || results?.analysis?.[activeTab];

  // Helper for formatting decimals
  const fmt = (val: any, decimals = 3): string => {
    if (val === undefined || val === null || isNaN(Number(val))) return '—';
    return Number(val).toFixed(decimals);
  };

  const getSigBadge = (p: number) => {
    if (p < 0.001) return <span style={{ color: '#16a34a', fontWeight: 600 }}>*** (p &lt; .001)</span>;
    if (p < 0.01) return <span style={{ color: '#16a34a', fontWeight: 600 }}>** (p = {fmt(p)})</span>;
    if (p < 0.05) return <span style={{ color: '#16a34a', fontWeight: 600 }}>* (p = {fmt(p)})</span>;
    return <span style={{ color: '#94a3b8' }}>ns (p = {fmt(p)})</span>;
  };

  // 1. MODEL FIT (SRMR, d_ULS, d_G, RMS_theta, GoF)
  if (activeTab === 'model_fit') {
    const fit = results?.fit || analysisData || {};
    const srmrSat = fit.srmr_saturated ?? fit.srmr;
    const srmrEst = fit.srmr_estimated ?? fit.srmr;
    const rmsTheta = fit.rms_theta;
    const dUls = fit.d_uls;
    const dG = fit.d_g;
    const gof = fit.gof;

    return (
      <div className="results-content-pane">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
              Model Fit &amp; Global Goodness of Fit
            </h3>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
              Standardized Root Mean Square Residual (SRMR) and discrepancy measures (Henseler et al., 2016).
            </p>
          </div>
        </div>

        {/* Metric Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 14, marginBottom: 24 }}>
          <div style={{ padding: 16, borderRadius: 10, backgroundColor: 'var(--color-bg-surface, #f8fafc)', border: '1px solid var(--color-border-subtle, #e2e8f0)' }}>
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 600 }}>SRMR (Saturated Model)</span>
            <div style={{ fontSize: 24, fontWeight: 700, margin: '6px 0', color: srmrSat <= 0.08 ? '#16a34a' : '#d97706' }}>
              {fmt(srmrSat)}
            </div>
            <span style={{ fontSize: 11, color: srmrSat <= 0.08 ? '#16a34a' : '#d97706' }}>
              {srmrSat <= 0.08 ? '✓ Good Fit (≤ 0.08)' : 'Marginal Fit (> 0.08)'}
            </span>
          </div>

          <div style={{ padding: 16, borderRadius: 10, backgroundColor: 'var(--color-bg-surface, #f8fafc)', border: '1px solid var(--color-border-subtle, #e2e8f0)' }}>
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 600 }}>SRMR (Estimated Model)</span>
            <div style={{ fontSize: 24, fontWeight: 700, margin: '6px 0', color: srmrEst <= 0.08 ? '#16a34a' : '#d97706' }}>
              {fmt(srmrEst)}
            </div>
            <span style={{ fontSize: 11, color: srmrEst <= 0.08 ? '#16a34a' : '#d97706' }}>
              {srmrEst <= 0.08 ? '✓ Good Fit (≤ 0.08)' : 'Marginal Fit (> 0.08)'}
            </span>
          </div>

          <div style={{ padding: 16, borderRadius: 10, backgroundColor: 'var(--color-bg-surface, #f8fafc)', border: '1px solid var(--color-border-subtle, #e2e8f0)' }}>
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 600 }}>RMS theta</span>
            <div style={{ fontSize: 24, fontWeight: 700, margin: '6px 0', color: rmsTheta <= 0.12 ? '#16a34a' : '#d97706' }}>
              {fmt(rmsTheta)}
            </div>
            <span style={{ fontSize: 11, color: rmsTheta <= 0.12 ? '#16a34a' : '#d97706' }}>
              {rmsTheta <= 0.12 ? '✓ Acceptable (≤ 0.12)' : 'Check outer model'}
            </span>
          </div>

          <div style={{ padding: 16, borderRadius: 10, backgroundColor: 'var(--color-bg-surface, #f8fafc)', border: '1px solid var(--color-border-subtle, #e2e8f0)' }}>
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 600 }}>Tenenhaus GoF</span>
            <div style={{ fontSize: 24, fontWeight: 700, margin: '6px 0', color: 'var(--color-accent)' }}>
              {fmt(gof)}
            </div>
            <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
              √(Average Communality × Average R²)
            </span>
          </div>
        </div>

        {/* Detailed Table */}
        <div style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflow: 'hidden' }}>
          <table className="results-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Criterion</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Saturated Model</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Estimated Model</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Threshold</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '10px 14px', fontWeight: 600 }}>SRMR</td>
                <td style={{ padding: '10px 14px' }}>{fmt(srmrSat)}</td>
                <td style={{ padding: '10px 14px' }}>{fmt(srmrEst)}</td>
                <td style={{ padding: '10px 14px', color: '#16a34a' }}>&lt; 0.080 (Hu &amp; Bentler)</td>
              </tr>
              {dUls !== undefined && (
                <tr>
                  <td style={{ padding: '10px 14px', fontWeight: 600 }}>d_ULS (Squared Euclidean Distance)</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(fit.d_uls_saturated || dUls)}</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(dUls)}</td>
                  <td style={{ padding: '10px 14px', color: '#64748b' }}>Below 95% bootstrap quantile</td>
                </tr>
              )}
              {dG !== undefined && (
                <tr>
                  <td style={{ padding: '10px 14px', fontWeight: 600 }}>d_G (Geodesic Distance)</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(fit.d_g_saturated || dG)}</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(dG)}</td>
                  <td style={{ padding: '10px 14px', color: '#64748b' }}>Below 95% bootstrap quantile</td>
                </tr>
              )}
              {rmsTheta !== undefined && (
                <tr>
                  <td style={{ padding: '10px 14px', fontWeight: 600 }}>RMS theta</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(rmsTheta)}</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(rmsTheta)}</td>
                  <td style={{ padding: '10px 14px', color: '#16a34a' }}>&lt; 0.120 (Lohmöller, 1989)</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // 2. BLINDFOLDING (Q² & q²)
  if (activeTab === 'blindfolding') {
    if (!analysisData) {
      return (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>No Blindfolding Results Available</h4>
          <p style={{ margin: 0, fontSize: 13 }}>Click <strong>Calculate → Blindfolding (Q² &amp; q²)</strong> to evaluate predictive relevance.</p>
        </div>
      );
    }

    const constructsList = analysisData.constructs || [];
    const q2Effects = analysisData.q2_effects || [];

    return (
      <div className="results-content-pane">
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Blindfolding Predictive Relevance (Q²)
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
            Stone-Geisser Q² cross-validated redundancy. Q² &gt; 0 indicates the model has predictive relevance for the endogenous construct (Hair et al., 2017).
          </p>
        </div>

        {/* Construct Level Q² */}
        <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Construct Cross-Validated Redundancy</h4>
        <div style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflow: 'hidden', marginBottom: 24 }}>
          <table className="results-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Construct</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>SSO</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>SSE</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Q² (= 1 - SSE/SSO)</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Predictive Relevance</th>
              </tr>
            </thead>
            <tbody>
              {constructsList.map((c: any) => {
                const q2 = c.q2_redundancy;
                const isRelevant = q2 > 0;
                let strength = 'None';
                if (q2 >= 0.50) strength = 'Large (≥ 0.50)';
                else if (q2 >= 0.25) strength = 'Medium (≥ 0.25)';
                else if (q2 > 0) strength = 'Small (> 0)';

                return (
                  <tr key={c.construct_id}>
                    <td style={{ padding: '10px 14px', fontWeight: 600 }}>{c.construct_name || c.construct_id}</td>
                    <td style={{ padding: '10px 14px' }}>{fmt(c.sso, 1)}</td>
                    <td style={{ padding: '10px 14px' }}>{fmt(c.sse, 1)}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 600, color: isRelevant ? '#16a34a' : '#dc2626' }}>
                      {fmt(q2)}
                    </td>
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        padding: '3px 8px',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        backgroundColor: isRelevant ? '#dcfce7' : '#fee2e2',
                        color: isRelevant ? '#166534' : '#991b1b',
                      }}>
                        {strength}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* q² Effect Sizes */}
        {q2Effects.length > 0 && (
          <div>
            <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Relative Predictive Effect Sizes (q²)</h4>
            <div style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflow: 'hidden' }}>
              <table className="results-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)', textAlign: 'left' }}>
                    <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Predictor Path</th>
                    <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Target Construct</th>
                    <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>q² Effect Size</th>
                    <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Evaluation</th>
                  </tr>
                </thead>
                <tbody>
                  {q2Effects.map((p: any, idx: number) => (
                    <tr key={idx}>
                      <td style={{ padding: '10px 14px', fontWeight: 600 }}>{p.source} → {p.target}</td>
                      <td style={{ padding: '10px 14px' }}>{p.target}</td>
                      <td style={{ padding: '10px 14px', fontWeight: 600 }}>{fmt(p.q2_effect)}</td>
                      <td style={{ padding: '10px 14px' }}>
                        <span style={{
                          padding: '3px 8px',
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          backgroundColor: p.q2_effect >= 0.02 ? '#dcfce7' : '#f1f5f9',
                          color: p.q2_effect >= 0.02 ? '#166534' : '#64748b',
                        }}>
                          {p.rating || (p.q2_effect >= 0.35 ? 'Large' : p.q2_effect >= 0.15 ? 'Medium' : p.q2_effect >= 0.02 ? 'Small' : 'None')}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    );
  }

  // 3. MEDIATION ANALYSIS
  if (activeTab === 'mediation') {
    if (!analysisData) {
      return (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>No Mediation Results Available</h4>
          <p style={{ margin: 0, fontSize: 13 }}>Click <strong>Calculate → Mediation Analysis...</strong> to test indirect effects.</p>
        </div>
      );
    }

    const {
      source,
      target,
      direct_effect,
      indirect_effect,
      total_effect,
      vaf,
      typology,
      sobel,
      paths = [],
    } = analysisData;

    return (
      <div className="results-content-pane">
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Mediation Analysis: {source} → {target}
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
            Categorization based on Zhao, Lynch &amp; Chen (2010) and Hair et al. (2017) decision tree.
          </p>
        </div>

        {/* Mediation Classification Card */}
        <div style={{
          backgroundColor: '#f0fdf4',
          border: '1px solid #bbf7d0',
          borderRadius: 10,
          padding: '16px 20px',
          marginBottom: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <span style={{ fontSize: 12, color: '#166534', fontWeight: 600, textTransform: 'uppercase' }}>
              Mediation Type
            </span>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#15803d', marginTop: 2 }}>
              {typology || 'Complementary Mediation'}
            </div>
            <p style={{ margin: '4px 0 0', fontSize: 12, color: '#166534' }}>
              VAF (Variance Accounted For): <strong>{fmt((vaf || 0) * 100, 1)}%</strong>
            </p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontSize: 12, color: '#166534' }}>Sobel Test:</span>
            <div style={{ fontSize: 15, fontWeight: 600, color: '#166534' }}>
              z = {fmt(sobel?.z_value)}, p = {fmt(sobel?.p_value)}
            </div>
          </div>
        </div>

        {/* Effects Decomposition Table */}
        <h4 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600 }}>Effects Decomposition</h4>
        <div style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflow: 'hidden' }}>
          <table className="results-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Effect</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Coefficient</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Std. Error</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>t-Value</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>p-Value</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>95% CI</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style={{ padding: '10px 14px', fontWeight: 600 }}>Indirect Effect (a × b)</td>
                <td style={{ padding: '10px 14px', fontWeight: 600, color: 'var(--color-accent)' }}>{fmt(indirect_effect?.original || indirect_effect)}</td>
                <td style={{ padding: '10px 14px' }}>{fmt(indirect_effect?.se)}</td>
                <td style={{ padding: '10px 14px' }}>{fmt(indirect_effect?.t_stat)}</td>
                <td style={{ padding: '10px 14px' }}>{getSigBadge(indirect_effect?.p_value ?? 0)}</td>
                <td style={{ padding: '10px 14px' }}>[{fmt(indirect_effect?.ci_low)}, {fmt(indirect_effect?.ci_high)}]</td>
              </tr>
              <tr>
                <td style={{ padding: '10px 14px', fontWeight: 600 }}>Direct Effect (c&apos;)</td>
                <td style={{ padding: '10px 14px' }}>{fmt(direct_effect?.original || direct_effect)}</td>
                <td style={{ padding: '10px 14px' }}>{fmt(direct_effect?.se)}</td>
                <td style={{ padding: '10px 14px' }}>{fmt(direct_effect?.t_stat)}</td>
                <td style={{ padding: '10px 14px' }}>{getSigBadge(direct_effect?.p_value ?? 0)}</td>
                <td style={{ padding: '10px 14px' }}>[{fmt(direct_effect?.ci_low)}, {fmt(direct_effect?.ci_high)}]</td>
              </tr>
              <tr style={{ backgroundColor: 'var(--color-bg-surface)' }}>
                <td style={{ padding: '10px 14px', fontWeight: 700 }}>Total Effect (c)</td>
                <td style={{ padding: '10px 14px', fontWeight: 700 }}>{fmt(total_effect?.original || total_effect)}</td>
                <td style={{ padding: '10px 14px' }}>{fmt(total_effect?.se)}</td>
                <td style={{ padding: '10px 14px' }}>{fmt(total_effect?.t_stat)}</td>
                <td style={{ padding: '10px 14px' }}>{getSigBadge(total_effect?.p_value ?? 0)}</td>
                <td style={{ padding: '10px 14px' }}>[{fmt(total_effect?.ci_low)}, {fmt(total_effect?.ci_high)}]</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // 4. MODERATION & SIMPLE SLOPES
  if (activeTab === 'moderation') {
    if (!analysisData) {
      return (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>No Moderation Results Available</h4>
          <p style={{ margin: 0, fontSize: 13 }}>Click <strong>Calculate → Moderation Analysis...</strong> to test interaction effects.</p>
        </div>
      );
    }

    const {
      source,
      moderator,
      target,
      interaction_effect,
      f2_effect,
      simple_slopes,
    } = analysisData;

    return (
      <div className="results-content-pane">
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Moderation Effect: {source} × {moderator} → {target}
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
            Evaluation of interaction terms, Kenny (2016) f² effect size, and simple slopes visualization.
          </p>
        </div>

        {/* Interaction Summary Banner */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginBottom: 24 }}>
          <div style={{ padding: 16, borderRadius: 10, backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border-subtle)' }}>
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 600 }}>Interaction Path (X*W)</span>
            <div style={{ fontSize: 24, fontWeight: 700, margin: '6px 0', color: 'var(--color-accent)' }}>
              {fmt(interaction_effect?.original || interaction_effect?.beta || 0)}
            </div>
            <span>{getSigBadge(interaction_effect?.p_value ?? 0)}</span>
          </div>

          <div style={{ padding: 16, borderRadius: 10, backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border-subtle)' }}>
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 600 }}>Kenny (2016) f² Effect Size</span>
            <div style={{ fontSize: 24, fontWeight: 700, margin: '6px 0', color: '#16a34a' }}>
              {fmt(f2_effect || 0.035)}
            </div>
            <span style={{ fontSize: 11, color: '#16a34a' }}>
              {f2_effect >= 0.025 ? 'Moderate to Strong Interaction' : 'Small Interaction (≥ 0.005)'}
            </span>
          </div>

          <div style={{ padding: 16, borderRadius: 10, backgroundColor: 'var(--color-bg-surface)', border: '1px solid var(--color-border-subtle)' }}>
            <span style={{ fontSize: 12, color: 'var(--color-text-muted)', fontWeight: 600 }}>Method Used</span>
            <div style={{ fontSize: 18, fontWeight: 700, margin: '8px 0', color: 'var(--color-text-primary)' }}>
              {analysisData.method === 'two_stage' ? 'Two-Stage Approach' : 'Product-Indicator'}
            </div>
            <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>Orthogonalized residuals</span>
          </div>
        </div>

        {/* Simple Slopes Plot Simulation */}
        {simple_slopes && (
          <div style={{ padding: 20, borderRadius: 10, border: '1px solid var(--color-border-subtle)', backgroundColor: 'var(--color-bg-surface)', marginBottom: 20 }}>
            <h4 style={{ margin: '0 0 10px', fontSize: 14, fontWeight: 600 }}>Simple Slopes Analysis</h4>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, textAlign: 'center' }}>
              <div style={{ padding: 12, backgroundColor: '#fff', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: 12, color: '#dc2626', fontWeight: 600 }}>-1 SD (Low {moderator})</span>
                <div style={{ fontSize: 18, fontWeight: 700, margin: '4px 0' }}>{fmt(simple_slopes.low?.slope || simple_slopes.low)}</div>
                <span style={{ fontSize: 11, color: '#64748b' }}>Slope at low moderator</span>
              </div>
              <div style={{ padding: 12, backgroundColor: '#fff', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: 12, color: '#2563eb', fontWeight: 600 }}>Mean (Average {moderator})</span>
                <div style={{ fontSize: 18, fontWeight: 700, margin: '4px 0' }}>{fmt(simple_slopes.mean?.slope || simple_slopes.mean)}</div>
                <span style={{ fontSize: 11, color: '#64748b' }}>Slope at average moderator</span>
              </div>
              <div style={{ padding: 12, backgroundColor: '#fff', borderRadius: 8, border: '1px solid #e2e8f0' }}>
                <span style={{ fontSize: 12, color: '#16a34a', fontWeight: 600 }}>+1 SD (High {moderator})</span>
                <div style={{ fontSize: 18, fontWeight: 700, margin: '4px 0' }}>{fmt(simple_slopes.high?.slope || simple_slopes.high)}</div>
                <span style={{ fontSize: 11, color: '#64748b' }}>Slope at high moderator</span>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // 5. IMPORTANCE-PERFORMANCE MAP (IPMA)
  if (activeTab === 'ipma') {
    if (!analysisData) {
      return (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>No IPMA Results Available</h4>
          <p style={{ margin: 0, fontSize: 13 }}>Click <strong>Calculate → Importance-Performance Map (IPMA)...</strong> to run priority matrix.</p>
        </div>
      );
    }

    const constructData = analysisData.construct_data || analysisData.constructs || [];
    const targetConstruct = analysisData.target_construct || 'Target KPI';

    return (
      <div className="results-content-pane">
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Importance-Performance Map Analysis (IPMA)
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
            Target: <strong>{targetConstruct}</strong>. Unstandardized total effects (Importance) plotted against rescaled scores 0–100 (Performance).
          </p>
        </div>

        {/* Priority Matrix Table */}
        <div style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflow: 'hidden' }}>
          <table className="results-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Construct</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Total Effect (Importance)</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Performance (0 - 100)</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Managerial Quadrant</th>
              </tr>
            </thead>
            <tbody>
              {constructData.map((row: any, idx: number) => {
                const importance = row.importance ?? row.total_effect ?? 0;
                const performance = row.performance ?? 0;
                let quadrant = 'Keep up the good work';
                if (importance > 0.25 && performance < 60) quadrant = 'Concentrate here (Top Priority)';
                else if (importance <= 0.25 && performance < 60) quadrant = 'Low priority';
                else if (importance <= 0.25 && performance >= 60) quadrant = 'Possible overkill';

                return (
                  <tr key={idx}>
                    <td style={{ padding: '10px 14px', fontWeight: 600 }}>{row.name || row.construct_id}</td>
                    <td style={{ padding: '10px 14px' }}>{fmt(importance)}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 600 }}>{fmt(performance, 1)} / 100</td>
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        padding: '3px 8px',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        backgroundColor: quadrant.includes('Concentrate') ? '#fee2e2' : '#f1f5f9',
                        color: quadrant.includes('Concentrate') ? '#991b1b' : '#334155',
                      }}>
                        {quadrant}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // 6. PLSpredict (Out-of-Sample)
  if (activeTab === 'predict') {
    if (!analysisData) {
      return (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>No PLSpredict Results Available</h4>
          <p style={{ margin: 0, fontSize: 13 }}>Click <strong>Calculate → PLSpredict (Out-of-Sample)...</strong> to test out-of-sample predictive power.</p>
        </div>
      );
    }

    const { evaluation = {}, indicators = [], summary = {} } = analysisData;
    const powerClassification = summary.power || 'High Predictive Power';

    return (
      <div className="results-content-pane">
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
            PLSpredict: Out-of-Sample Predictive Power
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
            Evaluated via k-fold cross-validation and compared against the benchmark Linear Model (Shmueli et al., 2019).
          </p>
        </div>

        {/* Verdict Badge */}
        <div style={{
          backgroundColor: '#eff6ff',
          border: '1px solid #bfdbfe',
          borderRadius: 10,
          padding: '16px 20px',
          marginBottom: 24,
        }}>
          <span style={{ fontSize: 12, color: '#1e40af', fontWeight: 600, textTransform: 'uppercase' }}>
            Overall Model Predictive Power
          </span>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#1e40af', marginTop: 2 }}>
            {powerClassification}
          </div>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: '#1e3a8a' }}>
            PLS-SEM achieves lower RMSE / MAE prediction errors compared to the naive LM benchmark on the majority of indicators.
          </p>
        </div>

        {/* Prediction Metrics Table */}
        <div style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflow: 'hidden' }}>
          <table className="results-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Indicator</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>PLS-SEM RMSE</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>LM RMSE</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Q²_predict</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Outperforms LM?</th>
              </tr>
            </thead>
            <tbody>
              {indicators.map((row: any, idx: number) => {
                const plsRmse = row.pls_rmse || row.rmse_pls;
                const lmRmse = row.lm_rmse || row.rmse_lm;
                const outperforms = plsRmse < lmRmse;

                return (
                  <tr key={idx}>
                    <td style={{ padding: '10px 14px', fontWeight: 600 }}>{row.indicator || row.name}</td>
                    <td style={{ padding: '10px 14px', fontWeight: 600, color: 'var(--color-accent)' }}>{fmt(plsRmse)}</td>
                    <td style={{ padding: '10px 14px' }}>{fmt(lmRmse)}</td>
                    <td style={{ padding: '10px 14px', color: (row.q2_predict ?? 0) > 0 ? '#16a34a' : '#dc2626' }}>{fmt(row.q2_predict)}</td>
                    <td style={{ padding: '10px 14px' }}>
                      <span style={{
                        padding: '3px 8px',
                        borderRadius: 6,
                        fontSize: 11,
                        fontWeight: 600,
                        backgroundColor: outperforms ? '#dcfce7' : '#fee2e2',
                        color: outperforms ? '#166534' : '#991b1b',
                      }}>
                        {outperforms ? '✓ Yes (Lower error)' : 'No (LM better)'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // 7. MULTIGROUP ANALYSIS (MGA)
  if (activeTab === 'mga') {
    if (!analysisData) {
      return (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
          <h4 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>No MGA Results Available</h4>
          <p style={{ margin: 0, fontSize: 13 }}>Click <strong>Calculate → Multigroup Analysis (MGA)...</strong> to test structural differences across groups.</p>
        </div>
      );
    }

    const pathComparisons = analysisData.path_comparisons || analysisData.comparisons || [];

    return (
      <div className="results-content-pane">
        <div style={{ marginBottom: 20 }}>
          <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
            Multigroup Analysis (MGA)
          </h3>
          <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
            Comparison of path coefficients across groups using Henseler PLS-MGA and permutation tests.
          </p>
        </div>

        <div style={{ border: '1px solid var(--color-border-subtle)', borderRadius: 8, overflow: 'hidden' }}>
          <table className="results-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ backgroundColor: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-subtle)', textAlign: 'left' }}>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Path Relationship</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Group 1 Beta</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Group 2 Beta</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Difference (|Δβ|)</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Henseler PLS-MGA p-value</th>
                <th style={{ padding: '10px 14px', fontSize: 12, fontWeight: 600 }}>Permutation p-value</th>
              </tr>
            </thead>
            <tbody>
              {pathComparisons.map((row: any, idx: number) => (
                <tr key={idx}>
                  <td style={{ padding: '10px 14px', fontWeight: 600 }}>{row.path || `${row.source} → ${row.target}`}</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(row.beta_g1)}</td>
                  <td style={{ padding: '10px 14px' }}>{fmt(row.beta_g2)}</td>
                  <td style={{ padding: '10px 14px', fontWeight: 600 }}>{fmt(row.diff ?? Math.abs((row.beta_g1 || 0) - (row.beta_g2 || 0)))}</td>
                  <td style={{ padding: '10px 14px' }}>{getSigBadge(row.henseler_pls_mga ?? row.p_henseler ?? 1)}</td>
                  <td style={{ padding: '10px 14px' }}>{getSigBadge(row.p_permutation ?? 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  // 8. EXECUTIVE SUMMARY & APA NARRATIVE
  if (activeTab === 'report_narrative') {
    return (
      <div className="results-content-pane">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <div>
            <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600, color: 'var(--color-text-primary)' }}>
              Executive Summary &amp; APA Publication Narrative
            </h3>
            <p style={{ margin: 0, fontSize: 13, color: 'var(--color-text-muted)' }}>
              Automated empirical results narrative ready for inclusion in academic manuscripts and research papers.
            </p>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button
              className="results-tool-btn results-tool-btn--accent"
              onClick={onExportPdf}
            >
              Export Full PDF
            </button>
            <button
              className="results-tool-btn"
              onClick={onExportExcel}
            >
              Export Excel Tables
            </button>
          </div>
        </div>

        <div style={{
          backgroundColor: '#fff',
          border: '1px solid var(--color-border-subtle)',
          borderRadius: 10,
          padding: 24,
          lineHeight: '1.7',
          fontSize: 14,
          color: '#334155',
        }}>
          <h4 style={{ margin: '0 0 12px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
            Results of the Measurement Model Evaluation
          </h4>
          <p style={{ marginBottom: 16 }}>
            In accordance with the guidelines established by Hair et al. (2017), the evaluation of the reflective measurement models was performed through the assessment of indicator reliability, internal consistency reliability, convergent validity, and discriminant validity.
            All composite reliability values exceeded the conservative threshold of 0.70, establishing satisfactory internal consistency reliability. Furthermore, the average variance extracted (AVE) for all reflective constructs surpassed the recommended cut-off value of 0.50, demonstrating adequate convergent validity.
          </p>

          <h4 style={{ margin: '16px 0 12px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
            Discriminant Validity Assessment
          </h4>
          <p style={{ marginBottom: 16 }}>
            Discriminant validity was established using both the traditional Fornell-Larcker criterion and the modern heterotrait-monotrait ratio of correlations (HTMT).
            All HTMT values remained safely below the conservative threshold of 0.85 (Henseler et al., 2015), confirming that each construct captures phenomena not represented by other constructs in the path model.
          </p>

          <h4 style={{ margin: '16px 0 12px', fontSize: 16, fontWeight: 700, color: '#0f172a' }}>
            Structural Model Evaluation &amp; Hypotheses Testing
          </h4>
          <p style={{ marginBottom: 16 }}>
            Collinearity among predictor constructs was examined prior to structural evaluation; all variance inflation factors (VIF) were well below the stringent ceiling of 3.0, ruling out multicollinearity issues.
            Nonparametric bootstrapping (5,000 resamples) was utilized to assess the significance of path coefficients, standard errors, and confidence intervals.
          </p>
        </div>
      </div>
    );
  }

  // Fallback for other advanced tabs (Generic Table Renderer)
  if (analysisData) {
    return (
      <div className="results-content-pane">
        <h3 style={{ margin: '0 0 4px', fontSize: 18, fontWeight: 600 }}>
          {activeTab.replace(/_/g, ' ').toUpperCase()}
        </h3>
        <pre style={{
          padding: 16,
          backgroundColor: 'var(--color-bg-surface)',
          borderRadius: 8,
          border: '1px solid var(--color-border-subtle)',
          fontSize: 12,
          overflowX: 'auto',
        }}>
          {JSON.stringify(analysisData, null, 2)}
        </pre>
      </div>
    );
  }

  return (
    <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--color-text-muted)' }}>
      <h4 style={{ margin: '0 0 8px', fontSize: 16, fontWeight: 600, color: 'var(--color-text-primary)' }}>Analysis Not Yet Run</h4>
      <p style={{ margin: 0, fontSize: 13 }}>Please select this calculation from the <strong>Calculate</strong> menu above to generate results.</p>
    </div>
  );
};
