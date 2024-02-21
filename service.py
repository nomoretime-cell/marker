import uvicorn
from fastapi import FastAPI
from marker.logger import configure_logging
from marker.service.routers.parser import router
from marker.service.routers.health_check import health_check_router
from marker.settings import settings

configure_logging()

app: FastAPI = FastAPI()
app.include_router(router, prefix="/api")
app.include_router(health_check_router)

if __name__ == "__main__":
    uvicorn.run(
        "service:app",
        host="0.0.0.0",
        port=8000,
        workers=settings.WORKER_NUM,
    )
