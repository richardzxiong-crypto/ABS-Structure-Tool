from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import deals, meta, runs

app = FastAPI(title="ABS Structuring Tool", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(deals.router)
app.include_router(runs.router)
app.include_router(meta.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
