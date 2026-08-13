"""AIFunRun コアパッケージ。"""

# 本体側に一括導入された動画ツールを、単体リポジトリでも透過的に共有する。
from .tooling import activate as _activate_portable_tools

_activate_portable_tools()
