# gacha_simulator/paths.py
"""路径解析工具——同时支持开发环境和 PyInstaller 打包环境。

只读路径（捆绑资源）：
    get_resource(filename)     → resources/

可写路径（应用数据——与 .exe 同级或包目录）：
    get_app_dir()              → 开发: 包目录 / 打包: .exe 所在目录
    get_config_dir()           → config/（可写——用户修改的配置）
    get_strategies_dir()       → strategies/（插件目录）

用户数据路径：
    get_user_data_dir(*subdirs) → 开发: 包内子目录 / 打包: %APPDATA%/GachaStat/
"""

import os
import sys


def get_base_dir() -> str:
    """返回应用根目录（只读——捆绑的资源文件）。

    开发环境：paths.py 所在目录（= gacha_simulator/ 包目录）
    打包环境：sys._MEIPASS（PyInstaller 的 _internal/ 目录）
    """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def get_app_dir() -> str:
    """返回应用可写根目录。

    开发环境：paths.py 所在目录（= gacha_simulator/ 包目录）
    打包环境：.exe 所在目录（os.path.dirname(sys.executable)）——与 _internal/ 同级，
             config/ 和 strategies/ 在此目录下，用户可直接访问和修改。
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_config_dir() -> str:
    """返回配置目录的绝对路径（可写——用户修改的配置）。

    开发环境：gacha_simulator/config/
    打包环境：dist/GachaStat/config/（与 .exe 同级，非 _internal/ 内只读副本）
    """
    return os.path.join(get_app_dir(), 'config')


def get_strategies_dir() -> str:
    """返回插件策略目录的绝对路径。

    开发环境：gacha_simulator/strategies/
    打包环境：dist/GachaStat/strategies/（与 .exe 同级）
    目录不存在时自动创建。
    """
    target = os.path.join(get_app_dir(), 'strategies')
    os.makedirs(target, exist_ok=True)
    return target


def get_resource(filename: str) -> str:
    """返回 resources/ 目录下指定文件的绝对路径（只读——捆绑的资源）。"""
    return os.path.join(get_base_dir(), 'resources', filename)


def get_user_data_dir(*subdirs: str) -> str:
    """返回用户数据目录的绝对路径（可写——用户生成的数据）。

    开发环境：paths.py 所在目录下的对应子目录
    打包环境：%APPDATA%/GachaStat/ 下的对应子目录
    自动创建目录（exist_ok=True）。

    用法：
        get_user_data_dir()                    → %APPDATA%/GachaStat/
        get_user_data_dir('output')            → %APPDATA%/GachaStat/output/
        get_user_data_dir('output', 'analysis') → %APPDATA%/GachaStat/output/analysis/
    """
    if getattr(sys, 'frozen', False):
        base = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'GachaStat')
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(base, *subdirs)
    os.makedirs(target, exist_ok=True)
    return target
