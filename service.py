import uvicorn
from fastapi import FastAPI
from marker.service.routers.parser import router
from marker.settings import settings

app: FastAPI = FastAPI()
app.include_router(router, prefix="/api")

if __name__ == "__main__":
    concurrency: int = 100
    print(f"server limit_concurrency: {concurrency}")
    uvicorn.run(
        "service:app",
        host="0.0.0.0",
        port=8000,
        limit_concurrency=concurrency,
        workers=settings.WORKER_NUM,
    )
