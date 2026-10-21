# AI Internship Agent

当前工具层使用 Python 3.12、Pydantic 2、pytest，不调用 LLM 或网络服务。

## 工具接口

- `read_resume(file_path, *, allowed_directory=...) -> str`：UTF-8 TXT/Markdown。
  保留原有单参数用法，默认仅允许项目 `examples/`；相对路径仍相对于当前工作目录。
  支持配置一个允许目录，解析 `..` 和符号链接后检查真实路径归属，并检查真实文件扩展名。
- `parse_job(jd_text) -> JobPosting`：提取 `Title/职位`、`Company/公司` 等标签，
  无职位标签时取首个非公司非空行；保留完整原始 JD。
  通过 `src/tools.py` 的固定技能词表、别名和 `Required/任职要求`、
  `Preferred/加分项` 等行首标签区分技能。无分区的命中默认为必备；同一技能必备优先。
  技能顺序按原文行序、同行词表序排列，不重复。
- `find_evidence(resume_text, skills) -> list[SkillEvidence]`：逐关键词返回原文匹配行，
  保留行内空格（不包含换行符）；无证据时 `found=False, evidence=[]`。
  关键词不区分大小写，按字面匹配，不做别名扩展；ASCII 关键词要求单词边界，
  避免 `SQL` 匹配 `MySQL`，同时支持中文紧邻英文技能。

## 注册与执行

```python
from src.tool_registry import create_tool_registry

registry = create_tool_registry()  # 也可由应用代码指定 allowed_directory
result = registry.execute("read_resume", {"file_path": "examples/resume.txt"})
print(result.model_dump_json())
```

`ToolRegistry()` 初始为空；只有显式 `register(name, arguments_model, handler)` 的工具可执行。
标准工厂显式注册上述三个工具。允许目录由应用配置，工具参数无法覆盖。
Pydantic 严格拒绝参数类型错误、额外字段、缺失字段及空白关键词。
执行结果统一为 `tool_name/success/data/error`，成功数据可 JSON 序列化，
错误包含稳定 `code` 和说明，参数验证错误不回显输入值。
直接调用工具函数时仍抛出 Python/Pydantic 异常，执行器负责转为统一结果。

## 离线测试

在已安装 Pydantic 2 和 pytest 的 Python 3.12 环境运行：

```sh
.venv/bin/python -m pytest
```

`pytest.ini` 默认只收集 `tests/`。根目录历史 `test_direct.py` 和 `test_gemini.py`
在导入时会加载环境密钥并发起真实 API 请求，因此不纳入默认测试；不要显式运行它们。

## 设计限制

JD 提取是可测试的文本规则，词表外技能、否定、熟练度、隐含要求和复杂格式不作语义判断。
证据只是原文提及，不代表技能得到验证，例如“未使用 Python”仍会匹配。
文件工具只处理可信本地应用配置下的普通文本；路径检查和读取之间未实现操作系统级原子锁定，
不用于存在并发恶意符号链接替换的多租户文件系统。暂无文件大小限制或 PDF/DOCX 支持。
本阶段不包含 Agent Loop、真实 LLM、前端或数据库。
