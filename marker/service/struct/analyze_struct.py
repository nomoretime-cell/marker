from typing import Optional
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    requestId: str
    inFileUrl: str


class AnalyzeResult(BaseModel):
    fileType: Optional[str] = None
    contentType: Optional[str] = None
    language: Optional[str] = None
    columnNum: Optional[int] = None
    pageNum: Optional[int] = None
    contentQuality: Optional[int] = None


class AnalyzeResponse:
    def __init__(
        self, requestId: str, code: str, message: str, data: AnalyzeResult
    ) -> None:
        self.requestId: str = requestId
        self.code: str = code
        self.message: str = message
        self.data: AnalyzeResult = data

    def to_dict(self) -> dict:
        obj_dict = {
            "requestId": self.requestId,
            "code": self.code,
            "message": self.message,
            "data": self.data.model_dump(),
        }
        return obj_dict

    def to_jsonl(self, append_info: dict = {}) -> dict:
        obj_dict = {**append_info, **self.data.model_dump()}
        return obj_dict

    @staticmethod
    def from_dict(data: dict) -> "AnalyzeResponse":
        return AnalyzeResponse(
            data["requestId"],
            data["code"],
            data["message"],
            AnalyzeResult(**data["data"]),
        )
