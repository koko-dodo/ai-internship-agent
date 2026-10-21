"""Explicit registration and validated execution; no dynamic tool lookup."""

from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .schemas import (
    FindEvidenceArguments, ParseJobArguments, ReadResumeArguments, ToolError, ToolResult,
    ToolSchema,
)
from .tools import DEFAULT_RESUME_DIRECTORY, find_evidence, parse_job, read_resume


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[type[BaseModel], Callable[..., Any], str]] = {}

    def register(
        self, name: str, arguments_model: type[BaseModel], handler: Callable[..., Any],
        *, description: str | None = None,
    ) -> None:
        """Only application code registers tools; reject duplicate names."""
        if not name.strip():
            raise ValueError("Tool name must not be blank")
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        if not issubclass(arguments_model, BaseModel) or not callable(handler):
            raise TypeError("A Pydantic arguments model and callable are required")
        if arguments_model.model_config.get("extra") != "forbid":
            raise ValueError("Tool argument models must forbid extra fields")
        self._tools[name] = (
            arguments_model, handler,
            description or handler.__doc__ or f"Run {name}.",
        )

    def get_tool_schemas(self) -> list[ToolSchema]:
        """Derive fresh JSON Schemas from the exact execution argument models."""
        return [
            ToolSchema(
                name=name, description=description,
                parameters=arguments_model.model_json_schema(),
            )
            for name, (arguments_model, _, description) in self._tools.items()
        ]

    def execute(self, name: str, arguments: Any) -> ToolResult:
        def failure(code: str, message: str) -> ToolResult:
            return ToolResult(
                tool_name=name, success=False, error=ToolError(code=code, message=message)
            )

        if name not in self._tools:
            return failure("unknown_tool", f"Unknown tool: {name}")
        model, handler, _ = self._tools[name]
        if not isinstance(arguments, dict):
            return failure("invalid_arguments", "Tool arguments must be an object")
        try:
            validated = model.model_validate(arguments, strict=True)
        except ValidationError as exc:
            # Do not echo supplied resume text or other argument values.
            details = "; ".join(
                f"{'.'.join(map(str, error['loc']))}: {error['type']}"
                for error in exc.errors(include_input=False, include_url=False)
            )
            return failure("invalid_arguments", details)
        try:
            data = handler(**validated.model_dump())
            if isinstance(data, BaseModel):
                data = data.model_dump(mode="json")
            elif isinstance(data, list):
                data = [
                    item.model_dump(mode="json") if isinstance(item, BaseModel) else item
                    for item in data
                ]
            return ToolResult(tool_name=name, success=True, data=data)
        except PermissionError:
            return failure("access_denied", "Resume access is not permitted")
        except FileNotFoundError:
            return failure("file_not_found", "Resume file or allowed directory does not exist")
        except UnicodeError:
            return failure("invalid_encoding", "Resume must use UTF-8 encoding")
        except ValueError as exc:
            return failure("invalid_input", str(exc))
        except OSError:
            return failure("io_error", "Unable to read resume file")
        except Exception:
            return failure("execution_error", "Tool execution failed unexpectedly")


def create_tool_registry(
    allowed_directory: str | Path = DEFAULT_RESUME_DIRECTORY,
) -> ToolRegistry:
    """Build the standard executor with a fixed, trusted resume directory."""
    registry = ToolRegistry()
    registry.register(
        "read_resume", ReadResumeArguments,
        partial(read_resume, allowed_directory=Path(allowed_directory).resolve()),
        description=read_resume.__doc__,
    )
    registry.register("parse_job", ParseJobArguments, parse_job)
    registry.register("find_evidence", FindEvidenceArguments, find_evidence)
    return registry
