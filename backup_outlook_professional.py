#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

DEFAULT_ORIGEM = Path.home() / "Library" / "Group Containers" / "UBF8T346G9.Office" / "Outlook" / "Outlook 15 Profiles" / "Main Profile"
DEFAULT_DESTINO = Path.home() / "Library" / "CloudStorage" / "OneDrive" / "Outlook-Backups"
DEFAULT_RETENTION_DAYS = 30
DEFAULT_MAX_BACKUPS = 20
DEFAULT_MAX_PRE_RESTORE_BACKUPS = 1
MIN_FREE_SPACE_BYTES = 1024 * 1024 * 1024
SNAPSHOT_PREFIX = "Outlook_Profile_"
STATE_FILENAME = ".outlook_profile_state.json"
RETRY_ERRNOS = {4, 5, 23}
CONFIG_FILENAME = ".env"


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def load_dotenv():
    config_path = Path(os.environ.get("BACKUP_OUTLOOK_CONFIG", Path.home() / "Library" / "Application Support" / "BackupOutlook" / CONFIG_FILENAME))
    if not config_path.exists():
        return
    try:
        lines = config_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise OSError(f"Não foi possível ler a configuração {config_path}: {exc}") from exc
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        try:
            tokens = shlex.split(value, comments=True)
            parsed_value = tokens[0] if tokens else ""
        except ValueError as exc:
            raise ValueError(f"Configuração inválida em {config_path}: {exc}") from exc
        os.environ[key] = os.path.expandvars(os.path.expanduser(parsed_value))


def ensure_source_exists(origem: Path):
    if not origem.exists() or not origem.is_dir():
        raise FileNotFoundError(f"Pasta de origem do Outlook não encontrada: {origem}")


