"""安全的计算器工具，使用受限的表达式求值器。"""

from __future__ import annotations

import math
import operator as op

from ..base import ToolDefinition

# 表达式求值器中允许的名称
_SAFE_NAMES: dict = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "pow": pow,
    "sqrt": math.sqrt,
    "ceil": math.ceil,
    "floor": math.floor,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
    "pi": math.pi,
    "e": math.e,
}

_EXPR_SCHEMA = {
    "type": "object",
    "properties": {
        "expression": {
            "type": "string",
            "description": "要计算的数学表达式，例如 '2 + 3 * 4' 或 'sqrt(16) + sin(pi/2)'",
        }
    },
    "required": ["expression"],
}


async def _evaluate(expression: str) -> str:
    """安全地计算数学表达式。

    使用 Python 的 ``ast.literal_eval`` 风格的方法，
    仅允许受限的运算符和函数集合。不允许内置函数、
    属性访问或赋值操作。
    """
    import ast

    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        return f"表达式语法错误: {exc}"

    def _eval_node(node: ast.AST) -> object:
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            name = node.id
            if name in _SAFE_NAMES:
                return _SAFE_NAMES[name]
            raise ValueError(f"不允许使用 '{name}'")
        elif isinstance(node, ast.BinOp):
            left = _eval_node(node.left)
            right = _eval_node(node.right)
            op_map = {
                ast.Add: op.add,
                ast.Sub: op.sub,
                ast.Mult: op.mul,
                ast.Div: op.truediv,
                ast.FloorDiv: op.floordiv,
                ast.Mod: op.mod,
                ast.Pow: op.pow,
            }
            op_func = op_map.get(type(node.op))
            if op_func is None:
                raise ValueError(f"不支持的运算符: {type(node.op).__name__}")
            return op_func(left, right)
        elif isinstance(node, ast.UnaryOp):
            operand = _eval_node(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return +operand
            raise ValueError(f"不支持的一元运算符: {type(node.op).__name__}")
        elif isinstance(node, ast.Call):
            func = _eval_node(node.func)
            args = [_eval_node(a) for a in node.args]
            if not callable(func):
                raise ValueError(f"'{node.func.id}' 不可调用")  # type: ignore[attr-defined]
            return func(*args)
        else:
            raise ValueError(f"不支持的结构: {type(node).__name__}")

    try:
        result = _eval_node(tree.body)
        return str(result)
    except Exception as exc:
        return f"计算表达式时出错: {exc}"


def build_calculator_tool() -> ToolDefinition:
    return ToolDefinition(
        name="calculator",
        description="安全地计算数学表达式。支持基本算术运算、"
        "三角函数（sin/cos/tan）、sqrt、log、ceil/floor 以及常量 pi/e。",
        parameters=_EXPR_SCHEMA,
        handler=_evaluate,
        source="builtin",
    )
