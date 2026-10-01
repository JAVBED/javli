import hashlib, json, shutil, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
import requests
from .instances import get as get_instance

API="https://api.modrinth.com/v2"
UA="mcli/0.8 (Minecraft CLI launcher)"

class ModrinthError(RuntimeError): pass

def _get(path, params=None):
    r=requests.get(API+path,params=params,timeout=30,headers={"User-Agent":UA})
    r.raise_for_status()
    return r.json()

def search(query, project_type="mod", limit=10, mc=None, loader=None):
    facets=[[f"project_type:{project_type}"]]
    if mc: facets.append([f"versions:{mc}"])
    if loader: facets.append([f"categories:{loader}"])
    return _get("/search",{"query":query,"limit":limit,"facets":json.dumps(facets)}).get("hits",[])

def project_versions(project, mc=None, loader=None):
    params={"include_changelog":"false"}
    if mc: params["game_versions"]=json.dumps([mc])
    if loader: params["loaders"]=json.dumps([loader])
    return _get(f"/project/{project}/version",params)

def choose_version(project, mc=None, loader=None):
    versions=project_versions(project,mc,loader)
    versions=[v for v in versions if v.get("status") in (None,"listed")]
    if not versions: raise ModrinthError(f"No compatible Modrinth version found for {project}")
    # API is normally newest-first. Prefer release, then beta/alpha.
    versions.sort(key=lambda v: (v.get("version_type")=="release",v.get("date_published","")),reverse=True)
    return versions[0]

def _primary(v):
    files=v.get("files",[])
    if not files: raise ModrinthError("Version has no downloadable files.")
    return next((f for f in files if f.get("primary")),files[0])

def _download_file(f,dest_dir):
    dest_dir.mkdir(parents=True,exist_ok=True)
    dest=dest_dir/f["filename"]
    r=requests.get(f["url"],stream=True,timeout=90,headers={"User-Agent":UA})
    r.raise_for_status()
    with dest.open("wb") as out:
        for c in r.iter_content(1024*1024):
            if c: out.write(c)
    return dest

def install_mod(project, instance, mc=None, loader=None, dependencies=True, seen=None, version_id=None):
    obj=get_instance(instance)
    mc=mc or obj["version"]
    loader=loader or obj.get("loader")
    seen=seen or set()
    v=_get(f"/version/{version_id}") if version_id else choose_version(project,mc,loader)
    if str(v.get("project_id"))!=str(project) and version_id:
        raise ModrinthError("Selected version belongs to a different project.")
    if mc not in v.get("game_versions",[]) or (loader and loader not in v.get("loaders",[])):
        raise ModrinthError("Selected mod version is incompatible with the instance.")
    if v["id"] in seen: return []
    seen.add(v["id"])
    installed=[]
    f=_primary(v)
    installed.append(_download_file(f,Path(obj["path"])/"minecraft"/"mods"))
    if dependencies:
        for dep in v.get("dependencies",[]):
            if dep.get("dependency_type")!="required": continue
            depid=dep.get("version_id")
            project_id=dep.get("project_id")
            if depid:
                dv=_get(f"/version/{depid}")
                if dv["id"] in seen: continue
                seen.add(dv["id"])
                installed.append(_download_file(_primary(dv),Path(obj["path"])/"minecraft"/"mods"))
            elif project_id:
                installed += install_mod(project_id,instance,mc,loader,True,seen)
    return installed

def remove_mod(name,instance):
    obj=get_instance(instance)
    mods=Path(obj["path"])/"minecraft"/"mods"
    hits=[p for p in mods.glob("*") if name.lower() in p.name.lower()]
    for p in hits: p.unlink()
    return hits

def list_mods(instance):
    obj=get_instance(instance)
    mods=Path(obj["path"])/"minecraft"/"mods"
    return sorted([p for p in mods.glob("*") if p.is_file()])

def _safe_pack_path(value):
    path=PurePosixPath(str(value).replace("\\","/"))
    if path.is_absolute() or not path.parts or any(part in (".","..") for part in path.parts) or ":" in path.parts[0]:
        raise ModrinthError(f"Unsafe modpack path: {value}")
    return Path(*path.parts)

