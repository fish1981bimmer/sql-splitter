#!/usr/bin/env python3
"""sql-splitter CLI 入口 — pip install后的命令行入口"""

import sys
import os

# 将原始scripts目录加入path（pip install前兼容）
_SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'scripts')
if os.path.isdir(_SCRIPTS_DIR):
    sys.path.insert(0, _SCRIPTS_DIR)


def main():
    """主CLI入口"""
    # 检查是否是license子命令
    if len(sys.argv) > 1 and sys.argv[1] == 'license':
        _handle_license_command()
        return
    
    # 否则走正常的split流程
    from split_sql_v22 import main as split_main
    split_main()


def _handle_license_command():
    """处理license子命令"""
    try:
        from license_checker import activate_license, deactivate_license, show_status, get_machine_id
    except ImportError:
        print("License模块未找到")
        sys.exit(1)
    
    if len(sys.argv) < 3:
        print("用法:")
        print("  sql-splitter license status        — 查看授权状态")
        print("  sql-splitter license activate KEY  — 激活License")
        print("  sql-splitter license deactivate    — 注销License")
        print("  sql-splitter license machine-id    — 显示机器指纹")
        sys.exit(0)
    
    subcmd = sys.argv[2]
    
    if subcmd == 'status':
        show_status()
    elif subcmd == 'activate':
        if len(sys.argv) < 4:
            print("请提供License Key: sql-splitter license activate XXXX-XXXX-XXXX-XXXX")
            sys.exit(1)
        key = sys.argv[3]
        holder = ''
        if '--holder' in sys.argv:
            idx = sys.argv.index('--holder')
            if idx + 1 < len(sys.argv):
                holder = sys.argv[idx + 1]
        ok, msg = activate_license(key, holder)
        print(msg)
    elif subcmd == 'deactivate':
        print(deactivate_license())
    elif subcmd == 'machine-id':
        print(get_machine_id())
    else:
        print(f"未知子命令: {subcmd}")
        sys.exit(1)


if __name__ == '__main__':
    main()
