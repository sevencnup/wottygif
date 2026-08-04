# Changelog

## 0.3.24 - 2026-08-04

- Added live elapsed-time and selected-duration labels to desktop and mobile video previews.
- Replaced the fixed timeline fill with progress driven by each visible video's current playback time.
- Made preview playback honor the selected clip start and end, pause at the end, and restart from the clip beginning.

## 0.3.23 - 2026-08-04

- Moved desktop video cropping into the production preview and mobile video cropping into the source preview, removing both duplicate crop videos.
- Bound mobile source and desktop/mobile production controls directly to their own preview video elements and playback states.
- Removed duplicate center-overlay preview buttons and stabilized toolbar icon geometry so controls no longer jump when their icon changes.

## 0.3.22 - 2026-08-04

- Added automatic cleanup for completed GIF results one hour after their completion time.
- Removed expired result files, completed-job records, and persisted metadata entries together.
- Added startup, periodic, and request-time cleanup so expired cache files are recovered after service pauses or restarts.

## 0.3.21 - 2026-08-04

- Added working video play and pause controls to source previews, crop editors, and production previews.
- Kept confirmed video crops visible in preview while avoiding forced autoplay or loop behavior.
- Added video segment start and end controls directly on the desktop and mobile production preview screens.

## 0.3.20 - 2026-08-03

- Removed the browser-default gray backgrounds from mobile bottom navigation buttons.
- Replaced the hand-drawn CSS navigation symbols with official `@lucide/vue` icon components.
- Kept a stable 48 px tap target while using blue text and icons as the only active-state treatment.

## 0.3.19 - 2026-08-03

- Persisted media job metadata beside generated results so completed jobs survive backend restarts.
- Recovered existing GIF files without metadata as downloadable historical results on startup.
- Refreshed the frontend job list continuously and immediately when opening the completed screen.

## 0.3.18 - 2026-08-03

- Preserved image and video asset groups when switching production modes, including the selected asset and image crop workflow state.
- Moved image crop manipulation into the existing desktop production preview and mobile source preview instead of rendering a duplicate crop canvas.
- Restored the confirmed cropped preview after the final confirmation while keeping a direct recrop command on desktop and mobile.

## 0.3.17 - 2026-08-03

- Replaced the purple accent system with a consistent solid-blue theme across desktop and mobile controls.
- Removed the remaining mobile background and active-state gradients.
- Increased the large-screen web workspace to 110% while preserving the existing compact mobile scale and responsive breakpoints.

## 0.3.16 - 2026-08-03

- Fixed confirmed video crops so the source and production previews immediately show the selected frame area.
- Applied the same confirmed-crop preview behavior to single-image and multi-image modes without leaking crop state between assets.
- Kept unconfirmed crop drafts out of the normal preview surfaces and preserved the true aspect ratio of narrow or wide crops.

## 0.3.15 - 2026-08-03

- Added real per-image cropping for single-image and multi-image jobs before Pillow resizing and GIF encoding.
- Added a guided desktop and mobile crop workflow that requires confirm or skip before switching images.
- Added per-image pending, cropped, and skipped states with previous-image recropping and automatic next-image progression.
- Fixed portrait mobile previews to size from the image's natural aspect ratio so the entire image remains visible.
- Added ordered image crop options to the multipart API and expanded backend coverage to 13 tests.

## 0.3.14 - 2026-08-03

- Fixed mobile configuration pages so their content scrolls inside the available viewport.
- Added a shared mobile asset workspace with full previews, asset selection, removal, reordering, and additional uploads for all three modes.
- Added explicit video crop confirmation and cancellation before entering preview or generating output.
- Turned the mobile preview tools into working navigation commands that reopen material, trim, crop, and quality editing.

## 0.3.13 - 2026-08-03

- Added an interactive video crop canvas to desktop and mobile editors.
- Added draggable crop positioning and eight resize handles, including direct left/right width adjustment.
- Added synchronized crop width and height sliders while retaining precise percentage inputs.

