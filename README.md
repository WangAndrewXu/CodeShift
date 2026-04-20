# CodeShift

CodeShift is a small full-stack code conversion prototype.

- Frontend: Next.js app for entering code, choosing source and target languages, and testing provider settings
- Backend: FastAPI service with a narrow rule-based converter and an OpenAI-compatible fallback

## Repository Layout

```text
codeshift-frontend/   Next.js UI
codeshift-backend/    FastAPI API
```

## Current Capabilities

- Detects `python`, `cpp`, `java`, and `javascript` from filenames
- Applies a limited rule-based conversion path for simple `greet(...)` examples
- Falls back to an OpenAI-compatible Responses API call when no rule matches
- Lets users store provider settings in browser local storage

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

## Known Gaps

- No automated tests yet
- No CI workflow yet
- Rule-based conversion only handles a very narrow example shape
- Provider credentials are stored in browser local storage, which is convenient but weak for shared machines
