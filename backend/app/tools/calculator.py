"""Safe arithmetic evaluator. Uses ast parsing (never eval) so only numbers and
the whitelisted operators can execute -- no names, imports, or attribute access.
"""

from __future__ import annotations

import ast
import operator

from app.tools import ToolSpec

TOOL_SPEC = ToolSpec(
    name="calculator",
    description="Evaluate a basic arithmetic expression (+ - * / // % **, parentheses).",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    },
)

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

# Model-supplied input: an unbounded exponent (e.g. 9**9**9) would hang the server.
_MAX_EXPONENT = 1000

_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node: ast.AST) -> int | float:
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise TypeError(f"Only numbers allowed, got {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > _MAX_EXPONENT:
                raise ValueError(f"Exponent too large (max {_MAX_EXPONENT})")
            return left**right
        op = _BINOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Operator {type(node.op).__name__} not allowed")
        return op(left, right)
    if isinstance(node, ast.UnaryOp):
        op = _UNARYOPS.get(type(node.op))
        if op is None:
            raise ValueError(f"Operator {type(node.op).__name__} not allowed")
        return op(_eval(node.operand))
    raise ValueError(f"Disallowed expression: {type(node).__name__}")


async def run(args: dict) -> str:
    expr = args.get("expression")
    if not isinstance(expr, str) or not expr.strip():
        return "Error: missing 'expression' string argument"
    try:
        return str(_eval(ast.parse(expr, mode="eval")))
    except ZeroDivisionError:
        return "Error: division by zero"
    except (SyntaxError, ValueError, TypeError, ArithmeticError, RecursionError) as exc:
        return f"Error: {exc}"