def install_modpack_file(pack, instance):
    obj=get_instance(instance)
    pack=Path(pack)
    if pack.suffix.lower()!=".mrpack":
        raise ModrinthError("Selected file is not an .mrpack.")
    game=Path(obj["path"])/"minecraft"
    with zipfile.ZipFile(pack) as z:
        index=json.loads(z.read("modrinth.index.json"))
        dependencies=index.get("dependencies") or {}
        if dependencies.get("minecraft") != obj["version"]:
            raise ModrinthError("Modpack Minecraft version does not match the target instance.")
        pack_loader=next((name.split("-")[0] for name in ("fabric-loader","quilt-loader","forge","neoforge") if name in dependencies),None)
        if pack_loader and obj.get("loader")!=pack_loader:
            raise ModrinthError(f"Modpack requires {pack_loader}; target instance uses {obj.get('loader') or 'vanilla'}.")
        # Overrides are copied into the game directory.
        for prefix in ("overrides/","client-overrides/"):
            for m in z.infolist():
                if m.filename.startswith(prefix) and not m.is_dir():
                    rel=_safe_pack_path(m.filename[len(prefix):])
                    dest=game/rel; dest.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(m) as src, dest.open("wb") as out: shutil.copyfileobj(src,out)
        for entry in index.get("files",[]):
            env=(entry.get("env") or {}).get("client")
            if env=="unsupported": continue
            downloads=entry.get("downloads") or []
            if not downloads: continue
            rel=_safe_pack_path(entry["path"])
            url=downloads[0]
            if urlparse(url).scheme!="https": raise ModrinthError("Modpack file URLs must use HTTPS.")
            dest=game/rel; dest.parent.mkdir(parents=True,exist_ok=True)
            temporary=dest.with_name(dest.name+".part")
            digest=hashlib.sha512()
            r=requests.get(url,stream=True,timeout=90,headers={"User-Agent":UA}); r.raise_for_status()
            with temporary.open("wb") as out:
                for c in r.iter_content(1024*1024):
                    if c: out.write(c); digest.update(c)
            expected=(entry.get("hashes") or {}).get("sha512")
            if expected and digest.hexdigest().lower()!=expected.lower():
                temporary.unlink(missing_ok=True)
                raise ModrinthError(f"Checksum mismatch for {rel}")
            temporary.replace(dest)
    return index

def install_modpack(project, instance, version_id=None):
    obj=get_instance(instance)
    v=_get(f"/version/{version_id}") if version_id else choose_version(project,obj["version"],None)
    if obj["version"] not in v.get("game_versions",[]):
        raise ModrinthError("Selected modpack version is incompatible with the target instance.")
    f=_primary(v)
    tmp=Path(obj["path"])/".mcli-pack"
    tmp.mkdir(parents=True,exist_ok=True)
    pack=_download_file(f,tmp)
    try:
        return install_modpack_file(pack,instance)
    finally:
        shutil.rmtree(tmp,ignore_errors=True)


def install_content(project, instance, project_type, version_id=None):
    if project_type not in ("resourcepack","shader"):
        raise ModrinthError(f"Unsupported content type: {project_type}")
    obj=get_instance(instance)
    mc=obj["version"]
    v=_get(f"/version/{version_id}") if version_id else choose_version(project,mc,None)
    if version_id and str(v.get("project_id"))!=str(project):
        raise ModrinthError("Selected version belongs to a different project.")
    if mc not in v.get("game_versions",[]):
        raise ModrinthError("Selected content version is incompatible with the instance.")
    f=_primary(v)
    folder="resourcepacks" if project_type=="resourcepack" else "shaderpacks"
    # Instances use their minecraft/ directory as the actual game directory.
    dest=Path(obj["path"])/"minecraft"/folder
    return _download_file(f,dest)

def list_content(instance, project_type):
    obj=get_instance(instance)
    folder="resourcepacks" if project_type=="resourcepack" else "shaderpacks"
    dest=Path(obj["path"])/"minecraft"/folder
    if not dest.exists():
        return []
    return sorted(p for p in dest.iterdir() if p.is_file())

def remove_content(name, instance, project_type):
    obj=get_instance(instance)
    folder="resourcepacks" if project_type=="resourcepack" else "shaderpacks"
    dest=Path(obj["path"])/"minecraft"/folder
    if not dest.exists():
        return []
    hits=[p for p in dest.iterdir() if p.is_file() and name.lower() in p.name.lower()]
    for p in hits:
        p.unlink()
    return hits
