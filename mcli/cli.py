import argparse, json, sys
from pathlib import Path
from .catalog import all_versions, resolve
from .install import install

ERA_TYPES = ["release", "snapshot", "beta", "alpha", "infdev", "indev", "classic", "preclassic"]

def normalize_type(v):
    return {"old_beta":"beta", "old_alpha":"alpha"}.get(v, v)


def _print_source_warnings(errors):
    if errors:
        print("\nSource warnings:", file=sys.stderr)
        for e in errors: print("  "+e,file=sys.stderr)

def cmd_versions(args):
    from .discovery import versions
    rows,errors=versions(args.source,args.type,getattr(args,"historical",False),getattr(args,"query",None))
    limit=getattr(args,"limit",None)
    if limit: rows=rows[:limit]
    print(f'{"VERSION":28} {"ERA":12} {"SOURCE":12} RELEASED')
    print("-"*78)
    for v in rows:
        typ={"old_beta":"beta","old_alpha":"alpha"}.get(v.type,v.type)
        print(f"{v.id:28} {typ:12} {v.source:12} {v.release_time or '-'}")
    print(f"\n{len(rows)} version(s)")
    _print_source_warnings(errors)

def cmd_search(args):
    from .discovery import search_versions
    rows,errors=search_versions(args.query,args.source,args.type)
    rows=rows[:args.limit]
    print(f'{"VERSION":28} {"ERA":12} {"SOURCE":12}')
    print("-"*56)
    for v in rows:
        typ={"old_beta":"beta","old_alpha":"alpha"}.get(v.type,v.type)
        print(f"{v.id:28} {typ:12} {v.source:12}")
    _print_source_warnings(errors)


def cmd_info(args):
    from .discovery import info
    data,errors=info(args.version,args.source)
    if not data:
        raise SystemExit(f"Version not found: {args.version}")
    print(json.dumps(data,indent=2))
    _print_source_warnings(errors)

def cmd_stats(args):
    from .discovery import stats
    data,errors=stats(args.source)
    print("Total:",data["total"])
    print("By source:")
    for k,v in sorted(data["by_source"].items()): print(f"  {k:14} {v}")
    print("By era:")
    for k,v in sorted(data["by_type"].items()): print(f"  {k:14} {v}")
    _print_source_warnings(errors)

def cmd_launch(args):
    v, errors = resolve(args.version, args.source)
    if not v:
        raise SystemExit(f"Version not found: {args.version}")
    wanted = args.era
    actual = normalize_type(v.type)
    # Mojang collapses legacy eras into old_alpha/old_beta, so only reject clear modern mismatches.
    if wanted in ("release","snapshot","beta","alpha") and actual not in (wanted, "archived", "unknown"):
        raise SystemExit(f"{args.version} is catalogued as {actual}, not {wanted}")
    path, meta = install(v)
    print(f"Installed {v.id} from {v.source}")
    selected = next((x for x in ("fabric","forge","neoforge","quilt") if getattr(args,x,False)), None)
    if selected:
        if v.source != "mojang":
            raise SystemExit("Modloaders are supported on Mojang-backed versions, not raw Omniarchive jars.")
        if selected in ("fabric","quilt"):
            from .loader_launch import launch_profile
            proc, lv = launch_profile(selected, v, path, meta, loader_version=args.loader_version)
            print(f"Started {selected} {lv} on Minecraft {v.id} (PID {proc.pid})")
            return
        if selected in ("forge","neoforge"):
            from .loader_launch import launch_installer_profile
            proc, lv, profile = launch_installer_profile(selected, v, path, meta, loader_version=args.loader_version)
            print(f"Started {selected} {lv} on Minecraft {v.id} (PID {proc.pid})")
            return
    if v.source == "omniarchive" and not meta.get("mainClass"):
        from .legacy import launch_legacy
        proc = launch_legacy(v, path)
    else:
        from .launcher import launch
        proc = launch(v, path, meta)
    print(f"Minecraft started (PID {proc.pid})")


def cmd_login(args):
    from .auth import login
    a = login(getattr(args,"alias",None))
    p = a["profile"]
    print(f'Logged in as {p.get("name")} ({p.get("id")})')

