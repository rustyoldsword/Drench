r"""Pack dist\Drench (made by tools\stage.ps1) into the release archive: a FOMOD with an explicit Main mod page.

  core/    everything except the compatibility layer (always installed)
  compat/  WetFunctionNG.esp (empty ESL stub) + the forwarding WetFunctionNG script (recommended option)
  fomod/   info.xml, ModuleConfig.xml - UTF-8 without an XML declaration (Vortex chokes on ElementTree's one)

Then the install path is tested the way a user meets it: the archive is extracted into an empty folder, the
installer's choices are read from ModuleConfig.xml and carried out, and the result must equal dist\Drench file for
file (MD5), with the build-machine leak check run over the extracted copy too.

Output: <Desktop>\Drench - Wet Skin Framework <version>.7z.   Usage:  python tools\package.py
Re-running rebuilds the archive from scratch and gives the same files."""
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / "dist" / "Drench"
OUT = ROOT / "dist" / "fomod"
VERSION = re.search(r'set_version\("([^"]+)"\)', (ROOT / "xmake.lua").read_text(encoding="utf-8")).group(1)
NAME = "Drench - Wet Skin Framework"
ARCHIVE = Path.home() / "Desktop" / f"{NAME} {VERSION}.7z"
SEVEN_ZIP = next(p for p in (Path(r"C:\Program Files\7-Zip\7z.exe"), Path(r"C:\Program Files (x86)\7-Zip\7z.exe")) if p.exists())
COMPAT = {Path("WetFunctionNG.esp"), Path("Scripts/WetFunctionNG.pex"), Path("Scripts/Source/WetFunctionNG.psc")}
MDNM_OPTION = "With Mu Dynamic NormalMap - drops in relief (best)"
PLAIN_OPTION = "Without Mu Dynamic NormalMap - wet shine only"


def is_relief(rel):
    """The 3BA relief maps for Mu Dynamic NormalMap (tools\\make_mdnm_detail.py): wet_<state>_detail_n.dds."""
    return rel.parent == Path("textures/actors/character/Drench") and rel.name.endswith("_detail_n.dds")
# strings that must never ship (build machine names, local paths): one per line in tools\leak_patterns.txt
_PATTERNS = Path(__file__).with_name("leak_patterns.txt")
LEAKS = [re.compile(line.strip().encode(), re.I) for line in (_PATTERNS.read_text(encoding="utf-8").splitlines() if _PATTERNS.exists() else []) if line.strip()]


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree(root):
    return {p.relative_to(root): p for p in root.rglob("*") if p.is_file()}


def module_config():
    root = ET.Element("config")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    root.set("xsi:noNamespaceSchemaLocation", "http://qconsulting.ca/fo3/ModConfig5.0.xsd")
    ET.SubElement(root, "moduleName").text = NAME
    ET.SubElement(ET.SubElement(root, "requiredInstallFiles"), "folder", source="core", destination="", priority="0")
    steps = ET.SubElement(root, "installSteps", order="Explicit")
    step = ET.SubElement(steps, "installStep", name="Main mod")
    groups = ET.SubElement(step, "optionalFileGroups", order="Explicit")

    main = ET.SubElement(groups, "group", name="Main mod", type="SelectAll")
    plugins = ET.SubElement(main, "plugins", order="Explicit")
    plugin = ET.SubElement(plugins, "plugin", name=f"Drench - Wet Skin Framework {VERSION}")
    ET.SubElement(plugin, "description").text = (
        "Wetness from rain, snow, water, sweat, arousal and sex, written straight into the skin shader: wet maps on "
        "body, hands, feet, head, Goam ears and genitals for 3BA and UBE, female and male. Settings in SKSE Menu "
        "Framework. Always installed. Disable WetFunction NG, Wet Function Redux, OSweat and Dewpoint.")
    ET.SubElement(plugin, "files")  # the files themselves are the required core folder
    ET.SubElement(ET.SubElement(plugin, "typeDescriptor"), "type", name="Required")

    compat = ET.SubElement(groups, "group", name="Compatibility", type="SelectAny")
    plugins = ET.SubElement(compat, "plugins", order="Explicit")
    plugin = ET.SubElement(plugins, "plugin", name="WetFunction NG compatibility")
    ET.SubElement(plugin, "description").text = (
        "For mods written for WetFunction NG (SexLab Survival, Diary of Mine, Vitals HUD, SexLab P++ and others): "
        "an empty ESL WetFunctionNG.esp, so their checks find it, and a WetFunctionNG script that hands every call "
        "to Drench. Recommended. Never install it next to the real WetFunction NG.")
    files = ET.SubElement(plugin, "files")
    ET.SubElement(files, "folder", source="compat", destination="", priority="0")
    ET.SubElement(ET.SubElement(plugin, "typeDescriptor"), "type", name="Recommended")

    # 3BA: drops in relief through Mu Dynamic NormalMap, or the wet shine alone as in WetFunction NG. The installer
    # recommends the one that fits: the relief when MuDynamicNormalMap.dll is installed.
    relief = ET.SubElement(groups, "group", name="3BA (CBBE) bodies", type="SelectExactlyOne")
    plugins = ET.SubElement(relief, "plugins", order="Explicit")
    for name, description, folder, with_mdnm in (
        (MDNM_OPTION,
         "Best quality. Drops and streaks stand up on the 3BA body in real relief, like on UBE, on top of the shine. "
         "Needs Mu Dynamic NormalMap: Drench hands it the drops as a detail map, and it rebuilds the body's normal map "
         "from its real shape. Adds 4K relief maps.", "relief", True),
        (PLAIN_OPTION,
         "Without Mu Dynamic NormalMap. The 3BA body gets the wet shine maps only - drops and sweat drawn in the "
         "shine, close to WetFunction NG. UBE keeps its relief either way.", None, False),
    ):
        plugin = ET.SubElement(plugins, "plugin", name=name)
        ET.SubElement(plugin, "description").text = description
        files = ET.SubElement(plugin, "files")
        if folder:
            ET.SubElement(files, "folder", source=folder, destination="", priority="0")
        kind = ET.SubElement(ET.SubElement(plugin, "typeDescriptor"), "dependencyType")
        ET.SubElement(kind, "defaultType", name="Optional" if with_mdnm else "Recommended")
        pattern = ET.SubElement(ET.SubElement(kind, "patterns"), "pattern")
        deps = ET.SubElement(pattern, "dependencies", operator="And")
        ET.SubElement(deps, "fileDependency", file="SKSE\\Plugins\\MuDynamicNormalMap.dll", state="Active")
        ET.SubElement(pattern, "type", name="Recommended" if with_mdnm else "Optional")
    return ET.ElementTree(root)


