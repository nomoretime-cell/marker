import logging
import threading
import time
import json

from fastapi import APIRouter
from marker.convert import convert_single_pdf
from marker.models import load_all_models
from marker.service.func.parser_func import (
    delete_file,
    download_file,
    download_presigned_file,
    upload_file,
    upload_presigned_file,
)
from marker.service.struct.parser_struct import ParserRequest, ParserResponse

router = APIRouter()
model_lst = load_all_models()


@router.post("/parser/", tags=["pdf parser"])
async def post_parser(parser_request: ParserRequest) -> dict:
    download_file(
        parser_request.inFileUrl,
        parser_request.inFileUrl,
    )

    start_time: float = time.time()
    full_text, out_meta = convert_single_pdf(
        parser_request.inFileUrl,
        model_lst,
        max_pages=parser_request.maxPages,
        parallel_factor=parser_request.parallelFactor,
        debug_mode=parser_request.isDebug,
    )
    execution_time: float = time.time() - start_time
    logging.info(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )

    with open(parser_request.outFileUrl, "w+", encoding="utf-8") as f:
        f.write(full_text)

    out_meta_filename = parser_request.outFileUrl.rsplit(".", 1)[0] + "_meta.json"
    with open(out_meta_filename, "w+") as f:
        f.write(json.dumps(out_meta, indent=4))

    upload_file(parser_request.outFileUrl, parser_request.outFileUrl)
    if not parser_request.isDebug:
        delete_file(out_meta_filename)
        delete_file(parser_request.inFileUrl)
        delete_file(parser_request.outFileUrl)
    return ParserResponse(parser_request.requestId, "200", "success").to_dict()


@router.post("/v1/parser/", tags=["pdf parser"])
async def post_v1_parser(parser_request: ParserRequest) -> dict:
    logging.info(f"POST request, thread id: {threading.current_thread().ident}")
    local_original_file: str = parser_request.requestId + "." + parser_request.fileType
    local_result_file: str = parser_request.requestId + ".md"
    download_presigned_file(
        parser_request.inFileUrl,
        local_original_file,
    )

    start_time: float = time.time()
    full_text, out_meta = convert_single_pdf(
        local_original_file,
        model_lst,
        max_pages=parser_request.maxPages,
        parallel_factor=parser_request.parallelFactor,
        debug_mode=parser_request.isDebug,
    )
    execution_time: float = time.time() - start_time
    logging.info(
        f"Function '{convert_single_pdf.__name__}' took {execution_time} seconds to execute."
    )

    if not parser_request.isDebug:
        # PROD
        delete_file(local_original_file)
        upload_presigned_file(parser_request.outFileUrl, local_result_file, full_text)
    else:
        # DEBUG
        with open(local_result_file, "w+", encoding="utf-8") as f:
            f.write(full_text)
        upload_presigned_file(parser_request.outFileUrl, local_result_file)

    return ParserResponse(parser_request.requestId, "200", "success").to_dict()
