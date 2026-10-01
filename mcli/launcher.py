import json, os, platform, re, shutil, subprocess, zipfile
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from .cache import ROOT, VERSIONS, ensure
from .net import download
from .auth import load_account, refresh, AuthError

LIBRARIES = ROOT / "libraries"
ASSETS = ROOT / "assets"
NATIVES = ROOT / "natives"
GAME = ROOT / "game"

def _os_name():
    return {"Windows":"windows","Darwin":"osx","Linux":"linux"}.get(platform.system(), "linux")

def _arch():
    return "64" if platform.machine().lower() in ("amd64","x86_64","arm64","aarch64") else "32"

def _rule_ok(rules):
    if not rules:
        return True
    allowed = False
    for rule in rules:
        applies = True
        osrule = rule.get("os")
        if osrule:
            if osrule.get("name") and osrule["name"] != _os_name():
                applies = False
            if osrule.get("arch"):
                want = osrule["arch"]
                machine = platform.machine().lower()
                if want == "x86" and _arch() != "32": applies = False
                elif want == "x86_64" and machine not in ("amd64","x86_64"): applies = False
                elif want == "arm64" and machine not in ("arm64","aarch64"): applies = False
        # Feature rules are false unless MCLI explicitly enables the feature.
        if rule.get("features"):
            applies = False
        if applies:
            allowed = rule.get("action") == "allow"
    return allowed

def _artifact_path(name):
    group, artifact, version = name.split(":")[:3]
    base = LIBRARIES / Path(*group.split(".")) / artifact / version
    return base / f"{artifact}-{version}.jar"

def _download_libraries(meta, natives_dir):
    cp=[]
    natives_dir.mkdir(parents=True, exist_ok=True)
    for lib in meta.get("libraries", []):
        if not _rule_ok(lib.get("rules")):
            continue
        downloads=lib.get("downloads", {})
        artifact=downloads.get("artifact")
        if artifact and artifact.get("url"):
            path=artifact.get("path")
            if path:
                dest=LIBRARIES / path
            else:
                dest=_artifact_path(lib["name"])
            if not dest.exists():
                download(artifact["url"], dest, artifact.get("sha1"))
            cp.append(str(dest))
        elif lib.get("name"):
            # Legacy / installer-generated launcher profile fallback.
            dest=_artifact_path(lib["name"])
            if not dest.exists() and lib.get("url"):
                parts=lib["name"].split(":")
                if len(parts)>=3:
                    group,artifact_id,ver=parts[:3]
                    rel="/".join(group.split("."))+f"/{artifact_id}/{ver}/{artifact_id}-{ver}.jar"
                    base=lib["url"]
                    if not base.endswith("/"): base+="/"
                    try:
                        download(base+rel,dest)
                    except Exception:
                        pass
            if dest.exists():
                cp.append(str(dest))

        classifiers=downloads.get("classifiers", {})
        nat=lib.get("natives", {}).get(_os_name())
        if nat:
            nat=nat.replace("${arch}", _arch())
            native_artifact=classifiers.get(nat)
            if native_artifact and native_artifact.get("url"):
                native_path=native_artifact.get("path")
                if native_path:
                    dest=LIBRARIES / native_path
                elif lib.get("name"):
                    base_dest=_artifact_path(lib["name"])
                    dest=base_dest.with_name(base_dest.stem+"-"+nat+".jar")
                else:
                    filename=urlparse(native_artifact["url"]).path.rsplit("/",1)[-1] or (nat+".jar")
                    dest=LIBRARIES/"legacy-natives"/filename
                if not dest.exists():
                    download(native_artifact["url"], dest, native_artifact.get("sha1"))
                with zipfile.ZipFile(dest) as z:
                    excludes=(lib.get("extract") or {}).get("exclude", ["META-INF/"])
                    for member in z.infolist():
                        if member.is_dir() or any(member.filename.startswith(x) for x in excludes):
                            continue
                        z.extract(member, natives_dir)
    return cp