def ensure_outlook_closed():
    result = subprocess.run(
        ["pgrep", "-x", "Microsoft Outlook"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode == 0:
        raise RuntimeError("Feche o Microsoft Outlook antes de fazer backup ou restauração.")


def ensure_destination_exists(destino: Path):
    destino.mkdir(parents=True, exist_ok=True)


def directory_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def profile_signature(path: Path) -> str:
    digest = hashlib.sha256()
    entries = []
    for item in path.rglob("*"):
        try:
            if item.is_file():
                stat = item.stat()
                entries.append(
                    (
                        str(item.relative_to(path)),
                        stat.st_ino,
                        stat.st_size,
                        stat.st_mtime_ns,
                        stat.st_ctime_ns,
                    )
                )
        except OSError:
            continue
    for relative_path, inode, size, modified_ns, changed_ns in sorted(entries):
        digest.update(f"{relative_path}\0{inode}\0{size}\0{modified_ns}\0{changed_ns}\n".encode())
    return digest.hexdigest()


def read_backup_state(destino: Path):
    try:
        with (destino / STATE_FILENAME).open(encoding="utf-8") as state_file:
            return json.load(state_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def write_backup_state(destino: Path, state: dict):
    state_path = destino / STATE_FILENAME
    temporary = state_path.with_name(f".{state_path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as state_file:
            json.dump(state, state_file, indent=2)
            state_file.write("\n")
        os.replace(temporary, state_path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_free_space(path: Path, required_bytes: int, operation: str):
    usage = shutil.disk_usage(path)
    if usage.free < required_bytes:
        required_gb = required_bytes / (1024**3)
        free_gb = usage.free / (1024**3)
        raise OSError(
            f"Espaço insuficiente para {operation}: necessário aproximadamente "
            f"{required_gb:.1f} GB, disponível {free_gb:.1f} GB."
        )


def zip_uncompressed_size(archive: Path) -> int:
    with zipfile.ZipFile(archive) as zip_file:
        return sum(member.file_size for member in zip_file.infolist())


def list_snapshots(destino: Path):
    if not destino.exists():
        return []
    return sorted(
        [
            p
            for p in destino.iterdir()
            if p.name.startswith(SNAPSHOT_PREFIX)
            and ((p.is_file() and p.suffix == ".zip") or p.is_dir())
        ],
        key=lambda p: p.name,
        reverse=True,
    )


def remove_snapshot(snapshot: Path):
    if not snapshot.exists():
        return True
    try:
        if snapshot.is_dir():
            shutil.rmtree(snapshot)
        else:
            snapshot.unlink()
    except OSError as exc:
        log(f"Não foi possível remover {snapshot}: {exc}")
        return False
    return True


def cleanup_by_days(destino: Path, retention_days: int):
    if retention_days <= 0:
        raise ValueError("retention_days precisa ser maior que zero")

    cutoff = datetime.now().timestamp() - (retention_days * 86400)
    for snapshot in list_snapshots(destino):
        try:
            mtime = snapshot.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            log(f"Removendo snapshot expirado: {snapshot}")
            remove_snapshot(snapshot)


def cleanup_by_count(destino: Path, max_backups: int):
    if max_backups <= 0:
        raise ValueError("max_backups precisa ser maior que zero")

    snapshots = list_snapshots(destino)
    extra = snapshots[max_backups:]
    for snapshot in extra:
        log(f"Removendo snapshot excedente: {snapshot}")
        remove_snapshot(snapshot)


def cleanup_pre_restore_backups(origem: Path, keep: int = DEFAULT_MAX_PRE_RESTORE_BACKUPS):
    backups = sorted(
        origem.parent.glob(f"{origem.name}.pre_restore_*.zip"),
        key=lambda path: path.name,
        reverse=True,
    )
    for backup in backups[keep:]:
        log(f"Removendo backup pré-restauração antigo: {backup}")
        remove_snapshot(backup)


def create_zip_archive(src: Path, archive: Path, retries: int = 5, delay: float = 0.5):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            archive.unlink(missing_ok=True)
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zip_file:
                for path in sorted(src.rglob("*")):
                    zip_file.write(path, path.relative_to(src))
            return
        except OSError as exc:
            last_error = exc
            archive.unlink(missing_ok=True)
            if exc.errno not in RETRY_ERRNOS or attempt == retries:
                raise
            log(f"Compactação interrompida, tentativa {attempt}/{retries}. Aguardando {delay}s...")
            time.sleep(delay)
            delay *= 1.5
    raise last_error


def create_atomic_zip_archive(src: Path, destination: Path):
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        create_zip_archive(src, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def validate_zip_member(member_name: str, destination: Path):
    target = (destination / member_name).resolve()
    root = destination.resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"Snapshot ZIP inválido: caminho inseguro {member_name}")


def extract_zip_archive(archive: Path, destination: Path):
    with zipfile.ZipFile(archive) as zip_file:
        for member in zip_file.infolist():
            validate_zip_member(member.filename, destination)
        zip_file.extractall(destination)


def prepare_restore_directory(snapshot: Path, destination: Path):
    if snapshot.is_dir():
        shutil.copytree(snapshot, destination, dirs_exist_ok=False)
    elif snapshot.is_file() and snapshot.suffix == ".zip":
        extract_zip_archive(snapshot, destination)
    else:
        raise ValueError(f"Snapshot inválido: {snapshot}")


def backup_profile(origem: Path, destino: Path, max_backups: int, retention_days: int, force: bool = False):
    ensure_outlook_closed()
    ensure_source_exists(origem)
    ensure_destination_exists(destino)
    signature = profile_signature(origem)
    state = read_backup_state(destino)
    previous_snapshot = Path(state["snapshot"]) if state and state.get("snapshot") else None
    if (
        not force
        and state
        and state.get("source") == str(origem)
        and state.get("signature") == signature
        and previous_snapshot
        and previous_snapshot.exists()
    ):
        log(f"Perfil sem alterações; novo ZIP não será criado: {previous_snapshot}")
        return previous_snapshot

    source_size = directory_size(origem)
    ensure_free_space(
        destino,
        source_size + MIN_FREE_SPACE_BYTES,
        "a criação do snapshot ZIP",
    )

    snapshot_name = f"{SNAPSHOT_PREFIX}{now_stamp()}"
    snapshot_path = destino / f"{snapshot_name}.zip"
    counter = 1
    while snapshot_path.exists():
        snapshot_path = destino / f"{snapshot_name}_{counter}.zip"
        counter += 1

    log(f"Iniciando backup do perfil do Outlook")
    log(f"Origem: {origem}")
    log(f"Destino: {snapshot_path}")

    create_atomic_zip_archive(origem, snapshot_path)

    cleanup_by_days(destino, retention_days)
    cleanup_by_count(destino, max_backups)
    write_backup_state(
        destino,
        {"source": str(origem), "signature": signature, "snapshot": str(snapshot_path)},
    )

    log(f"Backup concluído: {snapshot_path}")
    return snapshot_path


def latest_snapshot(destino: Path):
    snapshots = list_snapshots(destino)
    if not snapshots:
        return None
    return snapshots[0]


def restore_snapshot(snapshot: Path, origem: Path):
    if not snapshot.exists():
        raise FileNotFoundError(f"Snapshot não encontrado: {snapshot}")
    if not snapshot.is_dir() and not (snapshot.is_file() and snapshot.suffix == ".zip"):
        raise ValueError(f"Snapshot inválido: {snapshot}")

    ensure_outlook_closed()
    ensure_source_exists(origem)
    print(f"Atenção: feche o Outlook antes de restaurar para evitar conflitos de arquivo.")
    answer = input(f"Deseja continuar com a restauração do snapshot {snapshot}? [s/N]: ").strip().lower()
    if answer not in {"s", "sim", "y", "yes"}:
        print("Restauração cancelada.")
        return

    stamp = now_stamp()
    backup_current = origem.parent / f"{origem.name}.pre_restore_{stamp}.zip"
    temporary_restore = origem.parent / f".{origem.name}.restore_{stamp}"
    displaced_origin = origem.parent / f".{origem.name}.previous_{stamp}"

    log(f"Salvando cópia atual antes da restauração em: {backup_current}")
    source_size = directory_size(origem)
    snapshot_size = zip_uncompressed_size(snapshot) if snapshot.is_file() else directory_size(snapshot)
    ensure_free_space(
        origem.parent,
        source_size + snapshot_size + MIN_FREE_SPACE_BYTES,
        "a restauração temporária",
    )
    create_atomic_zip_archive(origem, backup_current)

    try:
        prepare_restore_directory(snapshot, temporary_restore)
        if not temporary_restore.is_dir():
            raise ValueError("A restauração não gerou uma pasta válida")

        origem.rename(displaced_origin)
        try:
            temporary_restore.rename(origem)
        except Exception:
            displaced_origin.rename(origem)
            raise
        remove_snapshot(displaced_origin)
        cleanup_pre_restore_backups(origem)
    finally:
        remove_snapshot(temporary_restore)
    log(f"Restauração concluída com sucesso.")
    log(f"Origem restaurada em: {origem}")
    log(f"Backup anterior preservado em: {backup_current}")


def parse_args():
    parser = argparse.ArgumentParser(description="Backup profissional do perfil do Outlook para destino local ou OneDrive.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("help", help="mostra a ajuda do programa")
    backup = subparsers.add_parser("backup", help="cria um snapshot do perfil do Outlook")
    backup.add_argument("--force", action="store_true", help="cria um novo ZIP mesmo sem alterações detectadas")

    restore = subparsers.add_parser("restore", help="restaura um snapshot específico")
    restore.add_argument("snapshot", nargs="?", help="caminho do snapshot a restaurar")

    subparsers.add_parser("list", help="lista snapshots disponíveis")
    subparsers.add_parser("latest", help="mostra o snapshot mais recente")

    restore_latest = subparsers.add_parser("restore-latest", help="restaura automaticamente o último snapshot")
    restore_latest.add_argument("--keep-backup", action="store_true", help=argparse.SUPPRESS)

    cleanup = subparsers.add_parser("cleanup", help="remove snapshots antigos")
    cleanup.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS, help="remove backups mais antigos que X dias")
    cleanup.add_argument("--count", type=int, default=DEFAULT_MAX_BACKUPS, help="mantém apenas os últimos N backups")

    return parser.parse_args()


def main():
    try:
        load_dotenv()
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}")
        return 1

    args = parse_args()
    origem = Path(os.environ.get("ORIGEM", str(DEFAULT_ORIGEM)))
    destino = Path(os.environ.get("DESTINO", str(DEFAULT_DESTINO)))

    if args.command in (None, "help"):
        print("Uso: backup_outlook_professional.py [backup|restore <snapshot>|list|latest|restore-latest|cleanup --days N --count N]")
        return 0

    try:
        if args.command == "backup":
            backup_profile(origem, destino, DEFAULT_MAX_BACKUPS, DEFAULT_RETENTION_DAYS, force=args.force)
            return 0

        if args.command == "restore":
            if not args.snapshot:
                raise ValueError("Informe o caminho do snapshot para restaurar.")
            restore_snapshot(Path(args.snapshot), origem)
            return 0

        if args.command == "latest":
            latest = latest_snapshot(destino)
            if latest is None:
                print(f"Nenhum backup encontrado em {destino}")
                return 0
            print(latest)
            return 0

        if args.command == "restore-latest":
            latest = latest_snapshot(destino)
            if latest is None:
                print(f"Nenhum backup encontrado em {destino}")
                return 0
            restore_snapshot(latest, origem)
            return 0

        if args.command == "list":
            snapshots = list_snapshots(destino)
            if not snapshots:
                print(f"Nenhum backup encontrado em {destino}")
                return 0
            for item in snapshots:
                print(item)
            return 0

        if args.command == "cleanup":
            cleanup_by_days(destino, args.days)
            cleanup_by_count(destino, args.count)
            print(f"Limpeza concluída. Mantendo os últimos {args.count} backups e removendo itens com mais de {args.days} dias.")
            return 0

        print("Comando inválido.")
        return 2

    except FileNotFoundError as exc:
        print(f"Erro: {exc}")
        return 1
    except ValueError as exc:
        print(f"Erro: {exc}")
        return 1
    except Exception as exc:
        print(f"Erro inesperado: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
