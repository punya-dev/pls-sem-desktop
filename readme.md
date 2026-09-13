# PLS-SEM + CB-SEM Desktop App — Full Build Plan

Stack: **Tauri (Rust shell) + React (frontend) + Python/FastAPI (backend engine)**
Target: fully offline desktop app, Windows/macOS/Linux.

---

## PHASE 0 — Environment & Skeleton

**Goal:** prove the full chain works (Tauri window → React UI → Python sidecar → response) before writing any real feature.

### 0.1 Install toolchain
- Node.js (LTS) + npm/pnpm
- Rust (via `rustup`) — required by Tauri
- Python 3.11+ (pin a version, e.g. via `pyenv`)
- Tauri CLI: `cargo install tauri-cli` or `npm install -D @tauri-apps/cli`

I have completed this -> node, npm, tauri, cargo, rustup, python 3.14. all installed and done.

### 0.2 Scaffold frontend
```
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install
```
Use TypeScript from day one — with this many data structures (model specs, results, matrices) type safety will save you real time.

Made the frontend and deleted the initial vite BS now it is clean with the files and structre.

### 0.3 Scaffold Tauri
```
npm install -D @tauri-apps/cli
npx tauri init
```
Point `tauri.conf.json`'s `build.distDir` at `frontend/dist`, `devPath` at `http://localhost:5173`.

### 0.4 Scaffold Python backend
```
backend/
├── main.py
├── requirements.txt   # fastapi, uvicorn, numpy, scipy, pandas, pydantic
└── venv/
```
Minimal `main.py`:
```python
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
```
Run locally: `uvicorn main:app --port 8721`

