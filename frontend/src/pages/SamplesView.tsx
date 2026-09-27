import React, { useState } from 'react';
import { useStore } from '../store';
import AppSidebar from '../components/AppSidebar';

interface SampleProject {
  id: string;
  title: string;
  tag: string;
  constructs: number;
  indicators: number;
  sampleSize: number;
  description: string;
}

const SAMPLE_PROJECTS: SampleProject[] = [
  {
    id: 'corp-rep',
    title: 'Corporate Reputation Model',
    tag: 'Reflective-Formative',
    constructs: 6,
    indicators: 21,
    sampleSize: 344,
    description: 'Benchmark study from Hair et al. (2022). Examines how Competence and Likeability drive Customer Satisfaction and Loyalty.',
  },
  {
    id: 'acsi-ecsi',
    title: 'Customer Satisfaction Index (ACSI / ECSI)',
    tag: 'Reflective Paths',
    constructs: 7,
    indicators: 24,
    sampleSize: 250,
    description: 'European Customer Satisfaction Index with consistent PLSc estimation for pure latent factor structures.',
  },
  {
    id: 'tam3',
    title: 'Technology Acceptance Model (TAM 3)',
    tag: 'Moderation & Mediation',
    constructs: 8,
    indicators: 28,
    sampleSize: 412,
    description: 'Investigates Perceived Usefulness, Perceived Ease of Use, and Computer Self-Efficacy with two-stage interaction terms.',
  },
  {
    id: 'meta-mod',
    title: 'Latent Moderation & Multi-Group Analysis',
    tag: 'Two-Stage Moderation',
    constructs: 5,
    indicators: 18,
    sampleSize: 520,
    description: 'Template demonstrating continuous moderator interaction via orthogonalized indicators and non-parametric MICOM testing.',
  },
  {
    id: 'ecom-trust',
    title: 'E-Commerce Trust & Purchase Intention',
    tag: 'Consumer Behavior',
    constructs: 5,
    indicators: 19,
    sampleSize: 380,
    description: 'Cross-sectional study examining Website Usability, Security Perception, Institutional Trust, and Repurchase Intention.',
  },
  {
    id: 'htmt2-benchmark',
    title: 'HTMT2 Cross-Loading Benchmark Study',
    tag: 'Discriminant Validity',
    constructs: 4,
    indicators: 16,
    sampleSize: 300,
    description: 'Demonstration dataset designed to evaluate discriminant validity boundaries between closely correlated constructs.',
  },
];

export const SamplesView: React.FC = () => {
  const { workspaces, activeWorkspaceId, setActiveWorkspace, openTab, addWorkspace } = useStore();

  const handleOpenSample = (project: SampleProject) => {
    const existingWs = workspaces.find((w) => w.id === activeWorkspaceId) || workspaces[0];
    if (existingWs) {
      setActiveWorkspace(existingWs.id);
      openTab({ type: 'workspace', title: existingWs.name, workspaceId: existingWs.id });
    } else {
      const sampleWsId = `sample_ws_${Date.now()}`;
      addWorkspace({
        id: sampleWsId,
        name: project.title,
        path: '',
      });
      setActiveWorkspace(sampleWsId);
      openTab({ type: 'workspace', title: project.title, workspaceId: sampleWsId });
    }
  };

  return (
    <div className="app-body">
      <AppSidebar activeNav="samples" />

      <main className="main-content">
        <div className="main-content__inner">
          <div className="page-header animate-fade-in">
            <div className="page-header__text">
              <h1 className="page-header__title">Sample Projects</h1>
              <p className="page-header__subtitle">Explore guided models and standard benchmark datasets to get started.</p>
            </div>
          </div>

          <div className="project-list animate-fade-in">
            {SAMPLE_PROJECTS.map((project) => (
              <div
                key={project.id}
                className="project-card"
                onClick={() => handleOpenSample(project)}
                style={{ cursor: 'pointer' }}
              >
                <div className="project-card__content">
                  <div className="project-card__icon">
                    <span className="material-symbols-outlined">science</span>
                  </div>
                  <div className="project-card__info">
                    <div className="project-card__title-row">
                      <h3 className="project-card__title">{project.title}</h3>
                      <span className="project-card__badge project-card__badge--accent">{project.tag}</span>
                    </div>
                    <p className="project-card__desc">{project.description}</p>
                    <div className="project-card__meta">
                      <span>{project.constructs} constructs</span>
                      <span className="project-card__meta-dot">·</span>
                      <span>{project.indicators} indicators</span>
                      <span className="project-card__meta-dot">·</span>
                      <span>N = {project.sampleSize}</span>
                    </div>
                  </div>
                </div>
                <button
                  className="project-card__open-btn"
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleOpenSample(project);
                  }}
                >
                  <span>Open</span>
                  <span className="material-symbols-outlined">arrow_forward</span>
                </button>
              </div>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
};

export default SamplesView;
