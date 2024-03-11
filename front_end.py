import gradio as gr

from marker.service.routers.parser import inner_process
from marker.service.struct.parser_struct import ParserRequest


def process_pdf(file_path):
    full_text, out_meta = inner_process(
        file_path,
        ParserRequest(
            requestId="gradio-test",
            inFileUrl="",
            outFileUrl="",
        ),
    )
    return full_text


def main():
    iface = gr.Interface(
        fn=process_pdf,
        inputs=gr.File(label="Upload Document"),
        outputs="markdown",
        title="DocParser 文档解析器",
        description="上传文档",
    )

    iface.launch(ssl_verify=False, server_name="0.0.0.0", server_port=8100, share=True)


if __name__ == "__main__":
    main()
