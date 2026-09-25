"""What this computer is made of, and which local models it can actually run.

scan() is what the crab "sees" through his magnifying glass; rank() turns it
into the list he reads out afterwards, best pick first.
"""

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass

from brain import total_ram_gb

CPU_CLASS_ID = "{4d36e968-e325-11ce-bfc1-08002be10318}"  # display adapters, in the registry
PROBE_TIMEOUT_S = 8


@dataclass(frozen=True)
class Specs:
    ram_gb: float
    cores: int
    gpu: str            # "" when he couldn't find one
    vram_gb: float      # 0 when unknown / integrated
    os_label: str

    @property
    def budget_gb(self):
        """Roughly how much a model may weigh here. A real GPU runs it; otherwise
        it lives in RAM next to everything else the user has open."""
        return self.vram_gb if self.vram_gb >= 4 else self.ram_gb * 0.45

    def summary(self):
        gpu = f"{self.gpu}{f' · {self.vram_gb:.0f} GB VRAM' if self.vram_gb else ''}" if self.gpu else "no GPU found"
        return f"{self.ram_gb:.0f} GB RAM · {self.cores} cores · {gpu}"


def windows_gpu():
    """(name, VRAM GB). Win32_VideoController.AdapterRAM caps out at 4 GB, so the
    real size comes from the driver's registry key."""
    script = (
        "$g = Get-CimInstance Win32_VideoController | Sort-Object AdapterRAM -Descending | Select-Object -First 1;"
        f"$v = Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{CPU_CLASS_ID}\\*'"
        " -Name 'HardwareInformation.qwMemorySize' -ErrorAction SilentlyContinue |"
        " ForEach-Object { $_.'HardwareInformation.qwMemorySize' } | Sort-Object -Descending | Select-Object -First 1;"
        "if (-not $v) { $v = $g.AdapterRAM };"
        "@{ name = $g.Name; vram = [double]$v } | ConvertTo-Json -Compress"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=PROBE_TIMEOUT_S,
                         creationflags=subprocess.CREATE_NO_WINDOW)
    data = json.loads(out.stdout or "{}")
    return (data.get("name") or "").strip(), (data.get("vram") or 0) / 2**30


def scan():
    """Everything he needs to judge this machine. Never raises: unknown parts come
    back empty and rank() just leans on RAM."""
    ram = total_ram_gb()
    cores = os.cpu_count() or 4
    gpu, vram = "", 0.0
    try:
        if sys.platform == "win32":
            gpu, vram = windows_gpu()
        elif sys.platform == "darwin" and platform.machine() == "arm64":
            # Apple Silicon shares one pool of memory with the GPU.
            gpu, vram = f"Apple Silicon ({platform.machine()})", ram * 0.6
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return Specs(ram, cores, gpu, vram, f"{platform.system()} {platform.release()}")


# Models he knows how to pull, biggest first. Sizes are the Ollama download sizes.
# ponytail: a hand-kept list, not a live query of the registry. If a tag ever goes
# away the pull just errors and he says so; add new ones here.
CATALOG = [
    ("qwen3.5:4b", 3.4, "Sharpest of the three. Uses tools properly, so he fetches files on his own."),
    ("qwen3.5:2b", 2.7, "Good middle ground. Still picks his own tools, just a bit simpler."),
    ("qwen3:1.7b", 1.4, "Tiny and quick. Keywords pick the actions, the model does the chatting."),
]
HEADROOM = 1.35  # a model needs about a third again its own size while it's running


@dataclass(frozen=True)
class Pick:
    model: str
    size_gb: float
    blurb: str
    verdict: str
    fits: bool


def rank(specs):
    """The list he reads out: what fits, what's best, what's too much for this box."""
    budget = specs.budget_gb
    picks, best_found = [], False
    for model, size, blurb in CATALOG:
        fits = size * HEADROOM <= budget
        if fits and not best_found:
            best_found, verdict = True, "★ Best pick for this rig"
        elif fits:
            verdict = "Runs fast, a bit simpler" if size * 2.2 <= budget else "Runs fine"
        else:
            verdict = f"Too big — needs about {size * HEADROOM:.1f} GB free"
        picks.append(Pick(model, size, blurb, verdict, fits))
    if not best_found:  # tiny machine: the smallest one is still his best shot
        last = picks[-1]
        picks[-1] = Pick(last.model, last.size_gb, last.blurb, "★ Best shot, but it'll be slow", True)
    return picks


def demo():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # the verdicts have a ★ in them
    specs = scan()
    print(specs.summary(), f"-> budget {specs.budget_gb:.1f} GB")
    for pick in rank(specs):
        print(f"  {'y' if pick.fits else 'n'} {pick.model:14} {pick.size_gb:>4.1f} GB  {pick.verdict}")
    assert specs.ram_gb > 0 and specs.cores >= 1
    assert sum(p.verdict.startswith("★") for p in rank(specs)) == 1, "exactly one best pick"


if __name__ == "__main__":
    demo()