def _download_assets(meta):
    idx=meta.get("assetIndex")
    if not idx:
        return meta.get("assets", "legacy")

    indexes=ASSETS/"indexes"
    objects=ASSETS/"objects"
    indexes.mkdir(parents=True, exist_ok=True)

    idx_path=indexes/f'{idx["id"]}.json'
    if not idx_path.exists():
        download(idx["url"], idx_path, idx.get("sha1"))

    data=json.loads(idx_path.read_text(encoding="utf-8"))
    entries=list(data.get("objects", {}).values())
    missing=[]

    for obj in entries:
        h=obj["hash"]
        dest=objects/h[:2]/h
        if not dest.exists():
            url=obj.get("url") or f"https://resources.download.minecraft.net/{h[:2]}/{h}"
            missing.append((h,dest,url))

    total=len(entries)
    cached=total-len(missing)
    if not missing:
        print(f"Assets: {total}/{total} cached", flush=True)
        return idx["id"]

    workers=32
    print(f"Assets: {cached}/{total} cached — downloading {len(missing)} with {workers} workers", flush=True)

    def fetch_asset(item):
        h,dest,url=item
        download(url, dest, h)
        return h

    completed=cached
    last_percent=-1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(fetch_asset,item) for item in missing]
        for fut in as_completed(futures):
            fut.result()
            completed += 1
            percent=int(completed*100/total) if total else 100
            if percent != last_percent:
                print(f"Assets: {completed}/{total} ({percent}%)", end="\r", flush=True)
                last_percent=percent

    print(f"Assets: {total}/{total} (100%)" + " " * 20, flush=True)
    return idx["id"]

def _java():
    override=os.getenv("MCLI_JAVA")
    if override:
        return override
    found=shutil.which("java")
    if found:
        return found
    raise RuntimeError("Java was not found. Install Java or set MCLI_JAVA to java.exe/java.")

def _subst(value, vars):
    for k,v in vars.items():
        value=value.replace("${"+k+"}", str(v))
    return value

def _modern_args(meta, vars):
    jvm=[]
    game=[]
    args=meta.get("arguments")
    if args:
        for item in args.get("jvm", []):
            if isinstance(item,str):
                jvm.append(_subst(item,vars))
            elif _rule_ok(item.get("rules")):
                vals=item.get("value",[])
                if isinstance(vals,str): vals=[vals]
                jvm += [_subst(x,vars) for x in vals]
        for item in args.get("game", []):
            if isinstance(item,str):
                game.append(_subst(item,vars))
            elif _rule_ok(item.get("rules")):
                vals=item.get("value",[])
                if isinstance(vals,str): vals=[vals]
                game += [_subst(x,vars) for x in vals]
    else:
        # Legacy Mojang metadata.
        raw=meta.get("minecraftArguments","")
        import shlex
        game=[_subst(x,vars) for x in shlex.split(raw, posix=_os_name()!="windows")]
    return jvm,game

def _launch_preferences():
    values = {}
    for key, minimum, maximum in (("MCLI_MEMORY_MB", 512, 65536), ("MCLI_RESOLUTION_WIDTH", 640, 7680), ("MCLI_RESOLUTION_HEIGHT", 480, 4320)):
        raw = os.getenv(key)
        if raw:
            if not raw.isdecimal() or not minimum <= int(raw) <= maximum:
                raise RuntimeError(f"{key} must be between {minimum} and {maximum}.")
            values[key] = int(raw)
    game_dir = os.getenv("MCLI_GAME_DIR")
    if game_dir:
        folder = Path(game_dir).expanduser()
        if not folder.is_absolute():
            raise RuntimeError("MCLI_GAME_DIR must be an absolute path.")
        values["MCLI_GAME_DIR"] = str(folder)
    fullscreen = os.getenv("MCLI_FULLSCREEN")
    if fullscreen:
        if fullscreen not in ("0", "1"):
            raise RuntimeError("MCLI_FULLSCREEN must be 0 or 1.")
        values["MCLI_FULLSCREEN"] = fullscreen == "1"
    return values

