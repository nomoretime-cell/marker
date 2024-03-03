import gradio as gr

from marker.service.routers.parser import process
from marker.service.struct.parser_struct import ParserRequest


def process_pdf(file_path):
    full_text, out_meta = process(
        file_path,
        ParserRequest(
            requestId="gradio-test",
            inFileUrl="",
            outFileUrl="",
        ),
    )
    return full_text


iface = gr.Interface(
    fn=process_pdf,
    inputs=gr.File(label="Upload Document"),
    outputs="markdown",
    title="DocParser 文档解析器",
    description="上传文档",
)


iface.launch(server_name="30.220.144.140", share=True)