from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import admin, auth, customer
from app.core.database import engine, redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(title="Douyin Comment Platform API", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(customer.router)
app.include_router(admin.router)


@app.get("/healthz", tags=["system"])
async def healthz():
    return {"status": "ok"}
