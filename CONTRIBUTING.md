# 参与开发

使用 Windows 与 Python 3.12 或 3.13。先创建虚拟环境，再安装开发依赖：

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe main.py
```

提交改动前运行：

```powershell
.venv\Scripts\python.exe -m ruff check .
.venv\Scripts\python.exe -m ruff format --check .
.venv\Scripts\python.exe -m pytest -q
```

新增业务逻辑优先放在独立服务中，界面通过信号传递操作；扩展入口见 [架构说明](docs/architecture.md)。
针对行为变化补充测试，特别是题目身份、导入失败、存储失败和切题时的状态清理。
测试应使用临时目录、模拟动作宿主与离屏 Qt，避免修改真实学习记录。

问题报告请附上 Windows / Python 版本、复现步骤、预期行为与实际行为。
日志中可能包含题库名称、题目 ID 和本地路径，分享前请按需删去个人信息。

## 构建与发布

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe scripts/build_release.py
```

构建脚本会检查打包程序启动、Qt Multimedia、示例题库导入与缓存恢复，生成 `release/` 下的 ZIP 和 SHA-256 校验文件。
更新 `app/version.py` 与 `RELEASE_NOTES.md` 后推送对应 `v版本号` 标签，GitHub Actions 会测试、构建并上传 Release。
标签必须与代码版本一致。ZIP 中的 `_internal/` 为可替换的运行库，`data/` 在首次启动时创建。
