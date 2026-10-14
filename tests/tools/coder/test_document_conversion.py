"""Exercise binary document reads with the installed conversion dependencies."""

from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from siada.tools.coder.siada_editor import SiadaEditor


@pytest.fixture
def docx_path(tmp_path: Path) -> Path:
    """Build a small Word package containing Chinese text, links and an image."""
    path = tmp_path / "交底书.docx"
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/></Relationships>',
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="link" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
            'Target="https://example.com/reference" TargetMode="External"/>'
            '<Relationship Id="image" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
            'Target="media/image.png"/></Relationships>',
        )
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            "<w:body>"
            '<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
            "<w:r><w:t>交底书</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>中文正文</w:t></w:r></w:p>"
            '<w:p><w:hyperlink r:id="link"><w:r><w:t>参考链接</w:t></w:r></w:hyperlink></w:p>'
            "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>模块</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>说明</w:t></w:r></w:p></w:tc></w:tr>"
            "<w:tr><w:tc><w:p><w:r><w:t>地图</w:t></w:r></w:p></w:tc>"
            "<w:tc><w:p><w:r><w:t>路线规划</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
            "<w:p><w:r><w:drawing><wp:inline>"
            '<wp:docPr id="1" name="figure" descr="示意图"/>'
            "<a:graphic><a:graphicData><pic:pic><pic:blipFill>"
            '<a:blip r:embed="image"/>'
            "</pic:blipFill></pic:pic></a:graphicData></a:graphic>"
            "</wp:inline></w:drawing></w:r></w:p>"
            "</w:body></w:document>",
        )
        # Conversion only embeds the bytes; no image decoder is involved.
        archive.writestr("word/media/image.png", b"\x89PNG\r\n\x1a\nsynthetic-image")
    return path


def test_view_docx_preserves_text_links_tables_and_images(docx_path: Path):
    output = SiadaEditor().view(docx_path).output

    assert "# 交底书" in output
    assert "中文正文" in output
    assert "[参考链接](https://example.com/reference)" in output
    assert "| 模块 | 说明 |" in output
    assert "| 地图 | 路线规划 |" in output
    assert "![示意图](data:image/png;base64...)" in output
    assert "c3ludGhldGlj" not in output


@pytest.mark.asyncio
async def test_read_file_docx_uses_document_conversion(docx_path: Path):
    import json

    from agents.tool_context import ToolContext

    from siada.tools.coder.native_file_tools import read_file

    arguments = json.dumps({"path": docx_path.name, "view_range": None})
    context = ToolContext(
        SimpleNamespace(root_dir=str(docx_path.parent), siadaignore_controller=None),
        tool_name="read_file",
        tool_call_id="docx-read-regression",
        tool_arguments=arguments,
    )

    result = await read_file.on_invoke_tool(context, arguments)

    assert "中文正文" in result.content
    assert "[参考链接](https://example.com/reference)" in result.content
    assert "![示意图](data:image/png;base64...)" in result.content


def test_view_xlsx_preserves_tables(tmp_path: Path):
    from openpyxl import Workbook

    path = tmp_path / "references.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["模块", "参考链接"])
    sheet.append(["地图", "https://example.com/reference"])
    workbook.save(path)
    workbook.close()

    output = SiadaEditor().view(path).output

    assert "地图" in output
    assert "| 地图 | https://example.com/reference |" in output