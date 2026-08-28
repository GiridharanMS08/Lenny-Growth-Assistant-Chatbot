# PostgreSQL Configuration

The submitted workflow uses PostgreSQL for persistent sessions and messages.

## Password changes

For the take-home/local workflow, edit `intern/.env.example` when no `.env` file exists:

```text
DATABASE_URL=postgresql+psycopg://postgres:NEW_PASSWORD@localhost:5432/lenny
```

Restart `start.bat` or the backend after changing the file. The settings loader reads `.env` first and falls back to `.env.example`, so the password is not hard-coded in `config.py`.

For a normal development environment, create `intern/.env` from the example. That real `.env` takes precedence over both example files and should not be committed.

## Manual backend start

```bat
cd backend
..\\.venv\\Scripts\\activate
uvicorn app.main:app --reload
```

The `--reload` flag is retained for local development. It restarts the FastAPI process when Python source files change; it is not intended for production deployment.

## Database check

Before the backend starts, `start.bat` runs `SELECT 1` against the configured PostgreSQL database. The API also exposes database status through `GET /health`.