### 0.5 Wire Tauri → Python sidecar
- Add Python backend as a Tauri "sidecar" binary (Tauri's `externalBin` config) so it launches automatically with the app and shuts down when the app closes.
- For dev: run Python manually + Vite dev server, point React at `http://127.0.0.1:8721`.
- For prod: PyInstaller will later bundle `main.py` into a standalone exe; Tauri spawns that exe as a subprocess on startup and kills it on exit (handle this in Rust's `main.rs` using `tauri::api::process::Command`).

### 0.6 Validate end-to-end
React app calls `/health` on mount, displays "Backend connected ✅". **Do not proceed until this works reliably**, including a full `tauri build` producing a working packaged app on your OS. This is the highest-risk integration point in the whole project.

---
Phase 0 complete everyting works able to download the app and run it on local machine. currently just tells if backend is running or not.

## PHASE 1 — Data Layer

### 1.1 Data import
- Backend endpoint: `POST /data/import` accepting CSV/Excel (via `pandas.read_csv` / `read_excel`)
- Return: column names, dtypes, row count, preview (first ~20 rows) as JSON
- Frontend: file picker (Tauri's native dialog API `@tauri-apps/api/dialog`), preview table

### 1.2 Data diagnostics
- Descriptive stats endpoint: mean, std, min/max, skewness, kurtosis per column (pandas/scipy)
- Missing value report + treatment options: listwise deletion, mean imputation, EM (can defer EM to later)
- Normality checks (useful later for CB-SEM which is more sensitive to non-normality): Mardia's test if you want to be thorough, or simpler skew/kurtosis flags for v1

### 1.3 Local project file format
Decide now — this underlies everything:
- **Recommended:** a single-file **SQLite** project file (`.pls` extension) with tables for: raw data, model spec (JSON blob), results (JSON blob per run), metadata. SQLite gives you atomic saves, easy versioning, and it's trivially bundled via Python's built-in `sqlite3`.
- Alternative (simpler but less robust): a folder or zip containing `data.csv` + `model.json` + `results.json`.
- Build `project_io.py`: `create_project()`, `save_project()`, `load_project()`, `list_recent()`

### 1.4 Frontend: project shell UI
- New Project / Open Project / Recent Projects screen
- Basic app shell: sidebar (Data / Model / Results) + main canvas area

---

## PHASE 2 — Model Builder (Canvas)

This is your visual differentiator — invest real design time here.

### 2.1 Choose canvas library
Use **React Flow**. It handles pan/zoom/drag/edge-drawing out of the box and is the standard choice for node-edge editors like this.

### 2.2 Data model for the path diagram
Define a strict schema up front (e.g. via Zod on frontend, Pydantic on backend) — both algorithms will consume this same spec:
```json
{
  "constructs": [
    {"id": "C1", "name": "Satisfaction", "type": "reflective", "indicators": ["Q1","Q2","Q3"]}
  ],
  "indicators": [
    {"id": "Q1", "column": "survey_q1"}
  ],
  "paths": [
    {"from": "C1", "to": "C2"}
  ]
}
```
- Support both **reflective** and **formative** measurement modes per construct (toggle in UI)
- Support renaming, deleting, reconnecting nodes/edges
- Validate the diagram structurally before allowing "Run": no orphan indicators, no cycles (unless you explicitly want to support non-recursive vs recursive models — start with non-recursive/no-cycles for v1), every construct has ≥1 indicator (or ≥2/3 depending on your minimum-indicator rule)

### 2.3 Canvas UI features
- Drag indicators from a sidebar (populated from imported data columns) onto constructs
- Draw directional arrows between constructs (structural paths)
- Visual distinction: reflective (arrows construct→indicator) vs formative (indicator→construct) — mirror SmartPLS's visual convention so users feel at home
- Save/load diagram state into the project file (Phase 1.3)

### 2.4 Serialize to model spec
Button: "Run Analysis" → convert canvas state to the JSON model spec → POST to backend.

---

## PHASE 3 — PLS-SEM Engine

Build this as `backend/engine/pls/`.

### 3.1 Core iterative algorithm
Implement the classic Wold/Lohmöller algorithm:
1. Initialize outer weights (equal weights or unit weights)
2. Outer approximation: compute construct scores from indicators × weights
3. Inner approximation: update construct scores using path/centroid/factor weighting scheme
4. Outer weights update: regress indicators on inner-approximated scores (mode A for reflective, mode B for formative)
5. Repeat until weights converge (tolerance e.g. 1e-7) or max iterations hit

### 3.2 Structural model estimation
- Path coefficients via OLS regression of each endogenous construct on its predecessors
- R², adjusted R² per endogenous construct
- f² effect sizes (compare R² with/without each predictor)

### 3.3 Measurement model quality metrics
- Outer loadings/weights + their significance (from bootstrap, Phase 4)
- Reliability: Cronbach's alpha, Composite Reliability (CR), rho_A
- Convergent validity: AVE
- Discriminant validity: HTMT ratio, Fornell-Larcker criterion
- Collinearity: VIF for both outer (formative) and inner model predictors

### 3.4 Validation
- Get SmartPLS's published example datasets (they have well-known sample models, e.g. the "corporate reputation" model in their docs/tutorials) and compare your engine's output numbers against documented results before trusting it on anything else.
- Write unit tests comparing computed values to known reference outputs within a small tolerance.

---

## PHASE 4 — Bootstrapping & Significance (PLS)

### 4.1 Bootstrap procedure
- Resample cases with replacement (n = original sample size), re-run the full PLS algorithm, repeat 500–10,000 times (make this user-configurable)
- Collect distribution of path coefficients, loadings, weights across resamples
- Compute: standard errors, t-values, p-values (two-tailed), confidence intervals (percentile or bias-corrected)

### 4.2 Performance
- Use Python's `multiprocessing.Pool` to parallelize resamples across CPU cores — bootstrapping is embarrassingly parallel
- Stream progress back to frontend via **WebSocket** (`/ws/bootstrap-progress`) so the UI shows a live progress bar instead of freezing
- Allow cancellation mid-run

---

## PHASE 5 — Reporting & Results UI (PLS, v1 complete here)

### 5.1 Results visualization
- Overlay path coefficients + significance stars/colors directly on the React Flow diagram (reuse Phase 2 canvas in "read-only results" mode)
- Tables: outer loadings/weights, path coefficients with CI/p-values, R²/f²/Q², reliability & validity metrics, HTMT matrix, VIF

### 5.2 Export
- PDF export (e.g. `reportlab` or render an HTML report and print-to-PDF via a headless approach)
- Excel export of all metric tables (`openpyxl`/pandas `to_excel`)

**Milestone: at this point you have a complete, working PLS-SEM tool end to end. This is your realistic v1 — get here before starting CB-SEM.**

---

## PHASE 6 — CB-SEM Engine

Build this as `backend/engine/cbsem/`, sharing the model spec format from Phase 2 but with a fully separate estimation approach.

### 6.1 Model-implied covariance matrix
- From the path spec, build the structural equations and measurement equations
- Parameterize: factor loadings (Λ), structural coefficients (Β, Γ), latent variances/covariances (Φ, Ψ), error variances (Θ)
- Construct Σ(θ), the model-implied covariance matrix, as a function of free parameters θ

### 6.2 Estimation (Maximum Likelihood)
- Objective: minimize the ML fit function `F_ML = log|Σ(θ)| + tr(S·Σ(θ)⁻¹) − log|S| − p`, where S is the observed sample covariance matrix
- Use `scipy.optimize.minimize` (e.g. L-BFGS-B or trust-region methods) with parameter constraints (variances ≥ 0)
- Handle identification: check degrees of freedom (df = unique covariances/variances − free parameters) before attempting estimation; refuse/warn on under-identified models
- Handle Heywood cases (negative variance estimates) — a known headache in CB-SEM; add boundary constraints and flag these to the user rather than silently failing

### 6.3 Reference implementation
- Don't build this purely from textbook formulas — cross-check logic against **`semopy`** (Python) or **`lavaan`** (R) source/output. Run the same dataset through `semopy` and your engine and compare numerically until they match. This de-risks the hardest part of the whole project.

### 6.4 Fit indices
- Chi-square test statistic + df + p-value
- CFI, TLI (incremental fit)
- RMSEA (+ confidence interval)
- SRMR
- AIC, BIC (for model comparison later)

### 6.5 Standard errors & significance
- Derive standard errors from the inverse Hessian (information matrix) at the ML solution — standard asymptotic theory
- Compute z-values/p-values for each parameter
- (Optional, later) bootstrap SEs for non-normal data as an alternative

---

## PHASE 7 — Unify Results UX Across Algorithms

### 7.1 Algorithm selector
- Let the user choose PLS-SEM or CB-SEM per project/run (some models are only sensible for one — add basic guardrails/warnings, e.g. formative constructs are awkward in traditional CB-SEM)

### 7.2 Shared result interface
Design a common backend response shape so the frontend doesn't need two entirely separate result UIs:
```json
{
  "algorithm": "pls" | "cbsem",
  "structural": {...},
  "measurement": {...},
  "fit_or_quality": {...},   // R²/f²/Q² for PLS, fit indices for CB-SEM
  "significance": {...}
}
```
Branch only the parts that genuinely differ (fit indices vs R²-based quality) in the UI; keep diagram overlay, tables layout, and export shared.

---

## PHASE 8 — Advanced Features (post-MVP)

**PLS-SEM:**
- Importance-Performance Map Analysis (IPMA)
- Mediation analysis (direct/indirect/total effects, VAF)
- Multi-group analysis (MGA) / measurement invariance (MICOM)
- Higher-order (hierarchical component) models

**CB-SEM:**
- Modification indices (suggest freeing constrained parameters to improve fit)
- Multi-group CFA / invariance testing
- Model comparison (nested chi-square difference tests, AIC/BIC comparison)

**Both:**
- Model templates / sample datasets bundled with the app
- Themeable diagram styling, export-ready figure styling
- PDF report templates (branded, customizable)

---

## PHASE 9 — Packaging & Distribution

### 9.1 Bundle Python backend
- Use **PyInstaller** (`--onefile` or `--onedir`) to freeze `backend/main.py` + all dependencies (numpy/scipy/pandas/statsmodels) into a standalone executable
- Test the frozen exe standalone (outside Tauri) first — catch missing hidden imports early
- Watch bundle size: numpy/scipy alone can push this to 150–300MB; acceptable for a desktop analytics tool, but be aware

### 9.2 Tauri build
- Configure `externalBin` in `tauri.conf.json` to point at your PyInstaller output, per-platform
- `tauri build` produces native installers: `.msi`/`.exe` (Windows), `.dmg`/`.app` (macOS), `.deb`/`.AppImage` (Linux)

### 9.3 Offline audit
Before shipping, grep the whole codebase for outbound calls:
- No CDN-loaded fonts/scripts in the React build (bundle everything locally)
- No telemetry in any npm/pip dependency (check `requirements.txt` and `package.json` dependencies for anything phone-home by default, e.g. some analytics-instrumented UI kits)
- FastAPI bound strictly to `127.0.0.1`, never `0.0.0.0`

### 9.4 (Optional) Auto-update
- Tauri has a built-in updater — can work fully offline-first if you just ship update bundles alongside the app rather than requiring a live server (or skip this for v1 and do manual version releases)

---

## Suggested Execution Order (Summary)

1. Phase 0 — skeleton & sidecar wiring (get this rock solid first)
2. Phase 1 — data import/project files
3. Phase 2 — model builder canvas
4. Phase 3 — PLS-SEM engine
5. Phase 4 — bootstrapping
6. Phase 5 — PLS reporting → **v1 milestone: working PLS-SEM tool**
7. Phase 6 — CB-SEM engine (hardest phase, budget the most time/buffer here)
8. Phase 7 — unify UX
9. Phase 8 — advanced features
10. Phase 9 — packaging & ship

Each phase should end with something runnable and testable — don't move to the next phase with a half-working previous one, since the algorithm phases especially compound in complexity.
