# CodeShift

CodeShift is a small full-stack code conversion prototype.

- Frontend: Next.js app for entering code, choosing source and target languages, and testing provider settings
- Backend: FastAPI service with a lightweight rule-based converter and an OpenAI-compatible fallback

## Repository Layout

```text
codeshift-frontend/   Next.js UI
codeshift-backend/    FastAPI API
```

## Current Capabilities

- Detects `python`, `cpp`, `java`, and `javascript` from filenames
- Applies lightweight rule-based conversion for:
  - simple string variables
  - direct print/log statements
  - basic `greet(...)` examples
  - simple string concatenation
- Falls back to an OpenAI-compatible Responses API call when no lightweight rule matches
- Keeps provider API keys in memory for the current browser session instead of persisting them to local storage

## Local Development

### Backend

```bash
cd codeshift-backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Environment variables:

- `OPENAI_API_KEY`: required for AI fallback
- `OPENAI_BASE_URL`: optional OpenAI-compatible base URL
- `OPENAI_MODEL`: optional model override, defaults to `gpt-5.4-mini`
- `CODESHIFT_ALLOWED_ORIGINS`: optional comma-separated frontend origins for CORS

### Frontend

```bash
cd codeshift-frontend
npm install
npm run dev
```

Optional environment variables:

- `NEXT_PUBLIC_API_URL`: backend base URL, defaults to `http://127.0.0.1:8000`

## Deployment Notes

- Frontend preview deployments are currently handled by Vercel
- The current live demo is [code-shift-sigma.vercel.app](https://code-shift-sigma.vercel.app)
- For deployed environments, set `CODESHIFT_ALLOWED_ORIGINS` to include every frontend origin that should call the backend

## Validation

```bash
cd codeshift-frontend && npm run lint
cd codeshift-frontend && npm run build
python3 -m py_compile codeshift-backend/main.py
cd codeshift-backend && python3 -m unittest -v
```

## Known Gaps

- No CI workflow yet
- Rule-based conversion still covers only lightweight code patterns
- Anything outside the supported lightweight patterns relies on AI fallback
