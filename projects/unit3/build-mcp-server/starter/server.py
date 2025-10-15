#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
TODO: Implement tools for analyzing git changes and suggesting PR templates
"""

import json
import subprocess
from pathlib import Path
from typing import Optional
import os

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# PR template directory (shared across all modules)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Default PR templates
DEFAULT_TEMPLATES = {
    "bug.md": "Bug Fix",
    "feature.md": "Feature",
    "docs.md": "Documentation",
    "refactor.md": "Refactor",
    "test.md": "Test",
    "performance.md": "Performance",
    "security.md": "Security"
}

# Type mapping for PR templates
TYPE_MAPPING = {
    "bug": "bug.md",
    "fix": "bug.md",
    "feature": "feature.md",
    "enhancement": "feature.md",
    "docs": "docs.md",
    "documentation": "docs.md",
    "refactor": "refactor.md",
    "cleanup": "refactor.md",
    "test": "test.md",
    "testing": "test.md",
    "performance": "performance.md",
    "optimization": "performance.md",
    "security": "security.md"
}


@mcp.tool()
async def analyze_file_changes(base_branch: str = "main", max_diff_lines: int = 500, include_diff: bool = True, working_directory: Optional[str] = None) -> str:
    """Get the full diff and list of changed files in the current git repository.

    Args:
        base_branch: Base branch to compare against (default: main)
        max_diff_lines: Maximum number of diff lines to return because Large diffs can easily exceed this (default: 500)
        include_diff: Include the full diff content (default: true)
        working_directory: Optional working directory to run git commands in (default: None, uses MCP roots or server CWD)
    """
    try:
        # Try to get working directory from roots first
        if working_directory is None:
            try:
                context = mcp.get_context()
                roots_result = await context.session.list_roots()
                # Get the first root - Claude Code sets this to the CWD
                root = roots_result.roots[0]
                # FileUrl object has a .path property that gives us the path directly
                working_directory = root.uri.path
            except Exception:
                # If we can't get roots, fall back to current directory
                pass

        # Use provided working directory or current directory
        cwd = working_directory if working_directory else os.getcwd()

        # Debug output
        debug_info = {
            "provided_working_directory": working_directory,
            "actual_cwd": cwd,
            "server_process_cwd": os.getcwd(),
            "server_file_location": str(Path(__file__).parent),
            "roots_check": None
        }

        # Add roots debug info
        try:
            context = mcp.get_context()
            roots_result = await context.session.list_roots()
            debug_info["roots_check"] = {
                "found": True,
                "count": len(roots_result.roots),
                "roots": [str(root.uri) for root in roots_result.roots]
            }
        except Exception as e:
            debug_info["roots_check"] = {
                "found": False,
                "error": str(e)
            }

        # Get list of changed files
        files_result = subprocess.run(
            ["git", "diff", "--name-status", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd
        )

        # Get diff statistics
        stat_result = subprocess.run(
            ["git", "diff", "--stat", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd
        )

        # Get the actual diff if requested
        diff_content = ""
        truncated = False
        if include_diff:
            diff_result = subprocess.run(
                ["git", "diff", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True,
                cwd=cwd
            )
            diff_lines = diff_result.stdout.split('\n')

            # Check if we need to truncate
            if len(diff_lines) > max_diff_lines:
                diff_content = '\n'.join(diff_lines[:max_diff_lines])
                diff_content += f"\n\n... Output truncated. Showing {max_diff_lines} of {len(diff_lines)} lines ..."
                diff_content += "\n... Use max_diff_lines parameter to see more ..."
                truncated = True
            else:
                diff_content = diff_result.stdout

        # Get commit messages for context
        commits_result = subprocess.run(
            ["git", "log", "--oneline", f"{base_branch}..HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd
        )

        analysis = {
            "base_branch": base_branch,
            "files_changed": files_result.stdout,
            "statistics": stat_result.stdout,
            "commits": commits_result.stdout,
            "diff": diff_content if include_diff else "Diff not included (set include_diff=true to see full diff)",
            "truncated": truncated,
            "total_diff_lines": len(diff_lines) if include_diff else 0,
            "_debug": debug_info
        }

        return json.dumps(analysis, indent=2)

    except subprocess.CalledProcessError as e:
        return json.dumps({"error": f"Git error: {e.stderr}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""

    try:
        templates = [  # Example output structure:]
            {
                "filename": template_name,
                "type": template_type,
                "content": (TEMPLATES_DIR / template_name).read_text()
            }
            for template_name, template_type in DEFAULT_TEMPLATES.items()
        ]
        return json.dumps(templates, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let Claude analyze the changes and suggest the most appropriate PR template.

    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    try:
        # Get available templates
        templates_response = await get_pr_templates()
        templates = json.loads(templates_response)

        # mapping template with change_type
        template_type = TYPE_MAPPING.get(change_type.lower(), "feature.md")
        template_with_relative_type = templates.get(template_type, "").lower()
        for template in templates:
            if template["filename"] == template_type:
                relative_template = template
                break
            else:
                # Default to first template if not found
                relative_template = templates[0]
        suggestion = {
            "recommended_template": relative_template,
            "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
            "template_content": relative_template["content"],
            "suggestion": "Claude can help you fill out this template based on the specific changes in your PR."
        }

    except Exception as e:
        suggestion = {
            "recommended_template": f"recommended_template {e}",
            "reasoning": f"Based on your analysis: changes_summary, this appears to be a {e} change.",
            "template_content": f"template_content {e}",
            "suggestion": f"Claude can help you fill out this template based on the specific changes in your PR. {e}"
        }
        return json.dumps(suggestion, indent=2)

    return json.dumps(suggestion, indent=2)


if __name__ == "__main__":
    mcp.run()
