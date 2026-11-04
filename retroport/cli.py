"""Command-line interface.

    retroport scan <dir> [--report] [--skel-only]   inventory / readiness / find .skel models
    retroport inspect <file>                         full classification of one file
    retroport deps <m2>                              list a model's .skel/.anim/.bone deps
    retroport reinline <m2> --out <dir> [--json]     re-inline a .skel model (Milestones A+B)
    retroport check <md20> [--json]                  WotLK render-blocker diagnostics on converted output
    retroport bake <md20> --slot N=path [--json]     bake in-game texture paths into type-0 slots
    retroport repair <md20> --source-m2 <m2>         restore data MultiConverter overwrote at 0x130
    retroport register --dbc-dir --out --path        add CreatureModelData/DisplayInfo rows + SQL
    retroport register-item --dbc-dir --out ...      add an ItemDisplayInfo row (+ Item.dbc repoint) + SQL
    retroport textures <blp|dir>... --out --target   resize armor/object textures for 3.3.5
    retroport helms <helm_x_hum.m2> --out ...        convert every 3.3.5 race/gender variant of a helm
    retroport character --bfa|--retail ... --race --sex   port a BfA/retail playable race (model, textures, rows)
    retroport race <Race> --bfa|--retail --client --out   make it playable: DBCs, create screen, server DBCs + SQL
    retroport glue --bfa --client --out              character create laid out as BfA's, for every race
    retroport install <package> --client [--apply]   install it without overwriting your customizations

Designed to run today against any folder. Point it at a wow.export extraction
to get a real asset inventory and a list of what still needs conversion.
"""

from __future__ import annotations

import json
import os
import sys

# Windows consoles default to cp1252 and raise UnicodeEncodeError on non-ASCII output
# (e.g. a texture path with an odd byte). Prefer UTF-8 where the runtime allows it.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")   # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass
from collections import Counter

import typer
from rich.console import Console
from rich.table import Table

from .models import AssetType, Severity
from .scan.scanner import classify_file
from .validate.rules import validate
from .convert.skel_reinliner import reinline_file
from .convert.loaders import make_file_id_loader, make_manifest_loader, find_manifest
from .check import check_model, format_report
from .bugreport import build_report
from .texreport import build_texture_report
from .report import write_reports

app = typer.Typer(add_completion=False, help="Retroport modern WoW assets to 3.3.5a.")
console = Console()

_SEV_STYLE = {Severity.PASS: "green", Severity.WARN: "yellow", Severity.FAIL: "red"}


def _walk(root: str):
    if os.path.isfile(root):
        yield root
        return
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            yield os.path.join(dirpath, name)


@app.command()
def scan(
    path: str = typer.Argument(..., help="File or directory to scan."),
    report: bool = typer.Option(False, "--report", help="Also run readiness validation."),
    json_out: str = typer.Option(None, "--json", help="Write the full AssetInfo list to JSON."),
    show_unknown: bool = typer.Option(False, "--unknown", help="Include UNKNOWN files in the type table."),
    skel_only: bool = typer.Option(False, "--skel-only", help="List only .skel-based models (re-inliner targets)."),
) -> None:
    if not os.path.exists(path):
        console.print(f"[red]Path not found:[/] {path}")
        console.print("[dim]In Git Bash, use forward slashes (I:/WoWDownPort/...) or quote backslash paths.[/]")
        raise typer.Exit(code=2)

    infos = [classify_file(p) for p in _walk(path)]
    if not infos:
        console.print(f"[yellow]No files found under[/] {path}")
        raise typer.Exit(code=0)

    if skel_only:
        skels = [i for i in infos if i.uses_skel or i.type is AssetType.SKEL]
        if not skels:
            console.print(f"[yellow]No .skel-based models found under[/] {path}")
            console.print("[dim]Characters and Shadowlands+ creatures are the usual cases.[/]")
            raise typer.Exit(code=0)
        t = Table(title=f".skel-based models  ({len(skels)})  — feed an m2 row to `retroport reinline`")
        t.add_column("path", overflow="fold"); t.add_column("type"); t.add_column("version", justify="right")
        for i in sorted(skels, key=lambda x: x.path):
            t.add_row(i.path, i.type.value, str(i.version) if i.version else "-")
        console.print(t)
        raise typer.Exit(code=0)


    # Type breakdown
    by_type = Counter(i.type.value for i in infos)
    t = Table(title=f"Asset inventory  ({len(infos)} files)")
    t.add_column("type"); t.add_column("count", justify="right")
    t.add_column("chunked M2", justify="right"); t.add_column("uses .skel", justify="right")
    for atype, count in by_type.most_common():
        if atype == AssetType.UNKNOWN.value and not show_unknown:
            continue
        same = [i for i in infos if i.type.value == atype]
        chunked = sum(1 for i in same if i.chunked)
        skel = sum(1 for i in same if i.uses_skel)
        t.add_row(atype, str(count), str(chunked) if chunked else "-", str(skel) if skel else "-")
    console.print(t)

    # Expansion breakdown (M2 only, where the version word means something)
    exps = Counter(i.expansion for i in infos if i.expansion)
    if exps:
        e = Table(title="M2 by expansion")
        e.add_column("expansion"); e.add_column("count", justify="right")
        for name, count in exps.most_common():
            e.add_row(name, str(count))
        console.print(e)

    # Readiness summary
    not_ready = [i for i in infos if i.type is not AssetType.UNKNOWN and not i.wotlk_ready]
    ready = sum(1 for i in infos if i.wotlk_ready)
    console.print(f"[green]{ready}[/] already WotLK-ready, "
                  f"[yellow]{len(not_ready)}[/] need conversion, "
                  f"[dim]{by_type.get('unknown', 0)} unknown[/]")

    if report and not_ready:
        r = Table(title="Conversion blockers")
        r.add_column("file", overflow="fold"); r.add_column("type"); r.add_column("findings")
        for i in not_ready[:200]:
            rep = validate(i)
            issues = ", ".join(
                f"[{_SEV_STYLE[f.severity]}]{f.check}[/]" for f in rep.findings
                if f.severity is not Severity.PASS
            )
            r.add_row(os.path.basename(i.path), i.type.value, issues or "-")
        console.print(r)
        if len(not_ready) > 200:
            console.print(f"[dim]... and {len(not_ready) - 200} more[/]")

    if json_out:
        with open(json_out, "w", encoding="utf-8") as fh:
            json.dump([i.model_dump() for i in infos], fh, indent=2)
        console.print(f"[dim]Wrote {json_out}[/]")


