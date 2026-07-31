# Changelog

## 0.2.4 - 2026-07-31

- Restored Python 3.10 compatibility by replacing the Python 3.11-only `StrEnum` dependency.
- Added a backend readiness check to the unified dev launcher before Vite starts.
- Made backend startup failures print their error log directly in the terminal.

## 0.2.3 - 2026-07-31

- Fixed the unified dev launcher to prefer `python` over a broken `py` launcher fallback.
- Prevented false backend-offline states caused by the backend process never starting on some Windows setups.

## 0.2.2 - 2026-07-31

- Added a root `pnpm dev` command to launch FastAPI and Vite together.
- Added a PowerShell dev launcher that starts the backend, streams the frontend, and stops the backend on exit.
- Added Python command fallback when `backend\.venv` is missing.
- Updated project docs and version metadata for the unified local startup flow.

## 0.2.1 - 2026-07-31

- Changed paste intake from local zone capture to full-page clipboard capture.
- Replaced the mode dropdown with three always-visible mode cards.
- Made the create button always clickable and added clearer submit-state hints.
- Updated single image mode to create one queued job per image in batch submission.
- Added friendlier frontend messaging when the backend service is offline.

## 0.2.0 - 2026-07-31

- Reworked the job model around `single_image`, `multi_image`, and `video` modes.
- Added quality selection from `1` to `5` on both frontend and backend.
- Added a paste-to-preview intake area with drag-and-drop and file picker support.
- Added frontend-side asset preview cards and richer queue summaries.
- Improved API error reporting and added backend validation tests for mode constraints.

## 0.1.0 - 2026-07-31

- Recreated the project with a Python FastAPI backend and Vue/Vite frontend.
- Added health check and media job API scaffolding.
- Added a Vue workspace UI for health status and media job creation.
