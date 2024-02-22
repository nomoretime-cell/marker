from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    requestId: str
    inFileUrl: str


class AnalyzeResult:
    def __init__(self) -> None:
        self.fileType: str
        self.contentType: str
        self.language: str
        self.columnNum: int
        self.pageNum: int
        # self.contentQuality: int

    def to_dict(self) -> dict:
        obj_dict = {
            "fileType": self.fileType,
            "contentType": self.contentType,
            "language": self.language,
            "columnNum": self.columnNum,
            "pageNum": self.pageNum,
            # "contentQuality": self.contentQuality,
        }
        return obj_dict


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
            "data": self.data.to_dict(),
        }
        return obj_dict
