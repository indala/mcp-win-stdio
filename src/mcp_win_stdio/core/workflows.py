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
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

from jsonschema import Draft202012Validator

from mcp_win_stdio.core.config import WORKFLOWS_DIR, ensure_workspace_dirs

_VALIDATOR_CACHE: Dict[str, Draft202012Validator] = {}
TEMPLATE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")


def has_template(val: Any) -> bool:
    """Check if value or any nested element contains {{ template }} markers."""
    if isinstance(val, str):
        return bool(TEMPLATE_PATTERN.search(val))
    elif isinstance(val, dict):
        return any(has_template(v) for v in val.values())
    elif isinstance(val, list):
        return any(has_template(item) for item in val)
    return False


def extract_template_references(val: Any) -> List[str]:
    """Extract all template reference paths (e.g. ['steps.step1.stdout', 'deploy_env'])."""
    refs: List[str] = []
    if isinstance(val, str):
        for m in TEMPLATE_PATTERN.finditer(val):
            refs.append(m.group(1).strip())
    elif isinstance(val, dict):
        for v in val.values():
            refs.extend(extract_template_references(v))
    elif isinstance(val, list):
        for item in val:
            refs.extend(extract_template_references(item))
    return refs


def validate_workflow_preflight(
    definition: Dict[str, Any],
    catalog_describe_fn: Optional[Callable[[str, str], Optional[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Schema-Aware Workflow Preflight Validator.
    Validates step ordering, template reference shapes, tool existence, and JSON parameter schemas.
    Template-aware: skips strict type validation on arguments containing dynamic {{ steps... }} expressions.
    Collects and returns ALL errors so the agent or caller can fix them in a single roundtrip.
    """
    errors: List[Dict[str, Any]] = []

    if not isinstance(definition, dict):
        return [{"type": "structure_error", "message": "Workflow definition must be a JSON object/dictionary."}]

    steps = definition.get("steps")
    if not isinstance(steps, list) or len(steps) == 0:
        return [{"type": "structure_error", "message": "Workflow must declare a non-empty 'steps' list."}]

    declared_params = set(definition.get("parameters", {}).keys())
    seen_step_ids: Set[str] = set()

    # Fallback to catalog.describe_tool if describe fn is not injected
    if not catalog_describe_fn:
        from mcp_win_stdio.server.catalog import describe_tool as cat_describe
        catalog_describe_fn = cat_describe

    for idx, step in enumerate(steps):
        step_num = idx + 1
        if not isinstance(step, dict):
            errors.append({
                "type": "invalid_step",
                "step_index": step_num,
                "message": f"Step {step_num} is not a valid dictionary.",
            })
            continue

        step_id = step.get("id") or f"step_{step_num}"
        server = str(step.get("server") or "").lower().strip()
        tool = str(step.get("tool") or "").strip()
        raw_args = step.get("arguments") or {}

        # 1. Server & tool existence
        if not server:
            errors.append({
                "type": "missing_field",
                "step_id": step_id,
                "step_index": step_num,
                "field": "server",
                "message": f"Step '{step_id}' is missing required 'server' field.",
            })
        if not tool:
            errors.append({
                "type": "missing_field",
                "step_id": step_id,
                "step_index": step_num,
                "field": "tool",
                "message": f"Step '{step_id}' is missing required 'tool' field.",
            })

        # 2. Template Reference Ordering & Existence
        refs = extract_template_references(raw_args)
        for ref in refs:
            if ref.startswith("steps."):
                parts = ref.split(".")
                if len(parts) < 2:
                    errors.append({
                        "type": "malformed_template",
                        "step_id": step_id,
                        "step_index": step_num,
                        "reference": ref,
                        "message": f"Step '{step_id}' has malformed step reference '{{{{ {ref} }}}}'. Expected '{{{{ steps.<step_id>.<key> }}}}'.",
                    })
                else:
                    ref_step_id = parts[1]
                    if ref_step_id not in seen_step_ids:
                        errors.append({
                            "type": "invalid_step_dependency",
                            "step_id": step_id,
                            "step_index": step_num,
                            "reference": ref,
                            "message": f"Step '{step_id}' references step '{ref_step_id}' via '{{{{ {ref} }}}}' before '{ref_step_id}' has executed.",
                        })
            else:
                top_param = ref.split(".")[0]
                if top_param not in declared_params and top_param not in ("params", "env"):
                    errors.append({
                        "type": "undeclared_parameter",
                        "step_id": step_id,
                        "step_index": step_num,
                        "reference": ref,
                        "message": f"Step '{step_id}' references undeclared workflow parameter '{{{{ {ref} }}}}'. Declared parameters: {sorted(declared_params)}.",
                    })

        # 3. Tool Schema Contract Validation (skipping templated arguments & normalizing aliases)
        if server and tool and catalog_describe_fn:
            tool_meta = catalog_describe_fn(server, tool)
            if not tool_meta:
                # If custom mock caller or unlisted test tool, allow execution
                pass
            else:
                schema = tool_meta.get("parameters")
                if isinstance(schema, dict) and isinstance(raw_args, dict):
                    # Check parameter aliases mapping
                    try:
                        from mcp_win_stdio.server.catalog import normalize_arguments
                        norm_args = normalize_arguments(server, tool, raw_args)
                    except Exception:
                        norm_args = dict(raw_args)

                    # Filter out arguments containing dynamic runtime {{ templates }}
                    # so static schema types (e.g. integer or object) don't falsely fail on templated strings
                    static_args = {k: v for k, v in norm_args.items() if not has_template(v)}

                    cache_key = f"{server}:{tool}"
                    if cache_key not in _VALIDATOR_CACHE:
                        _VALIDATOR_CACHE[cache_key] = Draft202012Validator(schema)
                    validator = _VALIDATOR_CACHE[cache_key]

                    # Check required fields that are completely omitted (even in templates or aliases)
                    req_fields = schema.get("required", [])
                    for rf in req_fields:
                        if rf not in norm_args:
                            errors.append({
                                "type": "missing_required_argument",
                                "step_id": step_id,
                                "step_index": step_num,
                                "server": server,
                                "tool": tool,
                                "field": rf,
                                "message": f"Step '{step_id}' ({server}.{tool}) is missing required parameter '{rf}'.",
                            })

                    # Validate static arguments against schema properties
                    for err in validator.iter_errors(static_args):
                        # Skip root "required" violations here since we handle them explicitly above
                        if err.validator == "required":
                            continue
                        field_path = ".".join(str(p) for p in err.path) if err.path else "arguments"
                        errors.append({
                            "type": "schema_validation_error",
                            "step_id": step_id,
                            "step_index": step_num,
                            "server": server,
                            "tool": tool,
                            "field": field_path,
                            "message": f"Step '{step_id}' argument '{field_path}' violates schema: {err.message}",
                        })

        seen_step_ids.add(step_id)

    return errors



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


def _truncate_output_for_llm(val: Any, max_chars: int = 4000) -> Any:
    """Safely truncate massive terminal/stdout dumps to prevent agent context overflow."""
    if isinstance(val, str) and len(val) > max_chars:
        omitted = len(val) - max_chars
        return val[:max_chars] + f"\n... [{omitted:,} characters truncated to conserve LLM context tokens] ..."
    elif isinstance(val, dict):
        truncated_dict = {}
        for k, v in val.items():
            if isinstance(v, str) and len(v) > max_chars:
                omitted = len(v) - max_chars
                truncated_dict[k] = v[:max_chars] + f"\n... [{omitted:,} characters truncated] ..."
            else:
                truncated_dict[k] = v
        return truncated_dict
    return val


def run_workflow(
    name_or_def: Union[str, Dict[str, Any]],
    parameters: Optional[Dict[str, Any]] = None,
    project_root: Optional[Union[str, Path]] = None,
    call_tool_fn: Optional[Callable[[str, str, Dict[str, Any]], Any]] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Executes a multi-step workflow in a single run without round-trip latency.
    Pipes variables and step outputs forward through templating (both {{ steps.id.key }} and {{ steps.id.output.key }}).
    Supports dry_run previews, continue_on_error, on_failure recovery steps, and LLM output token protection.
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

    # 2. Preflight Schema & Template Validation (skipped if custom mock call_tool_fn is injected for unit testing)
    if not call_tool_fn:
        preflight_errors = validate_workflow_preflight(wf)
        if preflight_errors:
            return {
                "status": "preflight_failed",
                "workflow": wf_name,
                "total_errors": len(preflight_errors),
                "errors": preflight_errors,
                "message": f"Workflow '{wf_name}' rejected during preflight validation with {len(preflight_errors)} error(s).",
            }

    # 3. Build parameter context
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

    # Handle dry_run mode: interpolate known static parameters and mark runtime step dependencies
    if dry_run:
        plan: List[Dict[str, Any]] = []
        for idx, step in enumerate(steps):
            step_id = step.get("id") or f"step_{idx + 1}"
            server = step.get("server", "").lower().strip()
            tool = step.get("tool", "").strip()
            raw_args = step.get("arguments") or {}

            def _dry_run_resolver(val: Any) -> Any:
                if isinstance(val, str):
                    exact = re.fullmatch(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", val.strip())
                    if exact:
                        expr = exact.group(1).strip()
                        if expr.startswith("steps."):
                            return f"<unresolved_runtime_output: {expr}>"
                        return resolve_template_value(val, context)

                    def _mark_unresolved(m: re.Match) -> str:
                        expr = m.group(1).strip()
                        if expr.startswith("steps."):
                            return f"<unresolved_runtime_output: {expr}>"
                        resolved = resolve_template_value(m.group(0), context)
                        return str(resolved)

                    return re.sub(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}", _mark_unresolved, val)
                elif isinstance(val, dict):
                    return {k: _dry_run_resolver(v) for k, v in val.items()}
                elif isinstance(val, list):
                    return [_dry_run_resolver(item) for item in val]
                return val

            resolved_args = _dry_run_resolver(raw_args)
            plan.append({
                "step_id": step_id,
                "step_index": idx + 1,
                "server": server,
                "tool": tool,
                "resolved_arguments": resolved_args,
                "status": "dry_run_preview",
            })
        return {
            "workflow": wf_name,
            "status": "dry_run_plan",
            "dry_run": True,
            "total_steps": len(steps),
            "plan": plan,
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
        continue_on_err = step.get("continue_on_error", False)
        on_failure_action = step.get("on_failure")
        summarize_out = step.get("summarize_output", False)

        step_start = time.perf_counter()
        is_error = False
        try:
            # Interpolate variables into step arguments
            resolved_args = resolve_template_value(raw_args, context)
            result = caller(server, tool, resolved_args)
        except Exception as e:
            result = {"isError": True, "error": str(e)}
            is_error = True
        step_duration = round((time.perf_counter() - step_start) * 1000, 2)

        # Check for error
        is_error = False
        if isinstance(result, dict):
            if result.get("isError") or result.get("status") == "error":
                is_error = True

        # Handle on_failure fallback/rollback step if step failed
        recovery_record = None
        if is_error and isinstance(on_failure_action, dict):
            fail_server = on_failure_action.get("server", server).lower().strip()
            fail_tool = on_failure_action.get("tool", "").strip()
            fail_raw_args = on_failure_action.get("arguments") or {}
            fail_resolved_args = resolve_template_value(fail_raw_args, context)
            try:
                fail_res = caller(fail_server, fail_tool, fail_resolved_args)
                recovery_record = {
                    "recovery_step": f"{step_id}_recovery",
                    "server": fail_server,
                    "tool": fail_tool,
                    "status": "success",
                    "output": fail_res,
                }
            except Exception as fe:
                recovery_record = {
                    "recovery_step": f"{step_id}_recovery",
                    "server": fail_server,
                    "tool": fail_tool,
                    "status": "recovery_failed",
                    "error": str(fe),
                }

        # Truncate / summarize massive output if requested or very large
        final_output = _truncate_output_for_llm(result) if (summarize_out or is_error is False) else result

        step_record = {
            "step_id": step_id,
            "step_index": idx + 1,
            "server": server,
            "tool": tool,
            "duration_ms": step_duration,
            "status": "error" if is_error else "success",
            "output": final_output,
        }
        if recovery_record:
            step_record["recovery"] = recovery_record

        execution_trace.append(step_record)

        # Store in context for subsequent steps (supporting both steps.<id>.<k> and steps.<id>.output.<k>)
        if isinstance(result, dict):
            step_ctx = dict(result)
            if "output" not in step_ctx:
                step_ctx["output"] = result
            context["steps"][step_id] = step_ctx
        else:
            context["steps"][step_id] = {"output": result}

        if is_error and not continue_on_err and halt_on_failure:
            # Explicitly append skipped records for all remaining unexecuted steps
            for skip_idx in range(idx + 1, len(steps)):
                skip_step = steps[skip_idx]
                skip_id = skip_step.get("id") or f"step_{skip_idx + 1}"
                execution_trace.append({
                    "step_id": skip_id,
                    "step_index": skip_idx + 1,
                    "server": skip_step.get("server", "").lower().strip(),
                    "tool": skip_step.get("tool", "").strip(),
                    "status": "skipped",
                    "output": None,
                })

            total_duration = round((time.perf_counter() - start_time) * 1000, 2)
            successful_steps = sum(1 for s in execution_trace if s.get("status") == "success")
            failed_steps = sum(1 for s in execution_trace if s.get("status") == "error")
            skipped_steps = sum(1 for s in execution_trace if s.get("status") == "skipped")
            executed_steps = successful_steps + failed_steps
            return {
                "workflow": wf_name,
                "status": "halted_on_error",
                "failed_step": step_id,
                "steps_completed": successful_steps,
                "steps_successful": successful_steps,
                "steps_failed": failed_steps,
                "steps_skipped": skipped_steps,
                "steps_executed": executed_steps,
                "total_steps": len(steps),
                "duration_ms": total_duration,
                "error": result,
                "trace": execution_trace,
            }

    total_duration = round((time.perf_counter() - start_time) * 1000, 2)
    successful_steps = sum(1 for s in execution_trace if s.get("status") == "success")
    failed_steps = sum(1 for s in execution_trace if s.get("status") == "error")
    skipped_steps = sum(1 for s in execution_trace if s.get("status") == "skipped")
    executed_steps = successful_steps + failed_steps
    has_any_error = failed_steps > 0
    return {
        "workflow": wf_name,
        "status": "completed_with_errors" if has_any_error else "success",
        "steps_completed": successful_steps,
        "steps_successful": successful_steps,
        "steps_failed": failed_steps,
        "steps_skipped": skipped_steps,
        "steps_executed": executed_steps,
        "total_steps": len(steps),
        "duration_ms": total_duration,
        "trace": execution_trace,
    }