## 0.3.12 - 2026-08-03

- Fixed the mobile shell to stretch edge-to-edge instead of leaving wide side gutters.
- Replaced the mobile bottom-tab text glyphs with stable CSS-drawn navigation icons.

## 0.3.11 - 2026-08-03

- Reworked the mobile web experience into an app-style multi-screen flow.
- Added dedicated mobile home, mode configuration, preview, completed list, and result detail views.
- Kept the desktop three-column workbench while switching phones to the new mobile shell.

## 0.3.10 - 2026-08-03

- Added video trim controls for start and end time in the web editor.
- Added percentage-based video frame cropping before FFmpeg GIF generation.
- Changed video validation to allow long source videos as long as the selected segment stays within 30 seconds.

## 0.3.9 - 2026-08-03

- Removed the `2K/4K` quality option from the web UI.
- Rebalanced the quality card grid for four presets across desktop and mobile layouts.

## 0.3.8 - 2026-08-03

- Rebuilt the web UI around the provided three-column GIF maker reference.
- Added a dedicated left control rail, central production preview, and completed-result rail.
- Tightened portrait and landscape mobile layouts so the main generation flow stays in one viewport.

## 0.3.7 - 2026-08-01

- Reworked the web UI toward the provided three-column reference layout.
- Added a large production preview surface with a horizontal material strip.
- Restyled the mode selection and completed jobs panels with soft white cards and purple accents.

## 0.3.6 - 2026-08-01

- Reverted the dark workbench UI redesign.
- Restored the previous light workspace styling while keeping LAN access and mobile file selection fixes.

## 0.3.5 - 2026-08-01

- Reworked the frontend into a higher-contrast dark workbench with solid color blocks.
- Removed most divider-style borders and pale layered surfaces from the UI.
- Strengthened the mobile material intake area, mode controls, queues, and result cards.

## 0.3.4 - 2026-08-01

- Made the whole material intake area clickable so mobile users can tap the panel to choose files.
- Kept the hidden file input in the layout for better mobile browser compatibility.
- Enlarged the mobile material intake target and clarified the selection text.

## 0.3.3 - 2026-08-01

- Made the Vite dev server listen on `0.0.0.0` so the frontend can be opened from other devices on the LAN.
- Added local and LAN URL output to the unified `pnpm dev` launcher.
- Allowed private-network Vite origins in backend CORS for direct LAN API usage.

## 0.3.2 - 2026-07-31

- Increased GIF quality presets to 128-256 colors and up to 1920 px at level 5.
- Removed image and video error-diffusion dithering that caused visible texture and crust-like artifacts.
- Added quality-scaled K-Means palette refinement for image conversion.
- Added one-click ZIP download for all completed GIF results.
- Added FFprobe validation and a hard 30-second maximum for video jobs.
- Expanded backend regression coverage from five to nine tests.

## 0.3.1 - 2026-07-31

- Reworked the interface into a flat, single-surface media editor with no gradients and fewer dividers.
- Replaced stacked mobile sections with a compact viewport workbench and a shared asset/result stage.
- Added dedicated small-phone and landscape layouts that keep the primary generation flow on screen.
- Improved touch targets, focus states, safe-area spacing, status labels, and reduced-motion support.

## 0.3.0 - 2026-07-31

- Replaced metadata-only queue submission with real multipart media uploads.
- Added Pillow-based single-image and multi-image GIF generation.
- Added FFmpeg-based video-to-GIF generation with five quality presets.
- Added completed and failed job states, persisted result files, and a GIF result endpoint.
- Added GIF previews, Chinese status labels, failure details, and downloads to the responsive frontend.
- Added backend generation regression tests and restored `WEB_MEDIA_GENERATION.md`.

## 0.2.5 - 2026-07-31

- Reworked the workspace into a flatter, cleaner UI without large gradients or heavy borders.
- Improved the mobile layout with horizontally scrollable mode selection and a shared preview/queue stage.
- Kept key actions, summaries, and status visible in a tighter first-screen composition on smaller devices.

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
