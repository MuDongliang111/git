"""配置加载器，支持 YAML 解析和环境变量插值。"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

from .models import AppConfig

_ENV_VAR_PATTERN = re.compile(r"\$\{(\w+)\}")


def _interpolate_env_vars(value: str) -> str:
    """将 ``${VAR_NAME}`` 占位符替换为环境变量的值。"""

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return _ENV_VAR_PATTERN.sub(_replace, value)


def _interpolate_dict(data: dict) -> dict:
    """递归地对所有字符串值进行环境变量插值。"""
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = _interpolate_env_vars(value)
        elif isinstance(value, dict):
            result[key] = _interpolate_dict(value)
        elif isinstance(value, list):
            result[key] = [
                _interpolate_env_vars(item) if isinstance(item, str) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


def _load_yaml_file(path: Path) -> dict:
    """加载并解析单个 YAML 文件，失败时返回空字典。"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} 中的 YAML 格式无效: {exc}") from exc


def _deep_merge(base: dict, override: dict) -> dict:
    """递归地将 *override* 合并到 *base* 中。列表会被替换，不会合并。"""
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _load_dotenv() -> None:
    """自动加载项目根目录下的 .env 文件。"""
    try:
        from dotenv import load_dotenv

        # 查找 .env 文件：从当前目录向上查找
        env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except ImportError:
        pass


def load_config(*paths: str | Path) -> AppConfig:
    """从一个或多个 YAML 文件加载配置。

    文件按顺序加载；后面的文件会 **深度合并** 到前面的文件之上。
    ``${VAR}`` 形式的环境变量在加载和合并后进行插值。

    Parameters
    ----------
    *paths : str | Path
        一个或多个 YAML 配置文件的路径。

    Returns
    -------
    AppConfig
        经过验证的应用配置。

    Raises
    ------
    ValueError
        如果 YAML 文件格式错误。
    pydantic.ValidationError
        如果合并后的配置验证失败。
    """
    # 自动加载 .env 文件
    _load_dotenv()

    merged: dict = {}
    for path in paths:
        path = Path(path)
        data = _load_yaml_file(path)
        if data:
            merged = _deep_merge(merged, data)

    merged = _interpolate_dict(merged)
    return AppConfig(**merged)
