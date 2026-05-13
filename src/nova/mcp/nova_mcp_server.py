#!/usr/bin/env python3
"""Nova MCP Server — exposes Nova tools via Model Context Protocol (stdio)."""
import sys
import json
import os
import logging
import traceback

# Must add src/ to path before importing nova modules
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "..", "..")
sys.path.insert(0, _SRC)

# Load .env
try:
    from dotenv import load_dotenv
    _env = os.path.join(_SRC, "..", ".env")
    if os.path.exists(_env):
        load_dotenv(_env)
except Exception:
    pass

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

_router = None

def _get_router():
    global _router
    if _router is None:
        try:
            from nova.core.nova_router import NovaRouter
            from nova.tools.nova_skills import skills
            _router = NovaRouter()
            skills.set_router(_router)
        except Exception as e:
            log.error(f"Failed to init Nova router: {e}")
    return _router

def _get_tool_list():
    tools = []
    
    # Always provide ask_nova
    tools.append({
        "name": "ask_nova",
        "description": "Ask Nova anything in natural language. Returns Nova's response.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Question or command for Nova"}
            },
            "required": ["query"]
        }
    })
    
    try:
        from nova.tools.nova_skills import _TOOL_CATALOG
        from nova.tools.nova_tools_schemas import get_tool_schemas
        
        # We can also dynamically expose all catalog tools
        schemas = get_tool_schemas()
        for t in schemas:
            # get_tool_schemas might return openai-style functions. Convert to MCP:
            # openai: {"type": "function", "function": {"name": "...", "description": "...", "parameters": {...}}}
            if t.get("type") == "function":
                func = t["function"]
                tools.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "inputSchema": func.get("parameters", {"type": "object", "properties": {}})
                })
    except Exception as e:
        log.warning(f"Could not load tool catalog: {e}")
        
    return tools

def handle_initialize(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "nova-mcp",
                "version": "3.10"
            }
        }
    }

def handle_tools_list(msg_id):
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "tools": _get_tool_list()
        }
    }

def handle_tools_call(msg_id, params):
    name = params.get("name")
    args = params.get("arguments", {})
    
    result_text = ""
    
    try:
        if name == "ask_nova":
            router = _get_router()
            if router:
                query = args.get("query", "")
                resp = router.route([{"role": "user", "content": query}])
                result_text = resp.get("response", "No response.")
            else:
                result_text = "Error: Nova Router not available."
        else:
            from nova.tools.nova_skills import execute_tool
            # execute_tool returns dict with {"output": ...} or throws
            res = execute_tool(name, args)
            result_text = res.get("output", str(res))
    except Exception as e:
        log.error(f"Error executing {name}: {traceback.format_exc()}")
        result_text = f"Error: {str(e)}"
        
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "content": [
                {"type": "text", "text": str(result_text)}
            ]
        }
    }

def process_message(line):
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        log.warning("Invalid JSON received")
        return None
        
    method = msg.get("method")
    msg_id = msg.get("id")
    
    if method == "initialize":
        return handle_initialize(msg_id)
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return handle_tools_list(msg_id)
    elif method == "tools/call":
        return handle_tools_call(msg_id, msg.get("params", {}))
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    elif msg_id is not None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        }
    return None

def main():
    log.info("Starting Nova MCP Server on stdio...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
            
        response = process_message(line)
        if response:
            try:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except Exception as e:
                log.error(f"Failed to write response: {e}")

if __name__ == "__main__":
    main()
