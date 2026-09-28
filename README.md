# Campus Customs (HW4)

An online store for Yale apparel with an AI shopping assistant.

- **Frontend:** React + Vite + TypeScript (`frontend/`)
- **Backend:** FastAPI + SQLite (`backend/`)
- **AI:** PydanticAI agents on `gpt-5.6-luna` through Portkey

Shoppers can search, sort and page through 102 products, see stock by size, create an account, fill a cart and place orders. They can also chat with an assistant that looks up real products and stock, and follow live Yale Athletics scores. See [`output/harness.md`](output/harness.md) for how everything works, the safety rules and the spec limits.

## Project layout

```
hw4/
├── AI_prompts.md          every prompt used to build this, by homework question
├── requirements.txt       Python packages for the backend
├── .env.example           template for your .env (copy it, then add your key)
├── .gitignore
├── README.md
├── frontend/              Vite React TypeScript app
├── backend/
│   ├── main.py            FastAPI app: routes, accounts, carts and orders, chat history, scores
│   ├── agent.py           the AI agents, time and usage limits, and the audit trail
│   ├── models.py          every data shape, plus the spec limits
│   ├── tools.py           the agent's tools and read-only catalogue access
│   ├── prompts/
│   │   └── prompt.md      system prompt (plus the two helper agents' instructions)
│   └── check_guardrails.py  optional: tests every guardrail and spec limit
└── output/
    ├── harness.md         how everything works
    ├── design.md
    ├── usability.md
    ├── app_check.html     testing screenshots (open it in a browser)
    ├── app_check_images/
    └── audit_trail.json   append-only log of agent runs
```

**The agent is four files:** `backend/prompts/prompt.md`, `backend/agent.py`, `backend/tools.py` and `backend/models.py`. `main.py` is the web server around it.

## What's not in this repo

The data pack and your API key stay on your computer and are blocked by `.gitignore`:

```
data/
├── campus_customs.db     the product, inventory and user database
└── products/             the product images the catalogue points to
```

## Setup

You need **Python 3.12+** and **Node.js 20+**.

### 1. Place the data pack

Put the `data` folder from the class data pack inside `hw4/`, next to `backend/` and `frontend/`:

```
hw4/data/campus_customs.db
hw4/data/products/*.jpg
```

### 2. Add your API key

Copy `.env.example` to `.env` in the `hw4/` folder, then open `.env` and replace `your-portkey-api-key-here` with your Portkey key.

- Windows (PowerShell): `Copy-Item .env.example .env`
- Mac/Linux: `cp .env.example .env`

### 3. Install the backend

From the `hw4/backend` folder:

**Windows (PowerShell)**
```
cd backend
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r ..\requirements.txt
```

**Mac/Linux**
```
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
```

### 4. Install the frontend

In a second terminal, from the `hw4/frontend` folder:
```
cd frontend
npm install
```

## Running it

You need two terminals, one for each server.

**Terminal 1: backend** (from `hw4/backend`, with the virtual environment active)
```
uvicorn main:app --reload --port 8000
```
Leave it running. The API docs are at http://127.0.0.1:8000/docs.

**Terminal 2: frontend** (from `hw4/frontend`)
```
npm run dev
```

Then open **http://localhost:5173** in your browser. The frontend forwards `/api` and `/media` requests to the backend on port 8000, so both need to be running.

**Test account:** `test@campuscustoms.yale.edu` / `password` (from the class data pack), or create your own on the Create Account page.

## Checking the guardrails (optional)

From `hw4/backend`, with the virtual environment active:
```
python check_guardrails.py
```
It runs 44 checks in about 5 seconds, covering the spec limits, stock and cart rules, account security, chat limits, the 3-minute time limit and the audit trail. It uses a temporary copy of the database, so your real data isn't touched and no AI calls are made. Add `--live` to also run two real chats.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not load products. Is the backend running?" | Start the backend (Terminal 1) and check the data pack is in `hw4/data/`. |
| Product images are missing | The images belong in `hw4/data/products/`. |
| The chat says "something went wrong" | Check `.env` exists in `hw4/` and has a real `PORTKEY_API_KEY`. |
| `uvicorn` isn't found | Activate the virtual environment first (step 3), or run `.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000`. |
| PowerShell won't run `activate` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use the `.venv\Scripts\python.exe -m uvicorn ...` command above. |
| Port 8000 or 5173 is busy | Close the other program using it, or change the port (the frontend expects the backend on 8000). |
