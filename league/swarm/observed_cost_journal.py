"""Owner-private observed price facts, durable independently of SQLite rollback.

Only the existing broker root and its original opened event identify this journal.
Publication is immutable, hash named, fsynced and serialized by a fixed file lock.
No allowance, obligation, settlement, credential or provider call is created here.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

NAME = 'observed-cost-facts-v1'
WITNESS = 'observed-cost-facts-required-v1.json'
LIMIT = 4 * 1024 * 1024
MAX_RECORDS = 10000

class ObservationJournalError(RuntimeError):
    pass

def require(value, reason):
    if not value: raise ObservationJournalError(reason)

def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()

def digest(raw): return hashlib.sha256(raw).hexdigest()

def plain(path, directory=False):
    path=Path(path)
    require(path.is_absolute() and path.resolve()==path and not any(p.is_symlink() for p in (path,*path.parents)),
            'observed cost journal path is not plain')
    st=path.stat()
    require(st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==(0o700 if directory else 0o600)
            and (stat.S_ISDIR(st.st_mode) if directory else stat.S_ISREG(st.st_mode)),
            'observed cost journal owner, type or mode differs')
    return path

def read(path):
    path=plain(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        require(before.st_nlink==1 and before.st_size<=LIMIT, 'observed cost journal file is not bounded and single linked')
        raw=os.read(fd,LIMIT+1);after=os.fstat(fd)
        stamp=lambda st:(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns,st.st_ctime_ns)
        require(stamp(before)==stamp(after) and len(raw)<=LIMIT,'observed cost journal changed during read')
        def pairs(items):
            result={}
            for key,value in items:
                require(key not in result,'duplicate observed cost journal field');result[key]=value
            return result
        value=json.loads(raw,object_pairs_hook=pairs,
                        parse_constant=lambda _:(_ for _ in ()).throw(ObservationJournalError('nonfinite observed cost journal')))
        require(encode(value)==raw,'observed cost journal encoding differs')
        return value,raw
    except (ValueError,TypeError,UnicodeError) as exc:
        raise ObservationJournalError('unreadable observed cost journal') from exc
    finally:os.close(fd)

def identity(root, scope, opened_sha256):
    root=plain(root,directory=True);st=root.stat()
    return {'schema':1,'scope':scope,'opened_sha256':opened_sha256,'broker_root':str(root),
            'broker_identity':{'dev':st.st_dev,'ino':st.st_ino,'uid':st.st_uid,'mode':stat.S_IMODE(st.st_mode)}}

def sync(directory):
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def publish(path,value):
    raw=encode(value);fd,temp=tempfile.mkstemp(prefix='.pending-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        try:os.link(temp,path,follow_symlinks=False)
        except FileExistsError:
            _,old=read(path);require(old==raw,'immutable observed cost journal collision')
        sync(path.parent)
    finally:os.unlink(temp)
    return digest(raw)

def replace_manifest(path, value):
    # Only this completeness index is replaceable; original facts stay immutable.
    # An incomplete publication cannot look like fewer known obligations.
    raw=encode(value);fd,temp=tempfile.mkstemp(prefix='.pending-manifest-',dir=path.parent)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        if path.exists():plain(path)
        os.replace(temp,path);sync(path.parent)
    finally:
        if os.path.exists(temp):os.unlink(temp)

@contextmanager
def locked(root, *, create=False):
    root=plain(root,directory=True);directory=root/NAME
    if create:
        try:directory.mkdir(mode=0o700);sync(root)
        except FileExistsError:pass
    if not directory.exists() and not directory.is_symlink():
        yield None;return
    directory=plain(directory,directory=True);lock=directory/'journal.lock'
    fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW|(os.O_CREAT if create else 0),0o600)
    try:
        plain(lock);st=os.fstat(fd)
        require(st.st_nlink==1,'observed cost journal lock has aliases')
        fcntl.flock(fd,fcntl.LOCK_EX)
        require((lock.stat().st_dev,lock.stat().st_ino)==(st.st_dev,st.st_ino),'observed cost journal lock replaced')
        yield directory
    finally:fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)

def _records(directory, header, *, create=False):
    path=directory/'identity.json'
    if create and not path.exists():publish(path,header)
    actual,_=read(path);require(encode(actual)==encode(header),'observed cost journal is outside its original ledger/scope')
    manifest_path=directory/'manifest.json'
    if create and not manifest_path.exists():
        # A missing index in an established journal is loss, never a fresh start.
        require(set(p.name for p in directory.iterdir())<= {'identity.json','journal.lock'},
                'established observed cost completeness manifest is missing')
        replace_manifest(manifest_path,{'schema':1,'identity':header,'records':[]})
    manifest,_=read(manifest_path)
    require(isinstance(manifest,dict) and set(manifest)=={'schema','identity','records'}
            and type(manifest['schema']) is int and manifest['schema']==1 and encode(manifest['identity'])==encode(header) and isinstance(manifest['records'],list)
            and len(manifest['records'])<=MAX_RECORDS
            and all(isinstance(v,str) and len(v)==64 and all(c in '0123456789abcdef' for c in v) for v in manifest['records'])
            and manifest['records']==sorted(set(manifest['records'])),
            'observed cost completeness manifest differs')
    entries=sorted(directory.iterdir())
    require(len(entries)<=MAX_RECORDS+3,'observed cost journal record bound exceeded; do not discard facts')
    records=[]
    for p in entries:
        if p.name in ('journal.lock','identity.json','manifest.json'):continue
        # Failed/crashed unpublished temporary files are refused conservatively.
        value,raw=read(p)
        require(p.name==digest(raw)+'.json' and isinstance(value,dict)
                and set(value)=={'schema','identity','observed_at','tariff'} and type(value['schema']) is int and value['schema']==1
                and encode(value['identity'])==encode(header),'missing, partial or foreign observed cost journal record')
        records.append((digest(raw),value))
    require(set(manifest['records'])==set(key for key,_ in records),
            'observed cost completeness record set is missing or unpublished')
    return records

def witness(root,directory,header,*,create=False):
    path=Path(root)/WITNESS
    directory=plain(directory,directory=True);st=directory.stat()
    expected={'schema':1,'identity':header,'book_identity':{'dev':st.st_dev,'ino':st.st_ino,'uid':st.st_uid,'mode':stat.S_IMODE(st.st_mode)}}
    if create and not path.exists():
        require(set(p.name for p in directory.iterdir())<= {'journal.lock'},
                'established observed cost book required witness is missing')
        publish(path,expected)
    value,_=read(path)
    require(encode(value)==encode(expected),'observed cost required book identity differs')

def records(root, scope, opened_sha256, *, required=()):
    directory=Path(root)/NAME
    if not directory.exists() and not directory.is_symlink():
        require(not required and not (Path(root)/WITNESS).exists() and not (Path(root)/WITNESS).is_symlink(),
                'required observed cost journal is missing');return []
    header=identity(root,scope,opened_sha256)
    with locked(root) as directory:
        witness(root,directory,header)
        if directory is None:
            require(not required,'required observed cost journal is missing');return []
        result=_records(directory,header)
        require(set(required)<=set(key for key,_ in result),'required observed cost facts are missing')
        return result

def append(root, scope, opened_sha256, observed_at, tariff, *, needed):
    header=identity(root,scope,opened_sha256)
    with locked(root,create=True) as directory:
        witness(root,directory,header,create=True)
        previous=_records(directory,header,create=True)
        if not needed(previous):return None
        value={'schema':1,'identity':header,'observed_at':observed_at,'tariff':tariff}
        require(len(previous)<MAX_RECORDS,'observed cost fact limit reached; do not discard retained prices')
        key=digest(encode(value));publish(directory/(key+'.json'),value)
        replace_manifest(directory/'manifest.json',{'schema':1,'identity':header,'records':sorted({key,*[old for old,_ in previous]})})
        return key
