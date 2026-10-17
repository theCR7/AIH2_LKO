# Prerequisites Checklist — complete the DAY BEFORE

Tick every box. Most hackathon time is lost to installs, proxies and API keys, not code.

## 1. Accounts & keys (free, no credit card)

| # | Item | Where | Owner | Done |
|---|---|---|---|---|
| 1 | GitHub repo `ringsight` (private until demo), add 2 teammates as collaborators | github.com | Member A | ☐ |
| 2 | **Google AI Studio API key** (primary LLM — Gemini Flash family, free tier) | aistudio.google.com → Get API key | Member B | ☐ |
| 3 | **Groq API key** (backup LLM — e.g. `openai/gpt-oss-120b`, free tier) | console.groq.com | Member B | ☐ |
| 4 | Claude Code access (Pro/Max plan or API key) for **each** member who will drive it | claude.ai / console.anthropic.com | All | ☐ |
| 5 | Kaggle account (optional — IBM AML dataset for stretch goal / M.Tech) | kaggle.com | Member A | ☐ |
| 6 | Streamlit Community Cloud account linked to GitHub (optional public demo URL) | share.streamlit.io | Member C | ☐ |

> **Rate-limit reality:** free tiers cap requests per minute and per day, and Groq's free tier is tight on *tokens per minute* (~8K). The design therefore sends **compact evidence summaries** to the LLM, never raw CSVs, and **caches every LLM response** in the DB so the live demo replays instantly.
> **Data policy:** free-tier providers may use prompts to improve their models. We use **100% synthetic data** — never paste HCLTech/client data.

## 2. Machine setup (each member)

Prefer a **personal laptop** for the hackathon — corporate VDI/proxy/SSL inspection (WSS agent) commonly breaks `pip`, `npm` and LLM API calls.

| # | Item | Verify command | Done |
|---|---|---|---|
| 1 | Python **3.11 or 3.12** | `python --version` | ☐ |
| 2 | Git + GitHub auth (SSH key or `gh auth login`) | `git --version` | ☐ |
| 3 | VS Code + Python extension | — | ☐ |
| 4 | Claude Code CLI installed and logged in | `claude --version` | ☐ |
| 5 | Create venv & install deps from `requirements.txt` | `pip install -r requirements.txt` | ☐ |
| 6 | Smoke-test both LLM keys (script below) | `python smoke_llm.py` | ☐ |
| 7 | (Optional) Ollama + small model as offline fallback | `ollama run qwen2.5:7b` | ☐ |
| 8 | (Optional) SQL Server Express/LocalDB + **ODBC Driver 18** if you want SQL Server instead of SQLite | `odbcinst -q -d` / ODBC Data Sources | ☐ |

If on corporate network anyway:
```bash
pip config set global.cert "C:\path\to\corp-root-ca.pem"
set HTTPS_PROXY=http://<proxy>:<port>
```

### `smoke_llm.py` (run once, then delete)
```python
from dotenv import load_dotenv; load_dotenv()
from litellm import completion
for m in ["gemini/gemini-2.5-flash", "groq/openai/gpt-oss-120b"]:
    try:
        r = completion(model=m, messages=[{"role": "user", "content": "Reply OK"}], max_tokens=5)
        print(m, "->", r.choices[0].message.content)
    except Exception as e:
        print(m, "FAILED:", e)
```
> Model names change often — confirm current free model IDs in AI Studio / Groq console and put them in `.env`.

## 3. Database decision

| Option | Use when | Connection string |
|---|---|---|
| **SQLite (default)** | Hackathon — zero install, file in repo `data/` | `sqlite:///data/ringsight.db` |
| SQL Server Express / LocalDB | You want corporate-like stack / M.Tech | `mssql+pyodbc://@localhost\SQLEXPRESS/RingSight?driver=ODBC+Driver+18+for+SQL+Server&trusted_connection=yes&TrustServerCertificate=yes` |
| PostgreSQL (Neon/Supabase free) | Public cloud deploy later | `postgresql+psycopg://...` |

All code goes through **SQLAlchemy**, so switching is a one-line `.env` change. **Decision: SQLite on hackathon day.**

## 4. Free resources

| Need | Free resource |
|---|---|
| LLM (primary) | Google AI Studio — Gemini Flash / Flash-Lite |
| LLM (backup) | Groq — gpt-oss / Qwen models |
| LLM (offline) | Ollama — Qwen 2.5 7B / Llama 3.x 8B |
| Synthetic data | Own generator (in repo) + IBM *Transactions for AML* (Kaggle, CDLA-Sharing-1.0) |
| Graph | NetworkX, pyvis |
| UI | Streamlit (+ Streamlit Community Cloud hosting) |
| PDF | ReportLab |
| Icons/fonts | Streamlit built-ins, Google Fonts (Inter) |
| Slides | PowerPoint / Google Slides |
| Domain reference | FinCEN SAR narrative guidance, FATF typologies (public PDFs) |

## 5. Pre-hackathon team tasks (≈ 2 hours total)
- ☐ Read BRD + PRD together (30 min), agree the 3 demo "wow moments".
- ☐ Member A: commit this pack, create branches `feat/data`, `feat/agents`, `feat/ui`.
- ☐ Member B: smoke-test keys, note exact model IDs into `.env.example`.
- ☐ Member C: create slide shell (5 slides) from `DEMO_SCRIPT.md`.
- ☐ Agree Claude Code etiquette: **one driver per branch**, commit after every prompt, never two people editing the same file.
