from typing import Optional
from pydantic import BaseModel


class ParserRequest(BaseModel):
    requestId: str
    inFileUrl: str
    outFileUrl: str
    maxPages: Optional[int] = None
    parallelFactor: Optional[int] = 1
    isDebug: Optional[bool] = False


class ParserResponse:
    def __init__(self, requestId: str, code: str, message: str) -> None:
        self.requestId: str = requestId
        self.code: str = code
        self.message: str = message

    def to_dict(self) -> dict:
        obj_dict = {
            "requestId": self.requestId,
            "code": self.code,
            "message": self.message,
        }

        return obj_dict
