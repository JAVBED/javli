import json, os, re, shutil
from pathlib import Path
from .instances import create, InstanceError

class ImportError(InstanceError): pass

def _read_json(path):
    try: return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception: return {}

def _sanitize(name):
    name=re.sub(r"[^A-Za-z0-9._-]+","-",name.strip()).strip("-")
    return name or "imported"

def detect(path):
    p=Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir(): raise ImportError(f"Instance directory not found: {p}")
    if (p/"instance.cfg").exists():
        cfg={}
        for line in (p/"instance.cfg").read_text(encoding="utf-8",errors="ignore").splitlines():
            if "=" in line:
                k,v=line.split("=",1); cfg[k.strip()]=v.strip()
        game=p/".minecraft" if (p/".minecraft").exists() else p/"minecraft"
        return {"launcher":"Prism/MultiMC","name":cfg.get("name") or p.name,"game":game,"root":p}
    if (p/"minecraftinstance.json").exists():
        d=_read_json(p/"minecraftinstance.json")
        return {"launcher":"CurseForge","name":d.get("name") or p.name,"game":p,"root":p,"meta":d}
    if (p/"profile.json").exists() and ((p/"mods").exists() or (p/"minecraft").exists()):
        d=_read_json(p/"profile.json")
        return {"launcher":"Modrinth","name":d.get("name") or p.name,"game":p,"root":p,"meta":d}
    if (p/"instance.json").exists():
        d=_read_json(p/"instance.json")
        return {"launcher":"Generic","name":d.get("name") or p.name,"game":p/"minecraft" if (p/"minecraft").exists() else p,"root":p,"meta":d}
    if (p/"versions").exists() and (p/"assets").exists():
        return {"launcher":"Vanilla","name":p.name if p.name!=".minecraft" else "vanilla-import","game":p,"root":p}
    if (p/"mods").exists() or (p/"saves").exists():
        return {"launcher":"Generic","name":p.name,"game":p,"root":p}
    raise ImportError("Could not recognize this as a Minecraft instance/game directory.")

def _prism_components(root):
    mmc=_read_json(root/"mmc-pack.json")
    version=None; loader=None; loader_version=None
    for comp in mmc.get("components",[]):
        uid=str(comp.get("uid","")).lower(); ver=comp.get("version")
        if uid=="net.minecraft": version=ver
        elif "fabric-loader" in uid: loader,loader_version="fabric",ver
        elif "quilt-loader" in uid: loader,loader_version="quilt",ver
        elif "neoforge" in uid: loader,loader_version="neoforge",ver
        elif uid.endswith(".forge") or uid=="net.minecraftforge": loader,loader_version="forge",ver
    return version,loader,loader_version

def _curseforge_components(meta):
    version=meta.get("gameVersion")
    loader=loader_version=None
    for x in meta.get("baseModLoader",{}) and [meta.get("baseModLoader",{})] or []:
        name=str(x.get("name",""))
        low=name.lower()
        for kind in ("neoforge","fabric","quilt","forge"):
            if low.startswith(kind):
                loader=kind; loader_version=name.split("-",1)[1] if "-" in name else None
                break
    return version,loader,loader_version

def _modrinth_components(meta):
    version=meta.get("game_version") or meta.get("gameVersion")
    loader=meta.get("loader")
    loader_version=meta.get("loader_version") or meta.get("loaderVersion")
    return version,loader,loader_version

def inspect(path):
    d=detect(path); launcher=d["launcher"]
    if launcher=="Prism/MultiMC": vals=_prism_components(d["root"])
    elif launcher=="CurseForge": vals=_curseforge_components(d.get("meta",{}))
    elif launcher=="Modrinth": vals=_modrinth_components(d.get("meta",{}))
    else:
        m=d.get("meta",{}); vals=(m.get("version"),m.get("loader"),m.get("loader_version"))
    version,loader,loader_version=vals
    if not version:
        # Best-effort vanilla detection from version directories.
        versions=d["game"]/"versions"
        if versions.exists():
            rows=sorted((x.name for x in versions.iterdir() if x.is_dir()),reverse=True)
            if len(rows)==1: version=rows[0]
    return {**d,"version":version,"loader":loader,"loader_version":loader_version}

DATA_FOLDERS = {"mods", "config", "saves", "resourcepacks", "shaderpacks", "screenshots", "defaultconfigs", "kubejs", "schematics"}
DATA_FILES = {"options.txt", "optionsof.txt", "servers.dat", "servers.dat_old", "icon.png"}


def _copy_game_data(source, destination):
    """Copy playable user data without launcher profiles, tokens, or game binaries."""
    if source.is_symlink():
        raise ImportError("Source game directory is a link; choose its actual folder.")
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        if child.is_symlink():
            continue
        if child.is_file() and child.name.lower() in DATA_FILES:
            shutil.copy2(child, destination / child.name)
        elif child.is_dir() and child.name.lower() in DATA_FOLDERS:
            target = destination / child.name
            for folder, dirs, files in os.walk(child, followlinks=False):
                dirs[:] = [name for name in dirs if not (Path(folder) / name).is_symlink()]
                relative = Path(folder).relative_to(child)
                output = target / relative
                output.mkdir(parents=True, exist_ok=True)
                for filename in files:
                    path = Path(folder) / filename
                    if path.is_file() and not path.is_symlink():
                        shutil.copy2(path, output / filename)


def import_instance(path,name=None,move=False,version=None,data_only=False):
    info=inspect(path)
    if version:
        if not isinstance(version,str) or len(version)>100 or not re.fullmatch(r"[A-Za-z0-9._+\-]+",version):
            raise ImportError("Invalid Minecraft version override.")
        info["version"]=version
    if not info.get("version"):
        raise ImportError("Could not determine the Minecraft version. Import cancelled rather than guessing.")
    if data_only and move:
        raise ImportError("Data-only import always copies; moving the source is not supported.")
    dest_name=_sanitize(name or info["name"])
    obj=create(dest_name,"release",info["version"],"auto",info.get("loader"),info.get("loader_version"))
    dest=Path(obj["path"])/"minecraft"; src=Path(info["game"])
    try:
        if data_only:
            _copy_game_data(src,dest)
        elif move:
            if dest.exists(): shutil.rmtree(dest)
            shutil.move(str(src),str(dest))
        else:
            if dest.exists(): shutil.rmtree(dest)
            shutil.copytree(src,dest)
    except Exception:
        from .instances import delete
        delete(dest_name,False)
        raise
    return obj,info
