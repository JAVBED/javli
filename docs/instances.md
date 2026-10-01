# Instances

```bash
javli instance create survival release 26.1.2
javli instance launch survival
javli instance list
javli instance info survival
javli instance clone survival survival-copy
javli instance delete survival-copy
```

## Persistent modloaders

Instances can remember Fabric, Quilt, Forge or NeoForge and automatically use that loader on launch.

```bash
javli instance create survival release 1.21.1 --loader fabric
javli instance set survival loader fabric
javli instance set survival loader_version 0.18.4
javli instance launch survival
```

`instance list` shows the configured loader. Modloaders require Mojang-backed versions.

Launch preferences can be supplied by a graphical frontend through the process environment. `MCLI_MEMORY_MB` overrides the maximum heap in MB; `MCLI_RESOLUTION_WIDTH` and `MCLI_RESOLUTION_HEIGHT` fill the version's launch arguments where supported. Values are validated before authentication or downloads begin. `MCLI_JAVA` selects an explicit Java executable; otherwise JAVLI chooses or installs the runtime required by Minecraft metadata.

To install a local Modrinth pack into an existing compatible instance, run `javli modpack install path/to/pack.mrpack --instance survival`. Paths inside the archive are checked before extraction, and downloaded files with SHA-512 hashes are verified.

For a specific Modrinth version, add `--version-id <id>`. CurseForge packs can be installed with `javli modpack install <project-id> --provider curseforge --instance survival`, optionally selecting a file with `--file-id <id>`. CurseForge requires an API key and some pack files may not expose automatic download URLs.
