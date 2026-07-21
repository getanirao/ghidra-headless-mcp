# Ghidra Headless MCP

MCP (Model Context Protocol) server that exposes Ghidra's headless analysis capabilities to AI assistants via [pyhidra](https://github.com/dod-cyber-crime-institute/pyhidra).

## Security Model

This server communicates **exclusively over standard process stdio** — there is no HTTP socket, no TCP listener, and no network interface exposed. It is inherently immune to LAN/WAN exposure, SSRF, and unauthenticated API attacks. The only way to interact with it is for an MCP client to launch it as a subprocess and communicate via stdin/stdout.

## Prerequisites

- Python 3.10+
- Ghidra 11.x+ installed
- Java 17+ (required by Ghidra)

## Setup

```bash
# Install the package
pip install -e .

# Or install dependencies directly
pip install mcp pyhidra
```

## Usage

Set `GHIDRA_INSTALL_DIR` or pass `--ghidra-dir`:

```bash
# Windows
set GHIDRA_INSTALL_DIR=C:\path\to\ghidra
ghidra-mcp

# Linux/macOS
export GHIDRA_INSTALL_DIR=/opt/ghidra
ghidra-mcp
```

The server runs on stdio transport — configure it as an MCP server in your AI client:

### Claude Desktop config (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "ghidra-headless": {
      "command": "ghidra-mcp",
      "args": ["--ghidra-dir", "C:\\path\\to\\ghidra"],
      "env": {}
    }
  }
}
```

## Tools

### Read/Analysis tools

#### `analyze_binary`

Import a binary into a new Ghidra project with auto-analysis. Returns metadata. Subsequent tools operate on this binary until a new one is loaded.

**Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `binary_path` | string | yes | Path to the binary file |
| `project_dir` | string | no | Project directory (defaults to binary's parent) |

#### `decompile_function`

Decompile a single function to C code.

**Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `function_name` | string | yes | Function name (e.g. `main`) or hex address (e.g. `0x401000`) |

#### `get_data_types`

List all data types defined in the loaded program.

#### `get_cross_references`

Get cross-references to and from an address.

**Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `address` | string | yes | Address to query (e.g. `0x401000`) |
| `max_results` | integer | no | Max references per direction (default: 100) |

#### `get_call_graph`

Get the call graph for a function — who it calls (recursively) and who calls it.

**Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `function_name` | string | yes | Function name or address |
| `max_depth` | integer | no | Recursion depth for callees (default: 3) |

### Write/Mutation tools

#### `rename_symbol`

Rename a function or label at a given address. Changes are stored in the Ghidra project database.

**Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `address` | string | yes | Address of the symbol (e.g. `0x401000`) |
| `new_name` | string | yes | New name for the symbol |

#### `add_comment`

Attach a comment to a code unit at a given address. Comment types control where and how the comment is displayed in the Ghidra UI.

**Parameters:**
| Param | Type | Required | Description |
|---|---|---|---|
| `address` | string | yes | Address to comment on (e.g. `0x401000`) |
| `text` | string | yes | Comment body text |
| `comment_type` | string | no | `plate` (banner), `pre`, `post`, `eol`, or `repeatable` (default: `plate`) |

### Batch/Composite tools

#### `analyze_and_decompile_entrypoints`

Bulk decompilation of all entry points in one call — combines the program entry, exports, and known conventions (`main`, `WinMain`, `_start`, `entry`, `DllMain`, `DriverEntry`). Prevents AI tool-call bloat by avoiding N sequential `decompile_function` requests.

**Parameters:** None.

## Project Structure

```
ghidra-headless-mcp/
├── pyproject.toml
├── README.md
└── src/ghidra_headless_mcp/
    ├── __init__.py
    ├── server.py          # MCP server, tool registry, stdio transport
    ├── ghidra_bridge.py   # GhidraSession — pyhidra wrapper
    └── tools/
        └── __init__.py
```

## How it works

1. `pyhidra.start()` boots Ghidra's JVM once at server startup
2. `analyze_binary` creates a temporary Ghidra project and opens the binary
3. All subsequent tools operate on the currently loaded program via Ghidra's Java API (accessed through JPype)
4. Write tools (`rename_symbol`, `add_comment`) apply changes directly to the program database
5. Calling `analyze_binary` again closes the previous program and loads a new one
