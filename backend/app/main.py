from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
from app.db import get_engine
from app.errors import register_handlers

app = FastAPI(title="Relay reporting API")
register_handlers(app)
app.include_router(router)


@app.get("/api/health")
def health(engine: Annotated[Engine, Depends(get_engine)]) -> JSONResponse:
    """200 when the process is up and the database answers SELECT 1, otherwise 503."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse({"status": "error", "db": "unavailable"}, status_code=503)
    return JSONResponse({"status": "ok", "db": "ok"})
