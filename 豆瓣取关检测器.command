#!/bin/zsh
cd "$(dirname "$0")"

run_app() {
  "$1" app.py
}

try_run_app() {
  if command -v python3 >/dev/null 2>&1; then
    run_app python3
    return 0
  fi

  if command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(0 if sys.version_info.major == 3 else 1)' >/dev/null 2>&1; then
    run_app python
    return 0
  fi

  return 1
}

install_with_homebrew() {
  if ! command -v brew >/dev/null 2>&1; then
    echo
    echo "这台 Mac 还没有安装 Homebrew，无法自动通过命令行安装 Python 3。"
    echo "我会打开 Python 官方下载页面，请下载安装后重新双击这个文件。"
    open "https://www.python.org/downloads/macos/"
    return 1
  fi

  echo
  echo "正在使用 Homebrew 安装 Python 3..."
  brew install python
}

show_python_install_menu() {
  echo
  echo "找不到 Python 3。"
  echo
  echo "请选择下一步："
  echo "1. 使用 Homebrew 自动安装 Python 3"
  echo "2. 打开 Python 官方下载页面"
  echo "3. 退出"
  echo
  echo -n "请输入 1、2 或 3，然后按回车："
  read choice

  case "$choice" in
    1)
      install_with_homebrew
      if try_run_app; then
        return 0
      fi
      echo
      echo "Python 3 还没有准备好。请安装完成后重新双击这个文件。"
      ;;
    2)
      open "https://www.python.org/downloads/macos/"
      echo
      echo "下载安装 Python 3 后，请重新双击这个文件。"
      ;;
    *)
      echo
      echo "已退出。"
      ;;
  esac

  echo
  echo "按回车键关闭这个窗口。"
  read
}

try_run_app || show_python_install_menu
