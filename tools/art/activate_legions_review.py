"""Activate only the complete reviewed Legions exports in the normal native catalogue.

Public fresh defaults remain a separate approval/merge step. This tool refuses
unrelated catalogue differences and preserves the owner's settings by backup.
"""
import argparse,copy,hashlib,json,os,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.art.legions_redesign_catalogue import ROWS


def atomic_write(path: Path, raw: bytes) -> None:
    """Replace a file only after its same-directory temporary file is complete."""
    path=Path(path)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix=f'.{path.name}.',delete=False) as stream:
            temporary=Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply_transaction(changes: dict[Path, bytes]) -> None:
    """Read originals before writing; restore every attempted target on failure.

    This provides rollback for caught I/O failures, not cross-file crash atomicity.
    Previously absent targets are removed on rollback; existing ones are restored
    with the same atomic replacement used for activation.
    """
    changes={Path(path):raw for path,raw in changes.items()}
    originals={}
    for path,raw in changes.items():
        if not isinstance(raw,bytes):
            raise TypeError(f'Transaction payload must be bytes: {path}')
        try:
            originals[path]=path.read_bytes()
        except FileNotFoundError:
            originals[path]=None
    attempted=[]
    try:
        for path,raw in changes.items():
            attempted.append(path)
            atomic_write(path,raw)
        for path,raw in changes.items():
            if path.read_bytes()!=raw:
                raise OSError(f'Activation readback mismatch: {path}')
    except Exception as original_error:
        failures=[]
        for path in reversed(attempted):
            try:
                original=originals[path]
                if original is None:
                    path.unlink(missing_ok=True)
                    if path.exists():
                        raise OSError(f'Rollback failed to remove: {path}')
                else:
                    atomic_write(path,original)
                    if path.read_bytes()!=original:
                        raise OSError(f'Rollback readback mismatch: {path}')
            except Exception as rollback_error:
                failures.append(f'{path}: {rollback_error!r}')
        if failures:
            raise RuntimeError('Activation failed and rollback failed: '+'; '.join(failures)) from original_error
        raise


def candidate_catalogue(before: bytes) -> tuple[bytes, dict[str, object]]:
    from tools.render import dump_snapshot
    from game.graphics_benchmark import make_fixture
    from render_bridge.protocol import decode,encode,WORLD
    original=dump_snapshot._default_selection
    settings=original()
    settings['visual_packs']=[p for p in settings['visual_packs'] if p!='legions-redesign']+['legions-redesign']
    try:
        dump_snapshot._default_selection=lambda:settings
        fixture=make_fixture('four-player-combat-v1')
        payload=dump_snapshot.build_catalogue(fixture)
        raw=encode(payload,kind=WORLD,tick=fixture.manager.state.tick,frame_index=0)
    finally:dump_snapshot._default_selection=original
    old=decode(before).payload;new=decode(raw).payload
    aa={r['binding']:r for r in old['assets']};bb={r['binding']:r for r in new['assets']}
    expected={'confederacy:'+r[0] for r in ROWS}
    if len(expected)!=26:
        raise ValueError('Expected exactly 26 reviewed Legions bindings')
    if len(aa)!=len(old['assets']) or len(bb)!=len(new['assets']) or set(aa)!=set(bb):
        raise ValueError('Catalogue binding keyset changed or contains duplicate bindings')
    changed={k for k in aa if aa[k]!=bb[k]}
    if changed and changed!=expected:
        raise ValueError(f'Expected exactly the reviewed 26-binding delta or zero: {sorted(changed)}')
    for kind,_,_,_ in ROWS:
        path=ROOT/f'visual_packs/legions-redesign/assets/models/{kind}.mesh.json'
        row=bb.get('confederacy:'+kind)
        if row is None or row.get('path')!=str(path.relative_to(ROOT)):
            raise ValueError(f'Unexpected reviewed mesh path: {kind}')
        if row.get('sha256')!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError(f'Reviewed mesh hash mismatch: {kind}')
    for value in (old,new):
        value.pop('assets');value['metadata'].pop('visual_selection',None)
    if old!=new:
        raise ValueError('Unrelated scene/camera/metadata change')
    return raw,dict(changed_bindings=sorted(changed),unchanged_asset_rows=len(aa)-len(changed),all_other_scene_and_metadata_unchanged=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backup-dir',type=Path,required=True)
    p.add_argument('--activate-owner-settings',action='store_true')
    args=p.parse_args();backup=args.backup_dir.resolve()
    path=ROOT/'assets/cpp/catalogue.snap';before=path.read_bytes()
    raw,receipt=candidate_catalogue(before)
    backups={backup/'catalogue.snap':before}
    changes={}
    if args.activate_owner_settings:
        from render import menus
        settings_path=Path(menus.SETTINGS_PATH)
        original=settings_path.read_bytes()
        saved=json.loads(original)
        # Do not reinterpret an explicitly customized list to make a review work.
        expected=[name for name in menus.DEFAULT_SETTINGS['visual_packs'] if name!='legions-redesign']
        if saved.get('visual_packs') not in (expected,[*expected,'legions-redesign']):
            raise ValueError('Owner has a custom visual pack selection; refusing automatic append')
        current=copy.deepcopy(saved)
        current['visual_packs']=[*expected,'legions-redesign']
        settings_raw=(json.dumps(current,indent=2)+'\n').encode('utf-8')
        actual=json.loads(settings_raw)
        if actual!=current:
            raise ValueError('Serialized owner settings differ from the candidate')
        a=copy.deepcopy(actual);b=copy.deepcopy(saved);a.pop('visual_packs');b.pop('visual_packs')
        if a!=b:
            raise ValueError('Unrelated owner settings change')
        backups[backup/'settings.json']=original
        changes[settings_path]=settings_raw
        receipt.update(owner_settings_only_pack_append=True,owner_pack_count=len(current['visual_packs']))
    changes[path]=raw
    out=ROOT/'artifacts/legions-redesign/normal-game-catalogue.json'
    receipt.update(catalogue_sha256=hashlib.sha256(raw).hexdigest(),backup_directory=str(backup),public_default_activation='pending_owner_appearance_and_merge_approval')
    receipt_raw=(json.dumps(receipt,indent=2)+'\n').encode('utf-8')
    if json.loads(receipt_raw)!=receipt:
        raise ValueError('Serialized activation receipt differs from the candidate')
    changes[out]=receipt_raw
    # All candidates are validated before any backup or activation writes. Keep
    # verified backups even when the activation transaction must roll back.
    backup.mkdir(parents=True,exist_ok=False)
    for backup_path,original in backups.items():
        atomic_write(backup_path,original)
        if backup_path.read_bytes()!=original:
            raise OSError(f'Backup readback mismatch: {backup_path}')
    apply_transaction(changes)
    print(json.dumps(receipt))

if __name__=='__main__':main()