def info_xml():
    root = ET.Element("fomod")
    ET.SubElement(root, "Name").text = NAME
    ET.SubElement(root, "Version").text = VERSION
    ET.SubElement(root, "Description").text = (
        "Characters get wet from rain, snow, water, sweat, arousal and sex and dry off gradually. The successor of "
        "WetFunction NG: no RaceMenu, no MCM, wet maps written straight into the skin shader.")
    ET.SubElement(ET.SubElement(root, "Groups"), "element").text = "SKSE"
    return ET.ElementTree(root)


def write_xml(tree, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=False)
    ET.parse(path)


def install(extracted, target, mdnm):
    """What a FOMOD installer does: the required folder, every plugin typed Required/Recommended, and in the 3BA
    group the option the user's setup gets (mdnm: Mu Dynamic NormalMap installed or not)."""
    config = ET.parse(extracted / "fomod" / "ModuleConfig.xml").getroot()
    folders = [(f.get("source"), f.get("destination")) for f in config.find("requiredInstallFiles")]
    for plugin in config.iter("plugin"):
        plain = plugin.find("typeDescriptor/type")
        if plain is not None:
            chosen = plain.get("name") in ("Required", "Recommended")
        else:
            chosen = plugin.get("name") == (MDNM_OPTION if mdnm else PLAIN_OPTION)
        if chosen:
            folders += [(f.get("source"), f.get("destination")) for f in plugin.find("files")]
    for source, destination in folders:
        shutil.copytree(extracted / source, target / destination, dirs_exist_ok=True)
    return config


def leaks(root):
    found = []
    for rel, path in tree(root).items():
        if path.suffix.lower() == ".dds":
            continue
        data = path.read_bytes()
        found += [f"{rel}: {m.group(0)!r}" for pattern in LEAKS for m in [pattern.search(data)] if m]
    return found


def main():
    if not STAGE.exists():
        sys.exit("dist\\Drench is missing: run tools\\stage.ps1")
    staged = tree(STAGE)
    assert COMPAT <= set(staged), COMPAT - set(staged)
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel, path in staged.items():
        dst = OUT / ("compat" if rel in COMPAT else "relief" if is_relief(rel) else "core") / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst)
    write_xml(module_config(), OUT / "fomod" / "ModuleConfig.xml")
    write_xml(info_xml(), OUT / "fomod" / "info.xml")
    for xml in (OUT / "fomod").iterdir():
        assert not xml.read_bytes().startswith((b"<?xml", b"\xef\xbb\xbf")), f"{xml.name} has a declaration or BOM"

    if ARCHIVE.exists():
        ARCHIVE.unlink()
    subprocess.run([str(SEVEN_ZIP), "a", "-t7z", "-mx=9", "-md=256m", "-mmt=on", str(ARCHIVE), "."], cwd=OUT, check=True,
                   stdout=subprocess.DEVNULL)

    # the user's path: extract, run the installer's choices, compare with the build
    with tempfile.TemporaryDirectory() as tmp:
        extracted, installed = Path(tmp) / "archive", Path(tmp) / "Data"
        subprocess.run([str(SEVEN_ZIP), "x", str(ARCHIVE), f"-o{extracted}"], check=True, stdout=subprocess.DEVNULL)
        assert set(tree(extracted)) == set(tree(OUT)), "the archive does not hold what was packed"
        relief = {rel for rel in staged if is_relief(rel)}
        assert relief, "no relief maps staged"
        for mdnm, expected in ((True, set(staged)), (False, set(staged) - relief)):
            installed = Path(tmp) / ("Data-mdnm" if mdnm else "Data-plain")
            install(extracted, installed, mdnm)
            got = tree(installed)
            assert set(got) == expected, f"{'with' if mdnm else 'without'} MDNM: missing {expected - set(got)}, extra {set(got) - expected}"
            bad = [str(rel) for rel in expected if md5(staged[rel]) != md5(got[rel])]
            assert not bad, f"differ after install: {bad}"
        problems = leaks(extracted)
        assert not problems, f"build-machine text in the archive: {problems}"
        core_only = Path(tmp) / "CoreOnly"
        shutil.copytree(extracted / "core", core_only)
        assert not (COMPAT & set(tree(core_only))), "compatibility files leaked into core"
        assert not any(is_relief(rel) for rel in tree(core_only)), "relief maps leaked into core"

    print(f"{len(staged)} files ({len(COMPAT)} compatibility, {len(relief)} 3BA relief); install test with and without "
          f"MDNM: equal to the build, no leaks")
    print(f"{ARCHIVE.name}: {ARCHIVE.stat().st_size:,} bytes, MD5 {md5(ARCHIVE).upper()}")
    print(f"Drench.dll MD5 {md5(STAGE / 'SKSE' / 'Plugins' / 'Drench.dll').upper()}")


if __name__ == "__main__":
    main()
