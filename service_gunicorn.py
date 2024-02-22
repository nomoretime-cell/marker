from fastapi import FastAPI
from marker.logger import configure_logging
from marker.service.routers.parser import parser_router
from marker.service.routers.analyze import analyze_router
from marker.service.routers.health_check import health_check_router
from marker.settings import settings
from gunicorn.app.base import BaseApplication
from uvicorn.workers import UvicornWorker

configure_logging()

app: FastAPI = FastAPI()
app.include_router(parser_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(health_check_router)

# https://docs.gunicorn.org/en/stable/index.html
class GunicornApplication(BaseApplication):
    def __init__(self, app: FastAPI, options: dict = None):
        self.options: dict = options or {}
        self.application: FastAPI = app
        super().__init__()

    def load_config(self):
        config: dict = {
            key: value
            for key, value in self.options.items()
            if key in self.cfg.settings and value is not None
        }
        for key, value in config.items():
            self.cfg.set(key.lower(), value)

    def load(self) -> FastAPI:
        return self.application


if __name__ == "__main__":
    options: dict = {
        "bind": "0.0.0.0:8000",
        "workers": settings.WORKER_NUM,
        "worker_class": "uvicorn.workers.UvicornWorker",
    }
    GunicornApplication(app, options).run()