def cmd_account(args):
    from .auth import load_account, refresh, logout, list_accounts, use_account, remove_account
    action=args.account_action
    if action=="list":
        active,accounts=list_accounts()
        if not accounts:
            print("No Microsoft accounts saved.")
        for alias,a in accounts.items():
            p=a.get("profile",{})
            marker="*" if alias==active else " "
            print(f'{marker} {alias:18} {p.get("name","Unknown"):18} {p.get("id","")}')
    elif action=="show":
        a=load_account()
        if not a:
            print("No active Microsoft account.")
            return
        p=a.get("profile",{})
        print(f'{p.get("name","Unknown")}  {p.get("id","")}')
    elif action=="use":
        a=use_account(args.alias)
        print("Active account:",a.get("profile",{}).get("name",args.alias))
    elif action=="refresh":
        a=refresh(getattr(args,"alias",None))
        print("Refreshed:",a.get("profile",{}).get("name","Unknown"))
    elif action=="remove":
        a=remove_account(args.alias)
        print("Removed:",a.get("profile",{}).get("name",args.alias))
    elif action=="logout":
        logout()
        print("Active Microsoft account removed from JAVLI.")

def cmd_java(args):
    from .java_manager import installed, install, detect_system, java_major, java_exe, RUNTIMES
    if args.java_action == "list":
        sysjava=detect_system()
        if sysjava:
            print(f"system  Java {java_major(sysjava) or '?'}  {sysjava}")
        for name,home,exe in installed():
            print(f"managed {name:12} {exe}")
    elif args.java_action == "install":
        home=install(args.major, force=args.force)
        print(f"Installed Java {args.major}: {java_exe(home)}")
    elif args.java_action == "path":
        target=RUNTIMES/f"java-{args.major}"
        exe=java_exe(target)
        if exe.exists(): print(exe)
        else: raise SystemExit(f"Managed Java {args.major} is not installed.")

def cmd_instance(args):
    from pathlib import Path
    from .instances import create, get, list_instances, delete, clone, set_value
    if args.instance_action == "create":
        obj=create(args.name,args.era,args.version,args.source,getattr(args,"loader",None),getattr(args,"loader_version",None))
        print(f'Created instance {obj["name"]}: {obj["era"]} {obj["version"]}')
        print(obj["path"])
    elif args.instance_action == "list":
        rows=list_instances()
        if not rows:
            print("No instances.")
        for x in rows:
            loader=x.get("loader","vanilla")
            print(f'{x["name"]:20} {x["era"]:10} {x["version"]:20} {x["source"]:12} {loader}')
    elif args.instance_action == "info":
        print(json.dumps(get(args.name),indent=2))
    elif args.instance_action == "delete":
        delete(args.name,args.keep_files)
        print(f'Deleted instance {args.name}' + (" (files kept)" if args.keep_files else ""))
    elif args.instance_action == "clone":
        obj=clone(args.name,args.destination)
        print(f'Cloned {args.name} -> {obj["name"]}')
    elif args.instance_action == "set":
        obj=set_value(args.name,args.key,args.value)
        print(json.dumps(obj,indent=2))
    elif args.instance_action == "import":
        from .instance_import import inspect, import_instance
        info=inspect(args.path)
        print(f'Detected: {info["launcher"]}')
        print(f'Name: {info["name"]}')
        print(f'Minecraft: {info.get("version") or "unknown"}')
        print(f'Loader: {info.get("loader") or "vanilla"}' + (f' {info.get("loader_version")}' if info.get("loader_version") else ""))
        obj,info=import_instance(args.path,args.name,args.move,args.version,args.data_only)
        print(f'Imported as {obj["name"]}: {obj["version"]}')
        print(obj["path"])
    elif args.instance_action == "launch":
        obj=get(args.name)
        v, errors=resolve(obj["version"],obj["source"])
        if not v:
            raise SystemExit(f'Version not found: {obj["version"]}')
        path,meta=install(v)
        game_dir=Path(obj["path"])/"minecraft"
        loader=obj.get("loader")
        loader_version=obj.get("loader_version")
        if loader:
            if v.source != "mojang":
                raise SystemExit("Modloaders are supported on Mojang-backed versions, not raw Omniarchive jars.")
            if loader in ("fabric","quilt"):
                from .loader_launch import launch_profile
                proc,lv=launch_profile(loader,v,path,meta,game_dir,loader_version)
                print(f'Started {loader} {lv} from instance {args.name} (PID {proc.pid})')
                return
            if loader in ("forge","neoforge"):
                from .loader_launch import launch_installer_profile
                proc,lv,_=launch_installer_profile(loader,v,path,meta,game_dir,loader_version)
                print(f'Started {loader} {lv} from instance {args.name} (PID {proc.pid})')
                return
        if v.source=="omniarchive":
            from .legacy import launch_legacy
            proc=launch_legacy(v,path,game_dir)
        else:
            from .launcher import launch
            proc=launch(v,path,meta,game_dir)
        print(f'Minecraft started from instance {args.name} (PID {proc.pid})')

