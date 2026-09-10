#!/bin/zsh
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v python3 >/dev/null 2>&1; then
  print '请先安装 Python 3：https://www.python.org/downloads/'
  read '?按回车关闭'
  exit 1
fi
album_python="$(command -v python3)"
if [[ -x .venv/bin/python3 ]]; then
  album_python="$PWD/.venv/bin/python3"
fi
if ! "$album_python" -c 'from PIL import Image, ImageOps' >/dev/null 2>&1; then
  print '首次启动：正在准备照片处理组件…'
  python3 -m venv .venv || exit 1
  album_python="$PWD/.venv/bin/python3"
  "$album_python" -m pip install -r requirements.txt || { read '?组件下载失败，请检查网络。按回车关闭'; exit 1; }
fi
"$album_python" scripts/bootstrap.py
"$album_python" scripts/serve.py
read '?按回车关闭窗口'
