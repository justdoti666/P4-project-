"""仓库测试包的初始化文件。

存在这个文件后，``python -m unittest discover -s tests -t .`` 与
``python -m unittest discover -s tests`` 两种命令都能把 ``tests`` 当作包导入；
CI 与本地命令因此可以统一（见 `.github/workflows/selfcheck.yml`）。
"""
