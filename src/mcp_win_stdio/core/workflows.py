"""
Workflow Engine for mcp-win-stdio (mws).
Enables AI agents and developers to compose, persist, and execute multi-step MCP tool chains
in a single call, eliminating token bloat and multi-turn latency.
Stored in ~/.mcp-win-stdio/workflows/ (global) or <workspace>/.mws/workflows/ (project).
"""

import json
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from mcp_win_stdio.core.config import WORKFLOWS_DIR, ensure_workspace_dirs


def resolve_template_value(val: Any, context: Dict[str, Any]) -> Any:
    """
    Recursively interpolates parameters and step outputs into arguments.
    Supports full object resolution (e.g. '{{ steps.step1.data }}' -> list/dict)
    and string interpolation (e.g. 'prefix_{{ host }}_suffix').
    """
    if isinstance(val, str):
        # 1. Exact full-variable match: preserve data type (list, dict, int, etc.)
        exact_match = re.fullmatch(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", val.strip())
        if exact_match:
            path = exact_match.group(1).split(".")
            cur = context
            found = True
            for part in path:
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    found = False
                    break
            if found:
                return cur

        # 2. Substring interpolation for strings
        def _replace_match(m: re.Match) -> str:
            path = m.group(1).split(".")
            cur = context
            for part in path:
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    return m.group(0)
            return str(cur)

        return re.sub(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", _replace_match, val)

    elif isinstance(val, dict):
        return {k: resolve_template_value(v, context) for k, v in val.items()}
    elif isinstance(val, list):
        return [resolve_template_value(item, context) for item in val]
    return val


def get_workflow_dirs(project_root: Optional[Union[str, Path]] = None) -> List[Tuple[Path, str]]:
    """
    Returns prioritized list of (directory_path, scope_name) for workflow discovery.
    Prioritizes project-local workflows (.mws/workflows or .mcp-win-stdio/workflows)
    before falling back to global (~/.mcp-win-stdio/workflows).
    """
    ensure_workspace_dirs()
    dirs: List[Tuple[Path, str]] = []

    root = Path(project_root).resolve() if project_root else Path.cwd().resolve()

    p1 = root / ".mws" / "workflows"
    if p1.exists():
        dirs.append((p1, "project"))

    p2 = root / ".mcp-win-stdio" / "workflows"
    if p2.exists() and p2 != p1:
        dirs.append((p2, "project"))

    dirs.append((WORKFLOWS_DIR, "global"))
    return dirs


def list_workflows(
    project_root: Optional[Union[str, Path]] = None,
    scope: str = "all",
) -> List[Dict[str, Any]]:
    """
    Discover all registered workflows across project and global scopes.
    """
    search_dirs = get_workflow_dirs(project_root)
    results: List[Dict[str, Any]] = []
    seen_names = set()

    for d, s in search_dirs:
        if scope != "all" and s != scope:
            continue
        if not d.exists():
            continue

        for p in d.glob("*.json"):
            name = p.stem.lower()
            if name in seen_names:
                continue
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                results.append(
                    {
                        "name": name,
                        "title": data.get("title", name),
                        "description": data.get("description", ""),
                        "scope": s,
                        "file_path": str(p).replace("\\", "/"),
                        "parameters": data.get("parameters", {}),
                        "steps_count": len(data.get("steps", [])),
                    }
                )
                seen_names.add(name)
            except Exception:
                continue

    return results


def load_workflow(
    name: str,
    project_root: Optional[Union[str, Path]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load a workflow definition by name, searching project scope first, then global.
    """
    clean_name = name.lower().strip()
    search_dirs = get_workflow_dirs(project_root)

    for d, _ in search_dirs:
        candidate = d / f"{clean_name}.json"
        if candidate.exists():
            try:
                data = json.loads(candidate.read_text(encoding="utf-8"))
                data["_file_path"] = str(candidate).replace("\\", "/")
                return data
            except Exception:
                return None

    return None


def save_workflow(
    name: str,
    definition: Dict[str, Any],
    scope: str = "project",
    project_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Validate and save a workflow definition to disk.
    scope: 'project' saves to .mws/workflows/<name>.json in the current workspace.
           'global' saves to ~/.mcp-win-stdio/workflows/<name>.json.
    """
    clean_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name.lower().strip())
    if not clean_name:
        raise ValueError("Invalid workflow name. Must contain alphanumeric characters.")

    if not isinstance(definition, dict):
        raise ValueError("Workflow definition must be a dictionary.")

    steps = definition.get("steps")
    if not steps or not isinstance(steps, list):
        raise ValueError("Workflow definition must contain a non-empty 'steps' list.")

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"Step {idx + 1} must be a dictionary.")
        if not step.get("server"):
            raise ValueError(f"Step {idx + 1} is missing required 'server' field.")
        if not step.get("tool"):
            raise ValueError(f"Step {idx + 1} is missing required 'tool' field.")

    # Target directory resolution
    if scope == "global":
        target_dir = WORKFLOWS_DIR
    else:
        root = Path(project_root).resolve() if project_root else Path.cwd().resolve()
        target_dir = root / ".mws" / "workflows"

    target_dir.mkdir(parents=True, exist_ok=True)
    target_file = target_dir / f"{clean_name}.json"

    # Set metadata defaults
    definition.setdefault("name", clean_name)
    definition.setdefault("title", clean_name.replace("_", " ").title())
    definition.setdefault("description", f"Custom workflow '{clean_name}'")
    definition.setdefault("parameters", {})

    target_file.write_text(json.dumps(definition, indent=2), encoding="utf-8")

    return {
        "status": "success",
        "name": clean_name,
        "scope": scope,
        "path": str(target_file).replace("\\", "/"),
        "steps_count": len(steps),
        "message": f"Workflow '{clean_name}' successfully saved ({scope} scope).",
    }


def delete_workflow(
    name: str,
    scope: Optional[str] = None,
    project_root: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """
    Delete a workflow file from project or global scope.
    """
    clean_name = name.lower().strip()
    search_dirs = get_workflow_dirs(project_root)
    deleted = False
    deleted_paths = []

    for d, s in search_dirs:
        if scope and scope != "all" and s != scope:
            continue
        candidate = d / f"{clean_name}.json"
        if candidate.exists():
            candidate.unlink()
            deleted = True
            deleted_paths.append(str(candidate).replace("\\", "/"))

    return {
        "name": clean_name,
        "deleted": deleted,
        "deleted_paths": deleted_paths,
        "message": f"Workflow '{clean_name}' deleted." if deleted else f"Workflow '{clean_name}' not found.",
    }


def run_workflow(
    name_or_def: Union[str, Dict[str, Any]],
    parameters: Optional[Dict[str, Any]] = None,
    project_root: Optional[Union[str, Path]] = None,
    call_tool_fn: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
) -> Dict[str, Any]:
    """
    Executes a multi-step workflow in a single run without round-trip latency.
    Pipes variables and step outputs forward through templating.
    Halts execution safely if any step fails.
    """
    start_time = time.perf_counter()

    # 1. Resolve workflow definition
    if isinstance(name_or_def, str):
        wf = load_workflow(name_or_def, project_root=project_root)
        if not wf:
            return {
                "status": "error",
                "error": f"Workflow '{name_or_def}' not found in project or global workflows.",
            }
        wf_name = name_or_def
    else:
        wf = name_or_def
        wf_name = wf.get("name", "ad_hoc_workflow")

    steps = wf.get("steps", [])
    if not steps:
        return {"status": "error", "error": "Workflow has no steps defined."}

    # 2. Build parameter context
    declared_params = wf.get("parameters", {})
    context_params: Dict[str, Any] = {}

    for param_name, param_meta in declared_params.items():
        if isinstance(param_meta, dict) and "default" in param_meta:
            context_params[param_name] = param_meta["default"]

    if parameters:
        context_params.update(parameters)

    context: Dict[str, Any] = {
        "params": context_params,
        "steps": {},
        **context_params,  # top-level shorthand e.g. {{ host }}
    }

    # 3. Setup tool caller
    if not call_tool_fn:
        from mcp_win_stdio.server.process_pool import GLOBAL_POOL

        def _default_caller(server: str, tool: str, args: Dict[str, Any]) -> Any:
            proc = GLOBAL_POOL.get_or_spawn(server)
            return proc.call_tool(tool, args)

        caller = _default_caller
    else:
        caller = call_tool_fn

    # 4. Execute steps sequentially
    execution_trace: List[Dict[str, Any]] = []

    for idx, step in enumerate(steps):
        step_id = step.get("id") or f"step_{idx + 1}"
        server = step.get("server", "").lower().strip()
        tool = step.get("tool", "").strip()
        raw_args = step.get("arguments") or {}
        halt_on_failure = step.get("halt_on_failure", True)

        # Interpolate variables into step arguments
        resolved_args = resolve_template_value(raw_args, context)

        step_start = time.perf_counter()
        try:
            result = caller(server, tool, resolved_args)
        except Exception as e:
            result = {"isError": True, "error": str(e)}
        step_duration = round((time.perf_counter() - step_start) * 1000, 2)

        # Check for error
        is_error = False
        if isinstance(result, dict):
            if result.get("isError") or result.get("status") == "error":
                is_error = True

        step_record = {
            "step_id": step_id,
            "step_index": idx + 1,
            "server": server,
            "tool": tool,
            "duration_ms": step_duration,
            "status": "error" if is_error else "success",
            "output": result,
        }
        execution_trace.append(step_record)

        # Store in context for subsequent steps
        context["steps"][step_id] = result

        if is_error and halt_on_failure:
            total_duration = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "workflow": wf_name,
                "status": "halted_on_error",
                "failed_step": step_id,
                "steps_completed": idx,
                "total_steps": len(steps),
                "duration_ms": total_duration,
                "error": result,
                "trace": execution_trace,
            }

    total_duration = round((time.perf_counter() - start_time) * 1000, 2)
    return {
        "workflow": wf_name,
        "status": "success",
        "steps_completed": len(steps),
        "total_steps": len(steps),
        "duration_ms": total_duration,
        "trace": execution_trace,
    }
