"""Byte integrity for qualification evidence; no quality or approval decision."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import stat


def _native(path):
    path=Path(path).absolute()
    value=str(path)
    if os.name=="nt" and not value.startswith("\\\\?\\"):
        value="\\\\?\\UNC\\"+value[2:] if value.startswith("\\\\") else "\\\\?\\"+value
    return Path(value)


def sha256_file(path: Path) -> str:
    digest=hashlib.sha256()
    with _native(path).open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""):
            digest.update(block)
    return digest.hexdigest()


def _linked(path):
    info=path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info,"st_file_attributes",0)&0x400)


def checked_path(root: Path, relative: str) -> Path:
    """Evidence paths use canonical forward slashes and cannot follow links."""
    if type(relative) is not str or not relative or "\\" in relative or ":" in relative or "\0" in relative:
        raise ValueError("Invalid relative evidence path")
    parts=relative.split("/")
    if PurePosixPath(relative).is_absolute() or any(p in ("",".","..") for p in parts):
        raise ValueError("Evidence path must stay inside its root")
    base=_native(root)
    if _linked(base):raise ValueError("Evidence root cannot be a link")
    current=base
    for part in parts:
        current=current/part
        if current.exists() or current.is_symlink():
            if _linked(current):raise ValueError("Evidence cannot follow symbolic links or reparse points")
    if not current.resolve().is_relative_to(base.resolve()):
        raise ValueError("Evidence path escapes its root")
    return current


def file_record(path: Path, root: Path) -> dict:
    path=_native(path)
    relative=path.relative_to(_native(root)).as_posix()
    checked_path(root,relative)
    if not path.is_file():raise ValueError("Evidence is not a regular file: "+relative)
    before=path.stat()
    digest=sha256_file(path)
    after=path.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
        raise ValueError("Evidence changed while hashing: "+relative)
    return {"path":relative,"bytes":after.st_size,"sha256":digest}


def verify_file(root: Path, record: dict) -> dict:
    try:
        if type(record) is not dict or type(record.get("bytes")) is not int or record["bytes"]<0 or \
                type(record.get("sha256")) is not str or not re.fullmatch("[0-9a-f]{64}",record["sha256"]):
            raise ValueError("Malformed evidence record")
        path=checked_path(root,record["path"])
        actual=file_record(path,root)
        if any(actual[key]!=record[key] for key in ("path","bytes","sha256")):
            raise ValueError("Evidence size/hash does not match")
        return {"status":"pass","path":record["path"],"errors":[]}
    except (KeyError,OSError,ValueError) as exc:
        return {"status":"fail","path":record.get("path") if isinstance(record,dict) else None,
                "errors":[str(exc)]}


def inventory_tree(root: Path) -> dict:
    """Inventory all regular bytes; links are errors rather than silently omitted."""
    root=_native(root)
    if not root.is_dir() or _linked(root):raise ValueError("Evidence root must be a regular directory")
    files=[]
    pending=[root]
    while pending:
        directory=pending.pop()
        for path in sorted(directory.iterdir()):
            if _linked(path):raise ValueError("Linked evidence is not archiveable: "+path.name)
            if path.is_dir():pending.append(path)
            elif path.is_file():files.append(file_record(path,root))
            else:raise ValueError("Nonregular evidence is not archiveable: "+path.name)
    files.sort(key=lambda item:item["path"])
    return {"schema_version":1,"kind":"byte_inventory","files":files,
            "total_bytes":sum(item["bytes"] for item in files)}


def verify_inventory(root: Path, inventory: dict) -> dict:
    errors=[]
    records=inventory.get("files") if isinstance(inventory,dict) else None
    if not isinstance(records,list) or inventory.get("schema_version")!=1:
        return {"status":"fail","checked_files":0,"errors":["Malformed byte inventory"]}
    seen=set()
    for record in records:
        result=verify_file(root,record)
        errors.extend(result["errors"])
        name=result["path"]
        if isinstance(name,str):
            if name in seen:errors.append("Duplicate inventory path: "+name)
            seen.add(name)
    if inventory.get("total_bytes")!=sum(r.get("bytes",0) for r in records if isinstance(r,dict) and type(r.get("bytes")) is int):
        errors.append("Inventory total does not match")
    return {"status":"fail" if errors else "pass","checked_files":len(records),"errors":errors}


def read_json(path: Path):
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError("Duplicate JSON key: "+key)
            result[key]=value
        return result
    def invalid(value):raise ValueError("Nonfinite JSON: "+value)
    source=_native(path)
    if source.stat().st_size>256*1024*1024:raise ValueError("Evidence JSON exceeds the 256MiB read bound")
    return json.loads(source.read_text(encoding="utf-8"),object_pairs_hook=pairs,parse_constant=invalid)
