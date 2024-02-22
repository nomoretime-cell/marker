import asyncio
import logging
import threading
import time

from fastapi import APIRouter
from marker.convert import analyze_single_pdf
from marker.models import load_all_models
from marker.service.func.common_func import (
    delete_file,
    download_presigned_file,
)
from marker.service.struct.analyze_struct import (
    AnalyzeRequest,
    AnalyzeResponse,
    AnalyzeResult,
)

analyze_router = APIRouter()
model_lst = load_all_models()


@analyze_router.post("/v1/analyze/", tags=["doc analyze"])
async def post_analyze(request: AnalyzeRequest) -> dict:
    logging.info(f"POST request, thread id: {threading.current_thread().ident}")
    loop = asyncio.get_running_loop()

    # 1. prepare file path
    local_original_file: str = request.requestId

    # 2. download file
    await loop.run_in_executor(
        None, download_presigned_file, request.inFileUrl, local_original_file
    )

    # 3. process
    analyze_result: AnalyzeResult = process(local_original_file)

    # 4. delete file
    await loop.run_in_executor(None, delete_file, local_original_file)

    return AnalyzeResponse(
        request.requestId, "200", "success", analyze_result
    ).to_dict()


def process(file_path: str) -> AnalyzeResult:
    start_time: float = time.time()
    analyze_result = analyze_single_pdf(
        file_path,
        model_lst,
    )
    execution_time: float = time.time() - start_time
    logging.info(
        f"Function '{analyze_single_pdf.__name__}' took {execution_time} seconds to execute."
    )
    return analyze_result
