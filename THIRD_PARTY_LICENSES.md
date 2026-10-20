# 第三方依赖许可证

核实日期：2026-10-20。来源：各包 PyPI JSON 元数据（`https://pypi.org/pypi/<包名>/json`）。

| 依赖 | 用途 | 版本（核实时最新） | 许可证 | 备注 |
|---|---|---|---|---|
| [pydantic](https://pypi.org/project/pydantic/) | 数据模型 | 2.14.1 | MIT | |
| [typer](https://pypi.org/project/typer/) | CLI | 0.27.3 | MIT | |
| [rich](https://pypi.org/project/rich/) | 终端输出 | 15.0.0 | MIT | |
| [Jinja2](https://pypi.org/project/Jinja2/) | 报告模板 | 3.1.6 | BSD（分类器 `OSI Approved :: BSD License`） | 元数据未标明具体条款，未核实是 BSD-3-Clause |
| [scikit-learn](https://pypi.org/project/scikit-learn/) | TF-IDF 相似度 | 1.9.1 | BSD-3-Clause | |
| [Streamlit](https://pypi.org/project/streamlit/)（可选） | Web 界面 | 1.66.0 | Apache-2.0 | |
| [pytest](https://pypi.org/project/pytest/)（开发） | 测试 | 9.1.1 | MIT | |

| [memwall](https://pypi.org/project/memwall/)（可选，不随本项目分发） | 扫描记忆，本项目仅导入其 JSON 报告 | 0.6.1 | MIT（PyPI 元数据与 GitHub README 均写 MIT） | 通过 `pip install ".[memwall]"` 安装 |

以上只核实了直接依赖，**传递依赖（如 numpy、scipy）尚未核实。** 本项目为 Apache-2.0，上列许可证均为宽松许可证，与 Apache-2.0 项目兼容（此为一般判断，非法律意见）。