@app.command()
def inspect(path: str = typer.Argument(..., help="A single file to classify.")) -> None:
    if not os.path.isfile(path):
        console.print(f"[red]File not found:[/] {path}")
        console.print("[dim]In Git Bash, use forward slashes (I:/...) or quote backslash paths.[/]")
        raise typer.Exit(code=2)
    info = classify_file(path)
    console.print_json(info.model_dump_json(indent=2))
    rep = validate(info)
    console.print(f"\nReadiness: worst = [{_SEV_STYLE[rep.worst]}]{rep.worst.value}[/]")
    for f in rep.findings:
        console.print(f"  [{_SEV_STYLE[f.severity]}]{f.severity.value:4}[/] {f.check}: {f.detail}")


def _emit_json(command: str, ok: bool, result, error: str | None = None) -> None:
    """Stable JSON contract for programmatic callers (e.g. the Warcrafter UI)."""
    payload = {
        "ok": ok,
        "command": command,
        "error": error,
        "result": result.model_dump(mode="json") if result is not None else None,
    }
    print(json.dumps(payload, indent=2))


def _resolve_loaders(model: str, source: str, meta: str | None, no_anim: bool):
    """Pick the manifest loader (preferred) or the directory id-scan loader.
    Returns (skel_loader, anim_loader, description)."""
    meta = meta or find_manifest(model)
    if meta and os.path.isfile(meta):
        loader = make_manifest_loader(meta)        # resolves any FileDataID -> bytes
        anim_loader = None if no_anim else loader
        return loader, anim_loader, f"manifest {os.path.basename(meta)}"
    skel_loader = make_file_id_loader(source, ".skel")
    anim_loader = None if no_anim else make_file_id_loader(source, ".anim")
    return skel_loader, anim_loader, f"directory scan of {source}"


