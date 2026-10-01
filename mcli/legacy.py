import os, re, shutil, subprocess, zipfile
from pathlib import Path
from .cache import ROOT
from .auth import load_account

LEGACY = ROOT / "legacy"
NATIVES = ROOT / "legacy-natives"

class LegacyLaunchError(RuntimeError): pass

def java_path():
    override=os.getenv("MCLI_LEGACY_JAVA") or os.getenv("MCLI_JAVA")
    if override:
        return override
    j=shutil.which("java")
    if not j:
        raise LegacyLaunchError("Java not found. Set MCLI_LEGACY_JAVA to an older Java runtime (Java 8 is recommended for many historical builds).")
    return j

def inspect_jar(jar):
    with zipfile.ZipFile(jar) as z:
        names=set(z.namelist())
        manifest=""
        try:
            manifest=z.read("META-INF/MANIFEST.MF").decode("utf-8","replace")
        except KeyError:
            pass
    main=None
    m=re.search(r"(?im)^Main-Class:\s*(.+?)\s*$",manifest)
    if m: main=m.group(1).strip()
    return names,main

def choose_main(names, manifest_main=None):
    if manifest_main:
        return manifest_main
    # Known historical client entry points, in useful priority order.
    candidates=[
        "net/minecraft/client/Minecraft.class",
        "com/mojang/minecraft/Minecraft.class",
        "Minecraft.class",
    ]
    for c in candidates:
        if c in names:
            return c[:-6].replace("/",".")
    raise LegacyLaunchError("Could not determine this archive's client entry point.")

def launch_legacy(version, jar, game_dir_override=None):
    from .launcher import _launch_preferences
    preferences = _launch_preferences()
    game=Path(game_dir_override) if game_dir_override else Path(preferences["MCLI_GAME_DIR"]) if "MCLI_GAME_DIR" in preferences else LEGACY/version.id
    game.mkdir(parents=True,exist_ok=True)
    names,main=inspect_jar(jar)
    main=choose_main(names,main)

    account=load_account()
    username=(account or {}).get("profile",{}).get("name","Player")
    token=(account or {}).get("minecraft_access_token","0")

    # The very old clients were not standardized. MCLI selects arguments by
    # client family and falls back to direct invocation when appropriate.
    era=(version.type or "archived").lower()
    args=[]
    if main == "net.minecraft.client.Minecraft":
        # Legacy desktop client commonly accepted username/session.
        args=[username,token]
    elif main == "com.mojang.minecraft.Minecraft":
        # Classic jars varied; many can start directly and present their own menu.
        args=[]

    from .java_manager import resolve as resolve_java
    java = resolve_java(version_id=version.id, legacy=True)
    cmd=[str(java),"-Xmx1G","-cp",str(jar),main,*args]
    print(f"Launching archived {era} build {version.id}")
    print(f"Entry point: {main}")
    print(f"Game directory: {game}")
    return subprocess.Popen(cmd,cwd=game)