def cmd_loader(args):
    from .modloaders import install_loader
    result, version=install_loader(args.loader,args.minecraft,args.loader_version)
    print(f"Installed {args.loader} {version} for Minecraft {args.minecraft}")
    print(result)

def _print_mod_search_results(provider, query, hits):
    import shutil
    width=max(72,min(shutil.get_terminal_size((100,24)).columns,140))
    id_width=10
    name_width=max(22,min(36,(width-id_width-8)//2))
    desc_width=max(20,width-id_width-name_width-7)
    def clip(value,n):
        value=" ".join(str(value or "").split())
        return value if len(value)<=n else value[:max(0,n-3)].rstrip()+"..."
    label="CurseForge" if provider=="curseforge" else "Modrinth"
    print(f'\n{label} results for "{query}"\n')
    print(f' {"ID":<{id_width}} {"PROJECT":<{name_width}} DESCRIPTION')
    print(" "+"-"*(width-2))
    for h in hits:
        if provider=="curseforge":
            pid=h.get("id",""); name=h.get("name",""); desc=h.get("summary","")
        else:
            pid=h.get("project_id",""); name=h.get("title",""); desc=h.get("description","")
        print(f' {clip(pid,id_width):<{id_width}} {clip(name,name_width):<{name_width}} {clip(desc,desc_width)}')
    print(f'\n{len(hits)} result{"s" if len(hits)!=1 else ""} · {label}\n')

def cmd_mods(args):
    provider=getattr(args,"provider","modrinth")
    if args.mods_action=="search":
        if provider=="curseforge":
            from .curseforge import search
            hits=search(args.query,6,args.limit,args.minecraft,args.loader)
        else:
            from .modrinth import search
            hits=search(args.query,"mod",args.limit,args.minecraft,args.loader)
        _print_mod_search_results(provider,args.query,hits)
    elif args.mods_action=="install":
        if provider=="curseforge":
            from .curseforge import install_mod
        else:
            from .modrinth import install_mod
        paths=install_mod(args.project,args.instance,args.minecraft,args.loader,not args.no_deps,version_id=args.version_id) if provider=="modrinth" else install_mod(args.project,args.instance,args.minecraft,args.loader,not args.no_deps,file_id=args.file_id)
        for p in paths: print("Installed",p.name)
    elif args.mods_action=="remove":
        from .modrinth import remove_mod
        hits=remove_mod(args.name,args.instance)
        for p in hits: print("Removed",p.name)
        if not hits: print("No matching installed mod.")
    elif args.mods_action=="list":
        from .modrinth import list_mods
        for p in list_mods(args.instance): print(p.name)

def cmd_modpack(args):
    from .modrinth import search, install_modpack, install_modpack_file
    if args.modpack_action=="search":
        hits=search(args.query,"modpack",args.limit,args.minecraft,args.loader)
        for h in hits:
            print(f'{h["project_id"]:10} {h["title"]} — {h.get("description","")}')
    elif args.modpack_action=="install":
        if args.provider=="curseforge":
            from .curseforge import install_modpack as install_curseforge_modpack
            idx=install_curseforge_modpack(args.project,args.instance,args.file_id)
        else:
            idx=(install_modpack_file(args.project,args.instance) if args.project.lower().endswith(".mrpack") and Path(args.project).is_file() else install_modpack(args.project,args.instance,args.version_id))
        print("Installed modpack:",idx.get("name","CurseForge pack" if args.provider=="curseforge" else "Modrinth pack"))
        print("Minecraft:",(idx.get("minecraft") or {}).get("version", "?") if args.provider=="curseforge" else idx.get("dependencies",{}).get("minecraft","?"))

def cmd_content(args):
    from .modrinth import search, install_content, list_content, remove_content
    project_type="resourcepack" if args.command=="resourcepack" else "shader"
    action=args.content_action
    if action=="search":
        hits=search(args.query,project_type,args.limit,args.minecraft,None)
        for h in hits:
            print(f'{h["project_id"]:10} {h["title"]} — {h.get("description","")}')
    elif action=="install":
        path=install_content(args.project,args.instance,project_type,args.version_id)
        print("Installed",path.name)
    elif action=="list":
        for p in list_content(args.instance,project_type):
            print(p.name)
    elif action=="remove":
        hits=remove_content(args.name,args.instance,project_type)
        for p in hits: print("Removed",p.name)
        if not hits: print("No matching installed content.")

def cmd_random(args):
    from .random_launch import launch_random
    v,proc,errors=launch_random(args.source,args.type,args.historical,args.dry_run)
    typ={"old_beta":"beta","old_alpha":"alpha"}.get(v.type,v.type)
    print(f"Random pick: {v.id} [{typ}] via {v.source}")
    if proc:
        print(f"Minecraft started (PID {proc.pid})")
    _print_source_warnings(errors)

def cmd_update(args):
    from .updater import update
    update()

def build_parser():







    p = argparse.ArgumentParser(prog="javli", description="Minecraft Command-Line Launcher")
    sub = p.add_subparsers(dest="command", required=True)

    pu = sub.add_parser("update", help="Update this standalone JAVLI binary from GitHub Releases")
    pu.set_defaults(func=cmd_update)


    pr = sub.add_parser("random")
    pr.add_argument("--source", choices=["auto","mojang","omniarchive"], default="auto")
    pr.add_argument("--type", choices=ERA_TYPES)
    pr.add_argument("--historical", action="store_true")
    pr.add_argument("--dry-run", action="store_true")
    pr.set_defaults(func=cmd_random)




    ps = sub.add_parser("search")
    ps.add_argument("query")
    ps.add_argument("--source", choices=["auto","mojang","omniarchive"], default="auto")
    ps.add_argument("--type", choices=ERA_TYPES)
    ps.add_argument("--limit", type=int, default=25)
    ps.set_defaults(func=cmd_search)

    pst = sub.add_parser("stats")
    pst.add_argument("--source", choices=["auto","mojang","omniarchive"], default="auto")
    pst.set_defaults(func=cmd_stats)


    for content_cmd in ("resourcepack","shader"):
        pc=sub.add_parser(content_cmd)
        cs=pc.add_subparsers(dest="content_action",required=True)
        csearch=cs.add_parser("search"); csearch.add_argument("query"); csearch.add_argument("--minecraft"); csearch.add_argument("--limit",type=int,default=10); csearch.set_defaults(func=cmd_content)
        cinstall=cs.add_parser("install"); cinstall.add_argument("project"); cinstall.add_argument("--instance",required=True); cinstall.add_argument("--version-id"); cinstall.set_defaults(func=cmd_content)
        clist=cs.add_parser("list"); clist.add_argument("--instance",required=True); clist.set_defaults(func=cmd_content)
        crem=cs.add_parser("remove"); crem.add_argument("name"); crem.add_argument("--instance",required=True); crem.set_defaults(func=cmd_content)

    pm = sub.add_parser("mods")
    ms = pm.add_subparsers(dest="mods_action", required=True)
    mss=ms.add_parser("search"); mss.add_argument("query"); mss.add_argument("--minecraft"); mss.add_argument("--loader"); mss.add_argument("--provider",choices=["modrinth","curseforge"],default="modrinth"); mss.add_argument("--limit",type=int,default=10); mss.set_defaults(func=cmd_mods)
    msi=ms.add_parser("install"); msi.add_argument("project"); msi.add_argument("--instance",required=True); msi.add_argument("--minecraft"); msi.add_argument("--loader"); msi.add_argument("--provider",choices=["modrinth","curseforge"],default="modrinth"); msi.add_argument("--version-id"); msi.add_argument("--file-id"); msi.add_argument("--no-deps",action="store_true"); msi.set_defaults(func=cmd_mods)
    msr=ms.add_parser("remove"); msr.add_argument("name"); msr.add_argument("--instance",required=True); msr.set_defaults(func=cmd_mods)
    msl=ms.add_parser("list"); msl.add_argument("--instance",required=True); msl.set_defaults(func=cmd_mods)

    pmp = sub.add_parser("modpack")
    mps=pmp.add_subparsers(dest="modpack_action",required=True)
    mpss=mps.add_parser("search"); mpss.add_argument("query"); mpss.add_argument("--minecraft"); mpss.add_argument("--loader"); mpss.add_argument("--limit",type=int,default=10); mpss.set_defaults(func=cmd_modpack)
    mpsi=mps.add_parser("install"); mpsi.add_argument("project"); mpsi.add_argument("--instance",required=True); mpsi.add_argument("--version-id"); mpsi.add_argument("--file-id"); mpsi.add_argument("--provider",choices=["modrinth","curseforge"],default="modrinth"); mpsi.set_defaults(func=cmd_modpack)


    pld = sub.add_parser("loader")
    pld.add_argument("loader", choices=["fabric","forge","neoforge","quilt"])
    pld.add_argument("minecraft")
    pld.add_argument("--loader-version")
    pld.set_defaults(func=cmd_loader)


    pins = sub.add_parser("instance")
    ins = pins.add_subparsers(dest="instance_action", required=True)

    ic = ins.add_parser("create")
    ic.add_argument("name")
    ic.add_argument("era", choices=ERA_TYPES)
    ic.add_argument("version")
    ic.add_argument("--source", choices=["auto","mojang","omniarchive"], default="auto")
    ic.add_argument("--loader", choices=["fabric","forge","neoforge","quilt"])
    ic.add_argument("--loader-version")
    ic.set_defaults(func=cmd_instance)

    il = ins.add_parser("list")
    il.set_defaults(func=cmd_instance)

    ii = ins.add_parser("info")
    ii.add_argument("name")
    ii.set_defaults(func=cmd_instance)

    iim = ins.add_parser("import")
    iim.add_argument("path")
    iim.add_argument("--name")
    iim.add_argument("--version",help="Minecraft version when launcher metadata does not identify it")
    iim.add_argument("--data-only",action="store_true",help="Copy user game data without launcher tokens or Minecraft binaries")
    mode=iim.add_mutually_exclusive_group()
    mode.add_argument("--copy",action="store_true",help="Copy the source instance (default)")
    mode.add_argument("--move",action="store_true",help="Move the source game directory into javli")
    iim.set_defaults(func=cmd_instance)

    ila = ins.add_parser("launch")
    ila.add_argument("name")
    ila.set_defaults(func=cmd_instance)

    ide = ins.add_parser("delete")
    ide.add_argument("name")
    ide.add_argument("--keep-files", action="store_true")
    ide.set_defaults(func=cmd_instance)

    icl = ins.add_parser("clone")
    icl.add_argument("name")
    icl.add_argument("destination")
    icl.set_defaults(func=cmd_instance)

    ise = ins.add_parser("set")
    ise.add_argument("name")
    ise.add_argument("key", choices=["version","era","source","loader","loader_version"])
    ise.add_argument("value")
    ise.set_defaults(func=cmd_instance)


    pj = sub.add_parser("java")
    pjsub = pj.add_subparsers(dest="java_action", required=True)
    pjl = pjsub.add_parser("list")
    pjl.set_defaults(func=cmd_java)
    pji = pjsub.add_parser("install")
    pji.add_argument("major", type=int, choices=[8, 17, 21, 25])
    pji.add_argument("--force", action="store_true")
    pji.set_defaults(func=cmd_java)
    pjp = pjsub.add_parser("path")
    pjp.add_argument("major", type=int, choices=[8, 17, 21, 25])
    pjp.set_defaults(func=cmd_java)


    pl = sub.add_parser("login")
    pl.add_argument("--alias")
    pl.set_defaults(func=cmd_login)

    pa = sub.add_parser("account")
    pas = pa.add_subparsers(dest="account_action")
    pal=pas.add_parser("list"); pal.set_defaults(func=cmd_account)
    pash=pas.add_parser("show"); pash.set_defaults(func=cmd_account)
    pau=pas.add_parser("use"); pau.add_argument("alias"); pau.set_defaults(func=cmd_account)
    par=pas.add_parser("refresh"); par.add_argument("--alias"); par.set_defaults(func=cmd_account)
    parm=pas.add_parser("remove"); parm.add_argument("alias"); parm.set_defaults(func=cmd_account)
    palo=pas.add_parser("logout"); palo.set_defaults(func=cmd_account)
    pa.set_defaults(func=cmd_account, account_action="show")


    pv = sub.add_parser("versions")
    pv.add_argument("--source", choices=["auto","mojang","omniarchive"], default="auto")
    pv.add_argument("--type", choices=ERA_TYPES)
    pv.add_argument("--historical", action="store_true")
    pv.add_argument("--query")
    pv.add_argument("--limit", type=int)
    pv.set_defaults(func=cmd_versions)

    pi = sub.add_parser("info")
    pi.add_argument("version")
    pi.add_argument("--source", choices=["auto","mojang","omniarchive"], default="auto")
    pi.set_defaults(func=cmd_info)

    for era in ERA_TYPES:
        pe = sub.add_parser(era)
        pe.add_argument("version")
        pe.add_argument("--source", choices=["auto","mojang","omniarchive"], default="auto")
        group=pe.add_mutually_exclusive_group()
        group.add_argument("--fabric", action="store_true")
        group.add_argument("--forge", action="store_true")
        group.add_argument("--neoforge", action="store_true")
        group.add_argument("--quilt", action="store_true")
        pe.add_argument("--loader-version")
        pe.set_defaults(func=cmd_launch, era=era)

    return p

def main():
    args = build_parser().parse_args()
    if args.command != "update":
        try:
            from .updater import prompt_if_update_available
            if prompt_if_update_available():
                print("Update installed. Run your javli command again.")
                return
        except Exception:
            pass
    args.func(args)

if __name__ == "__main__":
    main()
