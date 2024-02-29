import datetime
from fastapi import APIRouter


health_check_router = APIRouter()


@health_check_router.get("/health", tags=["health check"])
async def health() -> dict:
    time_string = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "ok", "code": 200, "timestamp": time_string}


@health_check_router.get("/ready", tags=["health check"])
async def ready() -> dict:
    time_string = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "ok", "code": 200, "timestamp": time_string}
