#!/usr/bin/env python3
"""
CC_VisChat - 应用入口
Web-based Audio-Visual Interactive Application
"""

import argparse
import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import reload_config, get_config
from src.server import run_server


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="CC_VisChat - Web-based Audio-Visual Interactive Application"
    )

    parser.add_argument(
        "--config", "-c",
        type=str,
        default="config/config.yaml",
        help="配置文件路径 (默认: config/config.yaml)"
    )

    parser.add_argument(
        "--users", "-u",
        type=str,
        default="config/users.yaml",
        help="用户配置文件路径 (默认: config/users.yaml)"
    )

    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="服务器监听地址 (默认从配置文件读取)"
    )

    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="服务器监听端口 (默认从配置文件读取)"
    )

    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="启用调试模式 (热重载)"
    )

    parser.add_argument(
        "--no-ssl",
        action="store_true",
        help="禁用 SSL，使用 HTTP 模式 (用于反向代理场景，如 Caddy/Nginx)"
    )

    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()

    # 加载配置
    reload_config(args.config, args.users)
    config = get_config()

    print(r"""
   ____ ____  __     ___      ____ _           _
  / ___/ ___| \ \   / (_)___ / ___| |__   __ _| |_
 | |  | |      \ \ / /| / __| |   | '_ \ / _` | __|
 | |__| |___    \ V / | \__ \ |___| | | | (_| | |_
  \____\____|    \_/  |_|___/\____|_| |_|\__,_|\__|

    Web-based Audio-Visual Interactive Application
    """)

    print(f"配置文件: {args.config}")
    print(f"用户配置: {args.users}")
    print(f"调试模式: {'开启' if args.debug else '关闭'}")
    print(f"SSL 模式: {'禁用 (HTTP)' if args.no_ssl else '启用 (HTTPS)'}")
    print()

    # 启动服务器
    run_server(
        host=args.host,
        port=args.port,
        debug=args.debug,
        no_ssl=args.no_ssl
    )


if __name__ == "__main__":
    main()
