import logging
from typing import Optional

from ghidra.app.emulator import EmulatorHelper
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.listing import Instruction

logger = logging.getLogger(__name__)


def emulate_instruction_slice(
    program,
    start_address,
    instruction_count: int,
    initial_registers: dict[str, int],
    track_registers: Optional[list[str]] = None,
) -> dict:
    """Step through *instruction_count* instructions from *start_address*
    using Ghidra's headless P-code emulator.

    Parameters
    ----------
    program : Ghidra Program
    start_address : Ghidra Address
    instruction_count : int
    initial_registers : dict
        e.g. {"r0": 5, "r1": 0x41424344, "pc": 0x1000}
    track_registers : list[str] or None
        Subset of registers to log after each step.  If None, all
        initialised registers are tracked plus the program counter.

    Returns
    -------
    dict with keys:
        success        : bool
        steps          : list of step records
        final_registers : dict of last-seen register values
        error          : str if a step failed
    """
    emu = EmulatorHelper(program)
    monitor = ConsoleTaskMonitor()
    addr_factory = program.getAddressFactory()

    # ── Seed initial register state ──────────────────────────────────
    for reg_name, reg_val in initial_registers.items():
        try:
            emu.writeRegister(reg_name.upper(), reg_val)
        except Exception as exc:
            emu.dispose()
            raise ValueError(
                f"Cannot write register '{reg_name}': {exc}"
            ) from exc

    # Determine which registers to log at each step
    if track_registers is None:
        tracked = set(k.upper() for k in initial_registers)
        tracked.add("PC")
    else:
        tracked = set(r.upper() for r in track_registers)

    # ── Step loop ────────────────────────────────────────────────────
    steps = []
    current_addr = start_address
    error = None

    for step_index in range(instruction_count):
        pc_offset = emu.readRegister("PC")
        pc_addr = addr_factory.getAddress(pc_offset)

        # Fetch the instruction about to execute
        cu = program.getListing().getCodeUnitAt(pc_addr)
        if cu is None or not isinstance(cu, Instruction):
            steps.append({
                "step": step_index,
                "address": str(pc_addr),
                "instruction": "<not-an-instruction>",
                "error": "Hit non-instruction memory — stopping",
            })
            break

        instr_str = f"{cu.getMnemonicString()} {cu.getDefaultOperandRepresentation()}"

        # Single-step
        ok = emu.step(monitor)
        if not ok:
            error = emu.getLastError()
            steps.append({
                "step": step_index,
                "address": str(pc_addr),
                "instruction": instr_str,
                "error": error,
            })
            break

        # Snapshot tracked registers
        reg_snapshot = {}
        for reg in tracked:
            try:
                reg_snapshot[reg.lower()] = emu.readRegister(reg)
            except Exception:
                pass

        steps.append({
            "step": step_index,
            "address": str(pc_addr),
            "instruction": instr_str,
            "registers": reg_snapshot,
        })

    # ── Final register state ─────────────────────────────────────────
    final_regs = {}
    for reg in tracked:
        try:
            final_regs[reg.lower()] = emu.readRegister(reg)
        except Exception:
            pass

    emu.dispose()

    return {
        "success": error is None,
        "steps": steps,
        "final_registers": final_regs,
        "error": error,
    }
