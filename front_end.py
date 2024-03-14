import os
import tempfile
import uuid
import gradio as gr
from docx import Document
from docx.shared import Pt
from docx.shared import RGBColor
from docx.oxml.ns import qn
from marker.service.routers.parser import inner_process
from marker.service.struct.parser_struct import ParserRequest


def process_pdf(file_path):
    file_name = os.path.basename(file_path)
    full_text, out_meta = inner_process(
        file_path,
        ParserRequest(
            requestId="gradio" + "_" + str(uuid.uuid4()),
            inFileUrl="",
            outFileUrl="",
        ),
    )
    return file_name, full_text


def export_to_docx(file_name, text):
    filename = file_name + ".docx"
    file_path = os.path.join(tempfile.gettempdir(), filename)

    doc = Document()
    paragraph = doc.add_paragraph(text)

    run = paragraph.runs[0]
    run.font.name = "微软雅黑"
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0, 0, 0)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "微软雅黑")

    doc.save(file_path)
    return file_path


def export_to_markdown(file_name, text):
    filename = file_name + ".md"
    file_path = os.path.join(tempfile.gettempdir(), filename)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)
    return file_path


def main():
    with gr.Blocks(
        title="DocParser 文档解析器",
        css="""
            .upload-file-box {
                height: 190px;
            }
            .file-box {
                height: 80px;
            }
        """,
    ) as front_end:
        file_name = gr.State(str(""))
        gr.Markdown("## DocParser 文档解析器")
        with gr.Row():
            upload_file = gr.File(label="上传文档", elem_classes="upload-file-box")
            parse_btn = gr.Button("解析")

        output_textbox = gr.Textbox(
            label="解析结果",
            lines=10,
            placeholder="解析完成后，结果会在此展示",
        )

        with gr.Row():
            export_docx_btn = gr.Button("导出 DOCX")
            download_docx_file = gr.File(label="下载 DOCX", elem_classes="file-box")
            export_md_btn = gr.Button("导出 Markdown")
            download_md_file = gr.File(label="下载 Markdown", elem_classes="file-box")

        parse_btn.click(
            process_pdf,
            inputs=upload_file,
            outputs=[file_name, output_textbox],
        )
        export_docx_btn.click(
            export_to_docx,
            inputs=[file_name, output_textbox],
            outputs=download_docx_file,
        )
        export_md_btn.click(
            export_to_markdown,
            inputs=[file_name, output_textbox],
            outputs=download_md_file,
        )
    front_end.launch(
        # ssl_verify=False, server_name="30.220.144.140", server_port=8100, share=True
        ssl_verify=False, server_name="0.0.0.0", server_port=8100, share=True
    )


if __name__ == "__main__":
    main()
