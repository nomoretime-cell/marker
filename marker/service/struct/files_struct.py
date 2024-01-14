from typing import Optional
from pydantic import BaseModel


class ParserRequest(BaseModel):
    requestId: str
    inFileUrl: str
    outFileUrl: str
    fileType: Optional[str] = "pdf"
    maxPages: Optional[int] = None
    parallelFactor: Optional[int] = 1
    isDebug: Optional[bool] = False