@app.command()
def reinline(
    model: str = typer.Argument(..., help="The modern .m2 (chunked, .skel-based) to convert."),
    source: str = typer.Option(".", "--source", help="Extraction root for the .skel/.anim files (fallback when no manifest)."),
    out: str = typer.Option(..., "--out", help="Directory to write the converted .m2 into."),
    meta: str = typer.Option(None, "--meta", help="wow.export manifest .json (auto-detected next to the model if omitted)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
    no_anim: bool = typer.Option(False, "--no-anim", help="Structural re-inline only (skip the animation pass)."),
) -> None:
    """Re-inline a .skel model into a self-contained M2 (Milestones A + B)."""
    if not os.path.isfile(model):
        if json_out:
            _emit_json("reinline", False, None, f"model not found: {model}")
        else:
            console.print(f"[red]Model not found:[/] {model}")
        raise typer.Exit(code=2)

    skel_loader, anim_loader, how = _resolve_loaders(model, source, meta, no_anim)
    cr = reinline_file(model, skel_loader, out, anim_loader=anim_loader)

    if json_out:
        _emit_json("reinline", cr.success, cr, cr.stderr)
        raise typer.Exit(code=0 if cr.success else 1)

    style = "green" if cr.success else "red"
    console.print(f"[{style}]{'OK' if cr.success else 'FAILED'}[/]  {os.path.basename(model)}  [dim]({how})[/]")
    if cr.output:
        console.print(f"  output: {cr.output}")
    if cr.stderr:
        console.print(f"  [red]{cr.stderr}[/]")
    if cr.report:
        for f in cr.report.findings:
            console.print(f"  [{_SEV_STYLE[f.severity]}]{f.severity.value:4}[/] {f.check}: {f.detail}")
    raise typer.Exit(code=0 if cr.success else 1)


@app.command()
def deps(
    model: str = typer.Argument(..., help="A .m2 whose dependency files you want to check."),
    meta: str = typer.Option(None, "--meta", help="wow.export manifest .json (auto-detected next to the model if omitted)."),
) -> None:
    """List a model's .skel/.anim/.bone dependencies and whether each is present."""
    if not os.path.isfile(model):
        console.print(f"[red]Model not found:[/] {model}")
        raise typer.Exit(code=2)

    manifest = meta or find_manifest(model)
    if not manifest or not os.path.isfile(manifest):
        console.print("[yellow]No manifest found next to the model.[/]")
        console.print("[dim]Re-export from wow.export with the .skel/.anim options on, or pass --meta.[/]")
        raise typer.Exit(code=1)

    with open(manifest, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    base = os.path.dirname(os.path.abspath(manifest))

    rows: list[tuple[str, dict]] = []
    if data.get("skeleton"):
        rows.append(("skel", data["skeleton"]))
    rows += [("anim", e) for e in data.get("skelAnims", [])]
    rows += [("bone", e) for e in data.get("skelBones", [])]

    t = Table(title=f"Dependencies for {os.path.basename(model)}  (manifest: {os.path.basename(manifest)})")
    t.add_column("kind"); t.add_column("fileDataID", justify="right")
    t.add_column("file", overflow="fold"); t.add_column("present", justify="center")
    present = 0
    for kind, e in rows:
        ok = os.path.isfile(os.path.join(base, e.get("file", "")))
        present += ok
        t.add_row(kind, str(e.get("fileDataID", "?")), e.get("file", "?"),
                  "[green]Y[/]" if ok else "[red]N[/]")
    console.print(t)
    missing = len(rows) - present
    style = "green" if missing == 0 else "yellow"
    console.print(f"[{style}]{present}/{len(rows)} present[/]"
                  + ("" if missing == 0 else f", [red]{missing} missing[/] — export the missing ids from wow.export"))
    if missing == 0:
        console.print("[dim]All dependencies present. Run: retroport reinline <model> --out <dir> --json[/]")


@app.command()
def check(
    model: str = typer.Argument(..., help="A converted (MD20) .m2 to check for WotLK compatibility."),
    skin_dir: str = typer.Option(None, "--skin-dir", help="Where the .skin files are (defaults to the model's folder)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Diagnose render blockers in a converted model: skin count, geosets, combiner flag, shaders, bones."""
    if not os.path.isfile(model):
        if json_out:
            _emit_json("check", False, None, f"model not found: {model}")
        else:
            console.print(f"[red]Model not found:[/] {model}")
        raise typer.Exit(code=2)

    try:
        res = check_model(model, skin_dir=skin_dir)
    except ValueError as exc:
        if json_out:
            _emit_json("check", False, None, str(exc))
        else:
            console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)

    if json_out:
        rep = res.report()
        ok = all(f.severity is not Severity.FAIL for f in rep.findings)
        _emit_json("check", ok, rep)
        raise typer.Exit(code=0 if ok else 1)

    console.print(f"[bold]{os.path.basename(model)}[/]")
    console.print(format_report(res))
    console.print()
    for f in res.report().findings:
        console.print(f"  [{_SEV_STYLE[f.severity]}]{f.severity.value:4}[/] {f.check}: {f.detail}")


@app.command()
def bugreport(
    model: str = typer.Argument(..., help="The model to report on (raw modern .m2 for WXL testing)."),
    error: str = typer.Option("", "--error", help="The WoWError text (inline)."),
    error_file: str = typer.Option("", "--error-file", help="Read the WoWError from a file."),
    skin_dir: str = typer.Option(None, "--skin-dir", help="Where the .skin files are (defaults to the model's folder)."),
    out: str = typer.Option("", "--out", help="Write the report to a file as well as printing it."),
) -> None:
    """Build a #Bug-Report-ready summary (check diagnosis + WoWError) for WarcraftXL testing."""
    if not os.path.isfile(model):
        console.print(f"[red]Model not found:[/] {model}")
        raise typer.Exit(code=2)
    err = error
    if error_file:
        try:
            with open(error_file, "r", encoding="utf-8", errors="replace") as fh:
                err = fh.read()
        except OSError as exc:
            console.print(f"[red]Could not read error file:[/] {exc}")
            raise typer.Exit(code=2)

    report = build_report(model, error_text=err, skin_dir=skin_dir)
    print(report)                      # plain print: report is markdown, not rich markup
    if out:
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(report + "\n")
            console.print(f"\n[green]Written:[/] {out}")
        except OSError as exc:
            console.print(f"[red]Could not write:[/] {exc}")
            raise typer.Exit(code=2)


@app.command()
def texreport(
    model: str = typer.Argument(..., help="The model whose textures to report on."),
    manifest: str = typer.Option(None, "--manifest", help="wow.export .manifest.json (auto-found next to the model if omitted)."),
    out: str = typer.Option("", "--out", help="Write the report to a file as well as printing it."),
) -> None:
    """Report which textures come from CharSections (runtime) vs the model (hardcoded)."""
    if not os.path.isfile(model):
        console.print(f"[red]Model not found:[/] {model}")
        raise typer.Exit(code=2)
    report = build_texture_report(model, manifest_path=manifest)
    print(report)                      # plain print: report is markdown, not rich markup
    if out:
        try:
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(report + "\n")
            console.print(f"\n[green]Written:[/] {out}")
        except OSError as exc:
            console.print(f"[red]Could not write:[/] {exc}")
            raise typer.Exit(code=2)


@app.command()
def report(
    model: str = typer.Argument(..., help="The model to report on."),
    out_dir: str = typer.Option("reports", "--out-dir", "-o", help="Folder to write reports into (a per-model subfolder is created)."),
    error: str = typer.Option("", "--error", help="WoWError text (inline) for the bug report."),
    error_file: str = typer.Option("", "--error-file", help="Read the WoWError from a file."),
    manifest: str = typer.Option(None, "--manifest", help="wow.export .manifest.json (auto-found next to the model if omitted)."),
    skin_dir: str = typer.Option(None, "--skin-dir", help="Where the .skin files are (defaults to the model's folder)."),
) -> None:
    """Write check + texture + bug reports for a model into one folder (for comparisons)."""
    if not os.path.isfile(model):
        console.print(f"[red]Model not found:[/] {model}")
        raise typer.Exit(code=2)
    err = error
    if error_file:
        try:
            with open(error_file, "r", encoding="utf-8", errors="replace") as fh:
                err = fh.read()
        except OSError as exc:
            console.print(f"[red]Could not read error file:[/] {exc}")
            raise typer.Exit(code=2)

    written = write_reports(model, out_dir, error_text=err, manifest_path=manifest, skin_dir=skin_dir)
    console.print(f"[green]Wrote {len(written)} file(s):[/]")
    for p in written:
        console.print(f"  {p}")
    console.print(f"\nCombined report: [bold]{written[0]}[/]")


def _parse_slots(slot: list[str]) -> dict[int, str]:
    out: dict[int, str] = {}
    for s in slot or []:
        idx, sep, path = s.partition("=")
        if not sep or not idx.strip().isdigit():
            raise typer.BadParameter(f"--slot expects N=In\\Game\\Path.blp, got '{s}'")
        out[int(idx)] = path.strip()
    return out


@app.command()
def bake(
    model: str = typer.Argument(..., help="A converted (MD20) .m2."),
    slot: list[str] = typer.Option(None, "--slot", help="N=In\\Game\\path.blp (repeatable); explicit paths win."),
    source_m2: str = typer.Option("", "--source-m2", help="The modern (MD21) .m2 it was converted from, for TXID auto-fill."),
    listfile: str = typer.Option("", "--listfile", help="Community listfile.csv, to resolve TXID FileDataIDs."),
    overrides: str = typer.Option("", "--overrides", help="Manual fdid;path fixes (win over the listfile)."),
    out: str = typer.Option("", "--out", help="Output folder (default: <model folder>/baked). Never the model's own folder."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Bake in-game texture paths into type-0 slots (auto-fill from TXID + listfile, and/or explicit)."""
    from .convert import texbake
    from .models import ConversionResult, Finding, ValidationReport
    from .safeio import same_dir

    def fail(msg: str, code: int = 2):
        if json_out:
            _emit_json("bake", False, None, msg)
        else:
            console.print(f"[red]{msg}[/]")
        raise typer.Exit(code=code)

    if not os.path.isfile(model):
        fail(f"model not found: {model}")
    out_dir = out or os.path.join(os.path.dirname(os.path.abspath(model)), "baked")
    if os.path.isdir(out_dir) and same_dir(out_dir, os.path.dirname(os.path.abspath(model))):
        fail("--out is the model's own folder; pick another so the input is never overwritten")
    with open(model, "rb") as fh:
        data = fh.read()
    if data[:4] != b"MD20":
        fail("texture baking needs an MD20 (converted) model; run MultiConverter first")

    txid = texbake.read_txid(source_m2) if source_m2 else []
    known = texbake.resolve_fdids(texbake.empty_slot_fdids(data, txid), listfile or None, overrides or None)
    plan = texbake.plan_bake(data, txid, known, _parse_slots(slot))
    findings = [Finding(check="unresolved", severity=Severity.WARN,
                        detail=f"slot {s}: FileDataID {f} not in the listfile") for s, f in plan.unresolved]
    findings += [Finding(check="no_txid", severity=Severity.WARN,
                         detail=f"slot {s}: empty type-0 slot with no TXID entry; pass --slot {s}=...")
                 for s in plan.no_id]
    if not plan.paths:
        fail("nothing to bake - pass --slot N=path, or --source-m2 + --listfile to auto-fill", code=1)

    out_path = os.path.join(out_dir, os.path.basename(model))
    try:
        texbake.bake_file(model, plan.paths, out_path)
    except ValueError as exc:
        fail(str(exc), code=1)
    findings = [Finding(check="baked", severity=Severity.PASS, detail=f"slot {s} -> {p}")
                for s, p in sorted(plan.paths.items())] + findings
    cr = ConversionResult(source=model, output=out_path, stage="texbake", success=True,
                          report=ValidationReport(asset=out_path, findings=findings))
    if json_out:
        _emit_json("bake", True, cr)
        raise typer.Exit(code=0)
    console.print(f"[green]Baked[/] {len(plan.paths)} slot(s) -> {out_path}")
    for f in findings:
        console.print(f"  [{_SEV_STYLE[f.severity]}]{f.severity.value:4}[/] {f.detail}")


@app.command()
def repair(
    model: str = typer.Argument(..., help="A converted (MD20) .m2."),
    source_m2: str = typer.Option(..., "--source-m2", help="The .m2 MultiConverter was given (for a model without "
                                  ".skel, the extracted original)."),
    out: str = typer.Option("", "--out", help="Output folder (default: <model folder>/repaired). Never the model's own folder."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Restore data MultiConverter overwrote with the combiner-combos header (global loops or the Stand animation)."""
    from .convert import fixup
    from .formats.verify import VerifyError, m2_problems, no_new_problems
    from .models import ConversionResult, Finding, ValidationReport
    from .safeio import same_dir, write_verified

    def fail(msg: str, code: int = 2):
        if json_out:
            _emit_json("repair", False, None, msg)
        else:
            console.print(f"[red]{msg}[/]")
        raise typer.Exit(code=code)

    for path in (model, source_m2):
        if not os.path.isfile(path):
            fail(f"not found: {path}")
    out_dir = out or os.path.join(os.path.dirname(os.path.abspath(model)), "repaired")
    if os.path.isdir(out_dir) and same_dir(out_dir, os.path.dirname(os.path.abspath(model))):
        fail("--out is the model's own folder; pick another so the input is never overwritten")
    with open(model, "rb") as fh:
        data = fh.read()
    if data[:4] != b"MD20":
        fail("repair needs an MD20 (converted) model")
    with open(source_m2, "rb") as fh:
        original = fh.read()

    out_path = os.path.join(out_dir, os.path.basename(model))
    created_dir = not os.path.isdir(out_dir)

    def discard():
        os.remove(out_path)
        if created_dir:
            os.rmdir(out_dir)

    write_verified(out_path, data, no_new_problems(data, m2_problems))
    try:
        repaired = fixup.repair_combiner_header(out_path, original)
    except (ValueError, VerifyError) as exc:
        discard()
        fail(str(exc), code=1)
    if not repaired:
        discard()
        if json_out:
            _emit_json("repair", True, None)
        else:
            console.print("[green]Nothing to repair[/]: no model data starts inside the combiner-combos header field.")
        raise typer.Exit(code=0)

    findings = [Finding(check="repaired", severity=Severity.PASS,
                        detail=f"restored {name} from {os.path.basename(source_m2)}") for name in repaired]
    cr = ConversionResult(source=model, output=out_path, stage="repair", success=True,
                          report=ValidationReport(asset=out_path, findings=findings))
    if json_out:
        _emit_json("repair", True, cr)
        raise typer.Exit(code=0)
    console.print(f"[green]Repaired[/] {', '.join(repaired)} -> {out_path}")


@app.command()
def register(
    dbc_dir: str = typer.Option(..., "--dbc-dir", help="Folder with the extracted 3.3.5a CreatureModelData/DisplayInfo.dbc."),
    out: str = typer.Option(..., "--out", help="Folder for the patched DBCs (must differ from --dbc-dir)."),
    path: str = typer.Option(..., "--path", help="In-game model path, e.g. Creature\\Foo\\foo.m2."),
    m2: str = typer.Option("", "--m2", help="The converted .m2, to fill CreatureModelData's GeoBox from its bounds."),
    scale: float = typer.Option(1.0, "--scale"),
    display_floor: int = typer.Option(0, "--display-floor", help="First DisplayID to try (0 = max+1)."),
    model_floor: int = typer.Option(0, "--model-floor", help="First ModelData ID to try (0 = max+1)."),
    texvar: str = typer.Option("", "--texvar", help="TextureVariation1,2,3 as bare names (for type 11/12/13 slots)."),
    geoset: int = typer.Option(0, "--geoset", help="CreatureGeosetData."),
    entries: str = typer.Option("", "--entries", help="Creature entries to repoint (comma-separated) - adds the full SQL block."),
    search: str = typer.Option("", "--search", help="Creature name to include a name-search query for."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Append CreatureModelData + CreatureDisplayInfo rows for a converted model, and print the SQL."""
    from .dbc import register_creature_model
    from .formats.md20 import read_bounds
    from .formats.verify import m2_data_block
    from .sql import SQLInputError

    tv = [t.strip() for t in texvar.split(",")] if texvar else []
    tv = (tv + ["", "", ""])[:3]
    bounds = None
    try:
        if m2:
            with open(m2, "rb") as fh:
                bounds = read_bounds(m2_data_block(fh.read()))
        r = register_creature_model(dbc_dir, out, path, scale,
                                    display_floor=display_floor or None, modeldata_floor=model_floor or None,
                                    texture_variations=tuple(tv), geoset_data=geoset, bounds=bounds,
                                    creature_entries=entries, search_term=search)
    except (OSError, ValueError, SQLInputError) as exc:
        if json_out:
            _emit_json("register", False, None, str(exc))
        else:
            console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    if json_out:
        _emit_json("register", True, r)
        raise typer.Exit(code=0)
    console.print(f"[green]DisplayID {r.display_id}[/] -> ModelData {r.model_id} -> {r.model_name}")
    console.print(f"  {r.model_dbc}\n  {r.display_dbc}")
    console.print("[dim]Put BOTH DBCs in the client patch (DBFilesClient\\) AND the server's dbc\\ folder.[/]\n")
    console.print(r.sql, markup=False, highlight=False)


@app.command("register-item")
def register_item(
    dbc_dir: str = typer.Option(..., "--dbc-dir", help="Folder with the 3.3.5a ItemDisplayInfo.dbc (and Item.dbc)."),
    out: str = typer.Option(..., "--out", help="Folder for the patched DBCs (must differ from --dbc-dir)."),
    like_display: int = typer.Option(None, "--like-display", help="Clone this existing DisplayID (sound, flags...) and override."),
    from_model: str = typer.Option("", "--from-model", help="Converted .m2: prefills --model and --texture (type-2 slot)."),
    model: str = typer.Option(None, "--model", help="Model filename, e.g. Axe_2H_Foo.mdx."),
    model_right: str = typer.Option(None, "--model-right", help="Right model (shoulders)."),
    texture: str = typer.Option(None, "--texture", help="ModelTexture: bare .blp name in the model's folder."),
    texture_right: str = typer.Option(None, "--texture-right"),
    icon: str = typer.Option(None, "--icon", help="Inventory icon name, e.g. INV_Axe_04."),
    component: list[str] = typer.Option(None, "--component", help="Section=name body texture (repeatable), e.g. TorsoUpper=Foo_Chest_TU."),
    geosets: str = typer.Option("", "--geosets", help="GeosetGroup 1,2,3."),
    flags: int = typer.Option(None, "--flags"),
    spell_visual: int = typer.Option(None, "--spell-visual"),
    sound_group: int = typer.Option(None, "--sound-group", help="GroupSoundIndex (cloned from --like-display if omitted)."),
    item_visual: int = typer.Option(None, "--item-visual", help="ItemVisual (enchant-style glow)."),
    display_floor: int = typer.Option(0, "--display-floor", help="First DisplayID to try (0 = max+1)."),
    entries: str = typer.Option("", "--entries", help="item_template entries to repoint (comma-separated)."),
    item_like: int = typer.Option(None, "--item-like", help="Existing item entry whose Item.dbc row new entries copy."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Add an ItemDisplayInfo row for a converted weapon/armor model (and repoint Item.dbc + SQL)."""
    from .itemdbc import register_item_display, suggest_from_model
    from .sql import SQLInputError

    try:
        if from_model:
            hint = suggest_from_model(from_model)
            model = model if model is not None else hint["model"]
            texture = texture if texture is not None else (hint["texture"] or None)
        comps = {}
        for c in component or []:
            k, sep, v = c.partition("=")
            if not sep:
                raise typer.BadParameter(f"--component expects Section=name, got '{c}'")
            comps[k.strip()] = v.strip()
        geo = tuple(int(g) for g in geosets.split(",")) if geosets else None
        r = register_item_display(
            dbc_dir, out, template_display_id=like_display, model=model, model_right=model_right,
            texture=texture, texture_right=texture_right, icon=icon, component_textures=comps or None,
            geoset_groups=geo, flags=flags, spell_visual=spell_visual, sound_group=sound_group,
            item_visual=item_visual, display_floor=display_floor or None,
            item_entries=entries, item_like=item_like)
    except (OSError, ValueError, SQLInputError) as exc:
        if json_out:
            _emit_json("register-item", False, None, str(exc))
        else:
            console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    if json_out:
        _emit_json("register-item", True, r)
        raise typer.Exit(code=0)
    console.print(f"[green]ItemDisplayInfo {r.display_id}[/]  {r.row}")
    for label, ids in (("Item.dbc repointed", r.items_updated), ("Item.dbc added", r.items_added),
                       ("[yellow]not in Item.dbc[/]", r.items_missing)):
        if ids:
            console.print(f"  {label}: {', '.join(map(str, ids))}")
    console.print("\nPack into the patch MPQ:")
    for p in r.pack:
        console.print(f"  {p}", markup=False, highlight=False)
    console.print()
    console.print(r.sql, markup=False, highlight=False)


@app.command()
def textures(
    paths: list[str] = typer.Argument(..., help=".blp files and/or folders of .blp files."),
    out: str = typer.Option(..., "--out", help="Output root (components go to Item\\TextureComponents\\<Section>Texture\\)."),
    target: str = typer.Option("classic", "--target", help="Client character models: classic (256 skin) or hd (512 skin)."),
    max_object: int = typer.Option(0, "--max-object", help="Shrink object (weapon/helm) textures larger than this (0 = keep size)."),
    section: str = typer.Option(None, "--section", help="Force the body section (ArmUpper, TorsoUpper, ...) for all inputs."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Resize/re-encode textures for 3.3.5: armor components to their body region, objects capped + DXT."""
    from pydantic import BaseModel
    from .textures import convert_textures

    class TexturesOut(BaseModel):
        results: list

    try:
        results = convert_textures(paths, out, target=target, max_object=max_object or None, section=section)
    except (OSError, ValueError) as exc:
        if json_out:
            _emit_json("textures", False, None, str(exc))
        else:
            console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    if json_out:
        _emit_json("textures", True, TexturesOut(results=[r.model_dump() for r in results]))
        raise typer.Exit(code=0)
    for r in results:
        what = f"{r.section} " if r.section else ""
        console.print(f"[green]{r.kind:9}[/] {what}{r.source_size[0]}x{r.source_size[1]} -> "
                      f"{r.size[0]}x{r.size[1]} {r.format}  {r.output}", highlight=False)
        if r.dbc_name:
            console.print(f"           ItemDisplayInfo name: {r.dbc_name}", highlight=False)
        for w in r.warnings:
            console.print(f"           [yellow]{w}[/]")


@app.command()
def helms(
    model: str = typer.Argument(..., help="Any one race/gender variant of the helm (e.g. helm_foo_hum.m2)."),
    out: str = typer.Option(..., "--out", help="Output folder for all converted variants."),
    client: str = typer.Option("classic", "--client", help="classic (adds MultiConverter -fixhelm) or hd character models."),
    engine: str = typer.Option("wotlkconv", "--engine", help="wotlkconv (built-in) or multiconverter."),
    multiconverter: str = typer.Option("", "--multiconverter", help="MultiConverter_Console.exe (multiconverter engine)."),
    listfile: str = typer.Option("", "--listfile", help="Community listfile.csv (texture baking)."),
    no_goblin: bool = typer.Option(False, "--no-goblin", help="Skip the NPC-only goblin variants."),
) -> None:
    """Convert every 3.3.5 race/gender variant of a helm (one model per race/gender)."""
    from .helms import convert_helm_set

    if engine == "multiconverter" and not multiconverter:
        console.print("[red]--engine multiconverter needs --multiconverter <path to MultiConverter_Console.exe>[/]")
        raise typer.Exit(code=2)
    try:
        hs, results = convert_helm_set(model, out, client_models=client, engine=engine,
                                       tools={"multiconverter": multiconverter, "listfile": listfile},
                                       include_npc_races=not no_goblin,
                                       on_log=lambda m: console.print(m, markup=False, highlight=False))
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    bad = [c for c, r in results.items() if not r.ok]
    console.print(f"\n[bold]{hs.base}[/]: {len(results) - len(bad)}/{len(results)} variant(s) clean"
                  + (f", [yellow]blockers in {', '.join(bad)}[/]" if bad else ""))
    if hs.missing:
        console.print(f"[yellow]missing 3.3.5 variants:[/] {', '.join(hs.missing)}")
    console.print(f"ItemDisplayInfo model name: {hs.dbc_model}  (register-item --model {hs.dbc_model})")
    raise typer.Exit(code=1 if bad else 0)


@app.command()
def character(
    bfa: str = typer.Option("", "--bfa", help="A local BfA (8.x) install, e.g. I:\\WoW Modding\\Clients\\WorldofWarcraft BFA."),
    retail: str = typer.Option("", "--retail", help="Or a local retail install (9.0+), e.g. I:\\World of Warcraft: "
                               "its customization is projected onto 3.3.5's."),
    race: str = typer.Option(..., "--race", help="Race by ClientFileString or name, e.g. KulTiran."),
    sex: str = typer.Option(..., "--sex", help="male or female."),
    out: str = typer.Option(..., "--out", help="Output root (laid out like the MPQ: Character\\..., DBFilesClient\\)."),
    race_id: int = typer.Option(33, "--race-id", help="3.3.5 race id for the new race's DBC rows."),
    listfile: str = typer.Option(..., "--listfile", help="Community listfile.csv."),
    dbd: str = typer.Option(..., "--dbd", help="WoWDBDefs 'definitions' folder."),
    dbc_dir: str = typer.Option("", "--dbc-dir", help="Your client's 3.3.5 DBCs (CharSections, CharHairGeosets, "
                                "CharacterFacialHairStyles) to append rows to."),
    target: str = typer.Option("hd", "--target", help="hd (512 body texture, e.g. the 3.3.5 HD patch) or classic (256)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Port a BfA or retail playable race/sex: model + layout-remapped CharSections textures + DBC rows."""
    from .character.convert import convert_character

    try:
        install, product = _source_install(bfa, retail)
        r = convert_character(install, race, sex, out, race_id=race_id, listfile=listfile, dbd_dir=dbd,
                              dbc_dir=dbc_dir or None, target=target, product=product,
                              on_log=None if json_out else (lambda m: console.print(m, markup=False, highlight=False)))
    except (OSError, ValueError) as exc:
        if json_out:
            _emit_json("character", False, None, str(exc))
        else:
            console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    if json_out:
        _emit_json("character", True, r)
        raise typer.Exit(code=0)
    console.print(f"\n[green]{r.race} {r.sex}[/] -> race id {r.race_id}: model {r.model}")
    console.print(f"  {r.textures} texture(s), {len(r.files)} file(s), DBC rows {r.rows or '(no --dbc-dir)'}")
    for w in r.warnings:
        console.print(f"  [yellow]warn[/] {w}", highlight=False)
    for c in r.check:
        console.print(f"  [red]{c}[/]" if c.startswith("fail") else f"  {c}", highlight=False)


def _source_install(bfa: str, retail: str) -> tuple[str, str | None]:
    """(install folder, .build.info product) from --bfa / --retail: exactly one of them."""
    if bool(bfa) == bool(retail):
        raise ValueError("give one source: --bfa <BfA install> or --retail <retail install>")
    return (retail, "wow") if retail else (bfa, None)


@app.command(name="race")
def race_cmd(
    race: str = typer.Argument(..., help="Race by ClientFileString or name, e.g. KulTiran, MagharOrc."),
    bfa: str = typer.Option("", "--bfa", help="A local BfA (8.x) install."),
    retail: str = typer.Option("", "--retail", help="Or a local retail install (9.0+), e.g. I:\\World of Warcraft."),
    client: str = typer.Option(..., "--client", help="Your 3.3.5a client folder (read only; its DBCs and UI are the base)."),
    out: str = typer.Option(..., "--out", help="Output folder (client\\, server\\, INSTALL.txt)."),
    listfile: str = typer.Option(..., "--listfile", help="Community listfile.csv."),
    dbd: str = typer.Option(..., "--dbd", help="WoWDBDefs 'definitions' folder."),
    server_dbc: str = typer.Option("", "--server-dbc", help="The server's DBC folder (read only), e.g. D:\\AC\\Build\\Data\\dbc."),
    name: str = typer.Option("", "--name", help="Display name (default: the BfA ClientFileString), e.g. \"Kul Tiran\"."),
    alliance_id: int = typer.Option(22, "--alliance-id", help="Race id of the Alliance version (0: none). 1-32."),
    horde_id: int = typer.Option(23, "--horde-id", help="Race id of the Horde version (0: none). 1-32."),
    alliance_template: int = typer.Option(1, "--alliance-template", help="Race the Alliance version copies (start, racials, gear)."),
    horde_template: int = typer.Option(2, "--horde-template", help="Race the Horde version copies."),
    look_template: int = typer.Option(1, "--look-template", help="Race whose voices, names, helmets and scene are borrowed."),
    target: str = typer.Option("hd", "--target", help="hd (512 body texture) or classic (256)."),
    reuse: bool = typer.Option(False, "--reuse", help="Reuse the character conversion already in --out."),
    replace: bool = typer.Option(False, "--replace", help="Remove a previous build of these race ids first (rebuilds); "
                                 "it is rebuilt where it was, under any race built after it."),
    on_top: bool = typer.Option(False, "--on-top", help="With --replace: put the race after every other race "
                                "instead (new ids; rebuild the races built after it afterwards)."),
    template_helmets: bool = typer.Option(False, "--template-helmets",
                                          help="Wear the look template's helmets, fitted, even where BfA has the race's own."),
    template_outfits: bool = typer.Option(False, "--template-outfits",
                                          help="Keep the template race's start armour instead of BfA's own "
                                               "outfits for the race."),
    template_racials: bool = typer.Option(False, "--template-racials",
                                          help="Keep the faction template's racials (Human's, Orc's) instead of BfA's own."),
    patch: str = typer.Option("patch-H.MPQ", "--patch", help="The folder patch the package installs into: the client "
                              "is read as that patch sees it (a patch that outranks it, e.g. the retail backport "
                              "kit's, is left out)."),
    json_out: bool = typer.Option(False, "--json", help="Emit the JSON result envelope to stdout."),
) -> None:
    """Make a BfA or retail race playable on 3.3.5a: character, DBCs, create-screen UI, server DBCs and SQL."""
    from .race.build import build_race

    try:
        install, product = _source_install(bfa, retail)
        r = build_race(install_dir=install, product=product, client_dir=client, out_dir=out, listfile=listfile,
                       dbd_dir=dbd, race=race,
                       name=name or None, alliance_id=alliance_id, horde_id=horde_id,
                       alliance_template=alliance_template, horde_template=horde_template,
                       look_template=look_template, server_dbc_dir=server_dbc or None, target=target,
                       reuse=reuse, replace=replace, on_top=on_top, own_helmets=not template_helmets,
                       own_racials=not template_racials, own_outfits=not template_outfits, patch=patch,
                       on_log=None if json_out else (lambda m: console.print(m, markup=False, highlight=False)))
    except (OSError, ValueError) as exc:
        if json_out:
            _emit_json("race", False, None, str(exc))
        else:
            console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    if json_out:
        _emit_json("race", True, r)
        raise typer.Exit(code=0)
    console.print(f"\n[green]{r.name}[/]: " + ", ".join(f"race {s['race_id']} ({s['faction']})" for s in r.races))
    for side, rows in r.rows.items():
        console.print(f"  {side} rows: {rows}", highlight=False)
    for w in r.warnings:
        console.print(f"  [yellow]warn[/] {w}", highlight=False)
    console.print(f"  install steps: {os.path.join(out, 'INSTALL.txt')}")


@app.command(name="race-identity")
def race_identity_cmd(
    race: str = typer.Argument("EarthenDwarf", help="A registry race's retail ClientFileString (Earthen: EarthenDwarf)."),
    retail: str = typer.Option(..., "--retail", help="A local retail install, e.g. I:\\World of Warcraft."),
    client: str = typer.Option(..., "--client", help="The x64 client folder (read only; its DBCs and UI are the base)."),
    out: str = typer.Option(..., "--out", help="Output folder (client\\, server\\, package.json, INSTALL.txt)."),
    listfile: str = typer.Option(..., "--listfile", help="Community listfile.csv."),
    dbd: str = typer.Option(..., "--dbd", help="WoWDBDefs 'definitions' folder."),
    server_dbc: str = typer.Option(..., "--server-dbc", help="The server's DBC folder (read only)."),
    patch: str = typer.Option("patch-H.MPQ", "--patch", help="The folder patch the package installs into."),
) -> None:
    """A registry race's own names, voice, create-screen icon, scene and texts, and racials (races past 32,
    which the x64 client's wxl-races.cfg adds; Earthen 33/34)."""
    from .race.identity import EARTHEN, build_identity

    if race != EARTHEN["file"]:
        console.print("[red]only Earthen (EarthenDwarf) has its races and racial picks set up[/]")
        raise typer.Exit(code=2)
    try:
        r = build_identity(install_dir=retail, client_dir=client, out_dir=out, listfile=listfile, dbd_dir=dbd,
                           server_dbc_dir=server_dbc, patch=patch,
                           on_log=lambda m: console.print(m, markup=False, highlight=False))
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    console.print(f"\n[green]{r.name}[/]: " + ", ".join(f"race {s['race_id']} ({s['faction']})" for s in r.races))
    for side, rows in r.rows.items():
        console.print(f"  {side} rows: {rows}", highlight=False)
    for w in r.warnings:
        console.print(f"  [yellow]warn[/] {w}", highlight=False)
    console.print(f"  install steps: {os.path.join(out, 'INSTALL.txt')}")


@app.command(name="passives")
def passives_cmd(
    retail: str = typer.Option(..., "--retail", help="A local retail install, e.g. I:\\World of Warcraft."),
    client: str = typer.Option(..., "--client", help="A client folder that plays (read only; its DBCs are the base)."),
    out: str = typer.Option(..., "--out", help="Output folder (client\\, server\\, package.json)."),
    listfile: str = typer.Option(..., "--listfile", help="Community listfile.csv."),
    dbd: str = typer.Option(..., "--dbd", help="WoWDBDefs 'definitions' folder."),
    server_dbc: str = typer.Option(..., "--server-dbc", help="The server's DBC folder (read only)."),
    patch: str = typer.Option("patch-H.MPQ", "--patch", help="The patch the package installs into."),
) -> None:
    """Retail's six new passives for the stock races (Undead, Blood Elf, Dwarf, Tauren, Gnome, Night Elf),
    beside every 3.3.5 racial they have."""
    from .race.passives import build_passives

    try:
        r = build_passives(install_dir=retail, client_dir=client, out_dir=out, listfile=listfile, dbd_dir=dbd,
                           server_dbc_dir=server_dbc, patch=patch,
                           on_log=lambda m: console.print(m, markup=False, highlight=False))
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    for side, rows in r.rows.items():
        console.print(f"  {side} rows: {rows}", highlight=False)
    for w in r.warnings:
        console.print(f"  [yellow]warn[/] {w}", highlight=False)


@app.command(name="glue")
def glue_cmd(
    bfa: str = typer.Option(..., "--bfa", help="A local BfA (8.x) install."),
    client: str = typer.Option(..., "--client", help="Your 3.3.5a client folder (read only; its UI files are the base)."),
    out: str = typer.Option(..., "--out", help="Output folder (client\\, package.json, INSTALL.txt)."),
    listfile: str = typer.Option(..., "--listfile", help="Community listfile.csv."),
    dbd: str = typer.Option(..., "--dbd", help="WoWDBDefs 'definitions' folder."),
    patch: str = typer.Option("patch-H.MPQ", "--patch", help="The folder patch the package installs into: the client "
                              "is read as that patch sees it (a patch that outranks it, e.g. the retail backport "
                              "kit's, is left out)."),
) -> None:
    """Character create and select laid out as Battle for Azeroth's, for every race (create zooms to the face)."""
    from .glue.build import build_glue

    try:
        r = build_glue(install_dir=bfa, client_dir=client, out_dir=out, listfile=listfile, dbd_dir=dbd, patch=patch,
                       on_log=lambda m: console.print(m, markup=False, highlight=False))
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    for w in r.warnings:
        console.print(f"  [yellow]warn[/] {w}", highlight=False)
    console.print(f"  install steps: {os.path.join(out, 'INSTALL.txt')}")


@app.command(name="outfits")
def outfits_cmd(
    client: str = typer.Option(..., "--client", help="Your 3.3.5a client folder (read only; the CharStartOutfit.dbc it loads is the base)."),
    server_dbc: str = typer.Option(..., "--server-dbc", help="The server's DBC folder (read only)."),
    out: str = typer.Option(..., "--out", help="Output folder (client\\, server\\, package.json, INSTALL.txt)."),
    patch: str = typer.Option("patch-H.MPQ", "--patch", help="The folder patch the package installs into: the client "
                              "is read as that patch sees it (a patch that outranks it, e.g. the retail backport "
                              "kit's, is left out)."),
) -> None:
    """Start outfits of each race's own faction (an All Races All Classes Undead hunter gets the Horde's), every item showing its own display."""
    from .race.outfits import OutfitsError, build_outfits

    try:
        r = build_outfits(client_dir=client, server_dbc_dir=server_dbc, out_dir=out, patch=patch,
                          on_log=lambda m: console.print(m, markup=False, highlight=False))
    except (OSError, ValueError, OutfitsError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    for side, changes in r.changes.items():
        for c in changes:
            console.print(f"  {side}: {c}", highlight=False)
    console.print(f"  install steps: {os.path.join(out, 'INSTALL.txt')}")


@app.command(name="install")
def install_cmd(
    package: str = typer.Argument(..., help="A `race` or `glue` output folder (race.json / package.json)."),
    client: str = typer.Option("", "--client", help="Your 3.3.5a client folder."),
    patch: str = typer.Option("patch-H.MPQ", "--patch", help="The folder patch under Data\\ to install into."),
    server_dbc: str = typer.Option("", "--server-dbc", help="The server's DBC folder."),
    clean: bool = typer.Option(False, "--clean", help="Also move leftover files in the package's folders to the backup."),
    apply: bool = typer.Option(False, "--apply", help="Actually copy (default: show the plan only)."),
) -> None:
    """Install a race or glue package without overwriting anything you customized since the build."""
    from .race.install import apply_install, plan_install

    try:
        plan = plan_install(package, client or None, patch, server_dbc or None, clean)
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)
    counts = plan.count()
    for a in plan.actions:
        if a.kind in ("same", "leftover") or (a.kind == "add" and a.rel.startswith("client/Character/")):
            continue
        colour = {"stale": "red", "conflict": "red"}.get(a.kind, "white")
        console.print(f"  [{colour}]{a.kind:8s}[/] {a.target}" + (f"  ({a.detail})" if a.detail else ""),
                      highlight=False)
    leftovers = [a for a in plan.actions if a.kind == "leftover"]
    if leftovers:
        console.print(f"  [yellow]{len(leftovers)} leftover file(s)[/] in the package's folders that it doesn't "
                      f"contain (e.g. {leftovers[0].target}) - "
                      + ("they will be moved to the backup" if clean else "kept; --clean moves them to the backup"),
                      highlight=False)
    if plan.shadowed:
        by: dict[str, list[str]] = {}
        for rel, higher in plan.shadowed.items():
            by.setdefault(higher, []).append(rel)
        for higher, rels in sorted(by.items()):
            console.print(f"  [yellow]{len(rels)} file(s) shadowed[/] by {higher}, which outranks {patch} "
                          f"(e.g. {rels[0]}): the client loads that patch's copy, so these changes show only "
                          "once it is rebuilt on top of this install (the retail backport kit: take its patch out "
                          "of Data, bp.py scan, tables, audit, prove-gates, pack, put the new one back)",
                          highlight=False)
    console.print(f"\nplan: {counts}")
    if plan.blocked:
        console.print(f"[red]{len(plan.blocked)} file(s) block the install - nothing was copied.[/]")
        raise typer.Exit(code=1)
    if not apply:
        console.print("dry run - add --apply to install (replaced files are backed up first)")
        return
    receipt = apply_install(plan, clean)
    console.print(f"[green]installed[/]; backups and undo receipt: {receipt}")
    console.print(f"  undo with: retroport uninstall \"{receipt}\"")


@app.command(name="uninstall")
def uninstall_cmd(receipt: str = typer.Argument(..., help="An installs\\<time>.json receipt.")) -> None:
    """Undo an `install`: restore what it replaced or moved, remove what it added."""
    from .race.install import uninstall

    try:
        console.print(f"[green]undone[/]: {uninstall(receipt)}")
    except (OSError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2)


@app.command(name="workbench")
def workbench_cmd(
    bfa: str = typer.Option("", "--bfa", help="A local BfA (8.x) install to browse."),
    retail: str = typer.Option("", "--retail", help="A local retail install to browse (a partial one fetches "
                               "what it does not store from Blizzard's CDN, kept in the workbench cache)."),
    client: str = typer.Option("", "--client", help="Your 3.3.5a client: items it already has are marked."),
    dbd: str = typer.Option("", "--dbd", help="WoWDBDefs 'definitions' folder."),
    listfile: str = typer.Option("", "--listfile", help="Community listfile.csv."),
    data: str = typer.Option("", "--data", help="Where the workbench keeps its cache and basket "
                             "(default %USERPROFILE%\\.retroport\\workbench)."),
    port: int = typer.Option(8335, "--port"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open the page in your browser."),
) -> None:
    """Browse and pick items and sets - retail's from wago.tools, or from your own installs.

    Without --retail / --bfa, retail's items and BfA's bodies (for the character view) come from
    wago.tools.

    Options given are remembered (%USERPROFILE%\\.retroport\\workbench.json): later runs need none."""
    from .workbench.server import Settings, serve

    s = Settings.load()
    if bfa:
        s.set_source("bfa", "BfA", os.path.abspath(bfa))
    if retail:
        s.set_source("retail", "Retail", os.path.abspath(retail), product="wow", cdn=True)
    for name, value in (("client", client), ("dbd", dbd), ("listfile", listfile), ("data", data)):
        if value:
            setattr(s, name, os.path.abspath(value))
    s.save()
    for p in s.problems():
        console.print(f"[yellow]warn[/] {p}", highlight=False)
    serve(s, port=port, open_browser=not no_browser, log=lambda m: console.print(m, highlight=False))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
