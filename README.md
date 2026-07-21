# Ghidra Headless MCP

MCP (Model Context Protocol) server that exposes Ghidra's headless analysis capabilities to AI assistants via [pyhidra](https://github.com/dod-cyber-crime-institute/pyhidra).

## Security Model

This server communicates **exclusively over standard process stdio** — there is no HTTP socket, no TCP listener, and no network interface exposed. It is inherently immune to LAN/WAN exposure, SSRF, and unauthenticated API attacks. The only way to interact with it is for an MCP client to launch it as a subprocess and communicate via stdin/stdout.

## Quick Start

### Local

```bash
pip install -e .
set GHIDRA_INSTALL_DIR=C:\path\to\ghidra   # Windows
ghidra-mcp
```

### Docker

```bash
docker build -t ghidra-headless-mcp .
docker run -i --rm -v /path/to/binaries:/data ghidra-headless-mcp
```

The container bundles JDK 17, Ghidra 11.2, and the server — no host dependencies beyond Docker.

## Claude Desktop config

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

### Session management

| Tool | Description |
|---|---|
| `analyze_binary` | Import + analyze a binary, returns a `session_id`. Reuses the ID if provided, otherwise auto-generates. |
| `list_sessions` | List all active workspaces with their session IDs, binary paths, and load times. |
| `close_session` | Close a session and free its Ghidra project resources. |

Most tools accept an optional `session_id` parameter — omit it to use the most recently loaded session.

### Read / Analysis

| Tool | Description |
|---|---|
| `decompile_function` | Decompile a function by name or address. |
| `decompile_function_paginated` | Decompile with `line_start`, `line_end`, `max_tokens` (token-budget truncation), and `summarize` (strips boilerplate locals + collapsing blank lines). Prevents context-window exhaustion. |
| `get_data_types` | List all data types defined in the program. |
| `get_cross_references` | Cross-references to/from an address. |
| `get_call_graph` | Recursive call graph + callers for a function. |
| `analyze_and_decompile_entrypoints` | Composite — bulk decompile all entry points (program entry, exports, `main`, `_start`, etc.) in one call. |

### Write / Mutation

| Tool | Description |
|---|---|
| `rename_symbol` | Rename a function or label. Stored in the Ghidra project DB. |
| `add_comment` | Attach a comment (`plate`, `pre`, `post`, `eol`, `repeatable`). |
| `create_struct` | Create a custom structured data type from a JSON member layout `[{offset, name, type}, ...]`. Offsets are optional. |
| `retype_variable` | Re-type a local variable or function parameter (e.g. `undefined4*` → `MyStruct*`). |

### Assembly-level

| Tool | Description |
|---|---|
| `disassemble_range` | Disassemble N raw instructions at an address — returns mnemonic, operands, hex bytes, and length for precise lower-level inspection. |

### Binary diffing

| Tool | Description |
|---|---|
| `diff_binaries` | Compare two loaded sessions by function name and body size. Returns functions unique to each side and changed functions. |

## Workspace Sessions

Each `analyze_binary` call creates a named session. Sessions keep their Ghidra project open independently, so multiple binaries can be loaded concurrently:

```python
# Load two binaries into separate sessions
s1 = analyze_binary(binary_path="/bin/a.out")        # auto session_id
s2 = analyze_binary(binary_path="/bin/b.out", session_id="my_session")

# Operate on a specific session
decompile_function(function_name="main", session_id=s1.session_id)

# Diff them
diff_binaries(session_a=s1.session_id, session_b="my_session")
```

## Deployment

### Docker (multi-user / CI)

```bash
docker build -t ghidra-headless-mcp .

# Run as an MCP subprocess
docker run -i --rm \
  -v /data/binaries:/data \
  ghidra-headless-mcp \
  --ghidra-dir /opt/ghidra
```

The `Dockerfile` bundles Ghidra 11.2 and JDK 17 in a slim Python 3.11 image. Bind-mount your binaries directory at runtime.

### P-code micro-emulation

| Tool | Description |
|---|---|
| `emulate_slice` | Headlessly execute N instructions from an address using Ghidra's `EmulatorHelper`. Seed register state (e.g. `{"r0": 5, "r1": 0x41424344}`) and get a step-by-step trace of register mutations. Works on any Ghidra-supported architecture (ARM, x86, MIPS, etc.) — no GDB/LLDB, no network ports, no debugger stubs. |

**Example — trace ARM register propagation:**

```python
emulate_slice(
    start_address="0x1000",
    instruction_count=5,
    initial_registers={"r0": 0xDEADBEEF, "r1": 0, "pc": 0x1000},
)
# Returns step array with register snapshots after each instruction
```

### Function fingerprinting / signature transfer

| Tool | Description |
|---|---|
| `calculate_function_fingerprint` | Generate a structural hash for a function (vars, params, body size, branches, called funcs, embedded strings, numeric constants). Survives compiler reordering. |
| `export_signature_map` | Build a complete `{hash → name}` map for every function in the current binary. Save this JSON to reuse across versions. |
| `apply_signature_map` | Pass a previously exported signature map; the server sweeps the binary and renames every matching function automatically. |

**Typical workflow — patch diff across versions:**

```python
# 1. Analyze old binary and export its signature map
s1 = analyze_binary(binary_path="/bin/v1.bin")
old_map = export_signature_map(session_id=s1.session_id)

# 2. Analyze new binary and apply the map
s2 = analyze_binary(binary_path="/bin/v2.bin")
result = apply_signature_map(
    signature_json_map=old_map["signature_map"],
    session_id=s2.session_id,
)
# result.matched = 142  — 142 functions renamed automatically
```

## Project Structure

```
ghidra-headless-mcp/
├── Dockerfile
├── pyproject.toml
├── README.md
└── src/ghidra_headless_mcp/
    ├── __init__.py
    ├── server.py          # MCP server, tool registry, stdio transport
    ├── ghidra_bridge.py   # GhidraSession — pyhidra wrapper, all tool logic
    └── tools/
        └── __init__.py
```

## How it works

1. `pyhidra.start()` boots Ghidra's JVM once at server startup
2. Each `analyze_binary` call opens a new Ghidra project in its own named session
3. Read/write tools route to the requested session via `session_id` (or the active default)
4. Write tools apply changes directly to the Ghidra program database
5. Sessions persist until explicitly closed — enabling multi-binary workflows and diffing
