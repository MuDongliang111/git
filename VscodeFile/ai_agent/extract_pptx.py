"""临时脚本：提取 你好.pptx 的内容"""
import sys
sys.path.insert(0, "src")

# 直接调用 pptx_reader skill 中的函数
from skills.pptx_reader.tools import _read_pptx

result = _read_pptx("你好.pptx", include_notes=True)
print(result)
