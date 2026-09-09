#!/bin/zsh
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v python3 >/dev/null 2>&1; then
  print '请先安装 Python 3：https://www.python.org/downloads/'
  read '?按回车关闭'
  exit 1
fi
python3 scripts/serve.py
read '?按回车关闭窗口'
