import asyncio
import logging
import os
import threading
import time
import uuid
import aiofiles

from fastapi import APIRouter, File, HTTPException, UploadFile
from marker.convert import convert_single_pdf
from marker.models import load_all_models
from marker.service.func.common_func import (
    delete_file,
    download_file,
    download_presigned_file,
    save_file,
    upload_file,
    upload_presigned_file,
)
from marker.service.struct.parser_struct import ParserRequest, ParserResponse

parser_router = APIRouter()
model_lst = load_all_models()
is_request_processing = False
is_request_processing_lock = threading.Lock()


@parser_router.post("/internal/parser", tags=["doc parser"])
async def post_parser(parser_request: ParserRequest) -> dict:
    logging.info(f"POST request, thread id: {threading.current_thread().ident}")
    loop = asyncio.get_running_loop()

    # 1. download file
    await loop.run_in_executor(
        None, download_file, parser_request.inFileUrl, parser_request.inFileUrl
    )

    # 2. inner_process
    full_text, out_meta = inner_process(parser_request.inFileUrl, parser_request)

    # 3. save file
    await loop.run_in_executor(None, save_file, parser_request.outFileUrl, full_text)

    # 4. upload markdown file
    await loop.run_in_executor(
        None, upload_file, parser_request.outFileUrl, parser_request.outFileUrl
    )
    if not parser_request.isDebug:
        await loop.run_in_executor(None, delete_file, parser_request.inFileUrl)
        await loop.run_in_executor(None, delete_file, parser_request.outFileUrl)

    return ParserResponse(parser_request.requestId, "200", "success").to_dict()


@parser_router.post("/v1/parser", tags=["doc parser"])
async def post_v1_parser(parser_request: ParserRequest) -> dict:
    return await process(parser_request)


@parser_router.post("/v1/parser/file", tags=["doc parser"])
async def post_v1_parser_file(file: UploadFile = File(...)) -> dict:
    parser_request: ParserRequest = ParserRequest(
        requestId=str(uuid.uuid4()),
        formDataFile=file,
    )
    return await process(parser_request)


def inner_process(file_path: str, parser_request: ParserRequest) -> tuple[str, dict]:
    start_time: float = time.time()
    full_text, out_meta = convert_single_pdf(
        file_path,
        model_lst,
        max_pages=parser_request.maxPages,
        parallel_factor=parser_request.parallelFactor,
        debug_mode=parser_request.isDebug,
    )
    execution_time: float = time.time() - start_time
    logging.info(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )
    return full_text, out_meta


async def process(parser_request: ParserRequest):
    global is_request_processing
    with is_request_processing_lock:
        if is_request_processing:
            # raise HTTPException(status_code=503, detail="service is busy")
            return ParserResponse(
                parser_request.requestId, "503", "service is busy"
            ).to_dict()
        else:
            is_request_processing = True
    full_text = ""
    try:
        logging.info(
            f"POST request, pid: {os.getpid()}, thread id: {threading.current_thread().ident}"
        )
        loop = asyncio.get_running_loop()

        # 1. prepare file path
        local_original_file: str = parser_request.requestId

        # 2. download file
        if parser_request.formDataFile:
            async with aiofiles.open(local_original_file, "wb") as out_file:
                content = await parser_request.formDataFile.read()
                await out_file.write(content)
        else:
            download_presigned_file(parser_request.inFileUrl, local_original_file)

        # 3. inner_process
        full_text, out_meta = await loop.run_in_executor(
            None, inner_process, local_original_file, parser_request
        )

        # 4. upload markdown file
        if parser_request.isDebug:
            # save markdown file
            local_result_file: str = parser_request.requestId + ".md"
            save_file(local_result_file, full_text)
        else:
            # delete pdf file
            delete_file(local_original_file)

        if not parser_request.formDataFile:
            upload_presigned_file(
                parser_request.outFileUrl,
                "",
                full_text,
            )

    except HTTPException as http_e:
        raise http_e
    except Exception as e:
        return ParserResponse(parser_request.requestId, "500", e).to_dict()
    finally:
        with is_request_processing_lock:
            is_request_processing = False
        return ParserResponse(
            parser_request.requestId, "200", "success", data={"text": full_text}
        ).to_dict()
