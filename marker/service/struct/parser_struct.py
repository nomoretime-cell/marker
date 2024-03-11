from typing import Optional
from fastapi import UploadFile
from pydantic import BaseModel


class ParserRequest(BaseModel):
    requestId: str
    inFileUrl: str = None
    outFileUrl: str = None
    formDataFile: UploadFile = None
    maxPages: Optional[int] = None
    parallelFactor: Optional[int] = 1
    isDebug: Optional[bool] = False


class ParserResponse:
    def __init__(
        self, requestId: str, code: str, message: str, data: dict = None
    ) -> None:
        self.requestId: str = requestId
        self.code: str = code
        self.message: str = message
        self.data: dict = data

    def to_dict(self) -> dict:
        obj_dict = {
            "requestId": self.requestId,
            "code": self.code,
            "message": self.message,
            "data": self.data,
        }

        return obj_dict
