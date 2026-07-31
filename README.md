# WottyGIF

WottyGIF is being rebuilt as a Python backend plus Vue frontend app.

## Stack

- Backend: FastAPI
- Frontend: Vue 3 + Vite

## Development

Start backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Start frontend from the workspace root:

```powershell
cd F:\1python\xiangmu
pnpm --filter wottygif-frontend dev
```

## Version

Current version: `0.1.0`