def launch(version, client_jar, meta, game_dir_override=None):
    preferences = _launch_preferences()
    ensure()
    account=load_account()
    if not account:
        raise AuthError("No Microsoft account saved. Run: mcli login")
    # Refresh on every launch so Minecraft gets a current access token.
    print("[1/5] Refreshing account...", flush=True)
    account=refresh()
    profile=account["profile"]
    print(f"      Signed in as {profile['name']}", flush=True)

    natives=NATIVES/version.id
    print("[2/5] Checking libraries...", flush=True)
    cp=_download_libraries(meta,natives)
    cp.append(str(client_jar))

    print("[3/5] Checking assets...", flush=True)
    asset_index=_download_assets(meta)
    game_dir=Path(game_dir_override) if game_dir_override else Path(preferences["MCLI_GAME_DIR"]) if "MCLI_GAME_DIR" in preferences else GAME/version.id
    game_dir.mkdir(parents=True,exist_ok=True)

    vars={
        "auth_player_name":profile["name"],
        "version_name":version.id,
        "game_directory":str(game_dir),
        "assets_root":str(ASSETS),
        "assets_index_name":asset_index,
        "auth_uuid":profile["id"],
        "auth_access_token":account["minecraft_access_token"],
        "auth_session":account["minecraft_access_token"],
        "profile_name":"MCLI",
        "instance_icon":"",
        "server_ip":"",
        "server_port":"",
        "clientid":"",
        "auth_xuid":"",
        "user_type":"msa",
        "version_type":meta.get("type","release"),
        "natives_directory":str(natives),
        "launcher_name":"mcli",
        "launcher_version":"0.3.0",
        "classpath":os.pathsep.join(cp),
        "classpath_separator":os.pathsep,
        "library_directory":str(LIBRARIES),
        "user_properties":"{}",
        "resolution_width":str(preferences.get("MCLI_RESOLUTION_WIDTH", 854)),
        "resolution_height":str(preferences.get("MCLI_RESOLUTION_HEIGHT", 480)),
    }
    jvm_args,game_args=_modern_args(meta,vars)
    if preferences.get("MCLI_FULLSCREEN") and "--fullscreen" not in game_args:
        game_args.append("--fullscreen")
    if "MCLI_MEMORY_MB" in preferences:
        jvm_args = [arg for arg in jvm_args if not arg.startswith("-Xmx")]
        jvm_args.insert(0, f'-Xmx{preferences["MCLI_MEMORY_MB"]}M')
    if not any(x.startswith("-Xmx") for x in jvm_args):
        era={"old_beta":"beta","old_alpha":"alpha"}.get(version.type, version.type)
        if era in ("preclassic","classic","indev","infdev"):
            heap="256M"
        elif era in ("alpha","beta"):
            heap="512M"
        else:
            heap="2G"
        jvm_args.insert(0, f"-Xmx{heap}")
        print(f"      Memory: {heap} ({era})", flush=True)
    if not any("java.library.path" in x for x in jvm_args):
        jvm_args.append("-Djava.library.path="+str(natives))
    if "-cp" not in jvm_args and "-classpath" not in jvm_args:
        jvm_args += ["-cp",vars["classpath"]]

    main=meta.get("mainClass")
    if not main:
        raise RuntimeError("Version metadata has no mainClass.")
    from .java_manager import resolve as resolve_java
    print("[4/5] Resolving Java...", flush=True)
    java = resolve_java(meta=meta, version_id=version.id)
    print(f"      {java}", flush=True)

    cmd=[str(java),*jvm_args,main,*game_args]
    print(f"[5/5] Launching Minecraft {version.id} as {profile['name']}...", flush=True)
    proc=subprocess.Popen(cmd,cwd=game_dir)
    print(f"      PID {proc.pid}", flush=True)
    return proc
