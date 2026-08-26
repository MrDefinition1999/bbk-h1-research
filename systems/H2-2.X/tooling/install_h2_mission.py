#!/usr/bin/env python3
"""Plan, install, verify, or exactly roll back the Mission H2 FAT patch."""

from __future__ import annotations

import argparse
import builtins
import contextlib
import gzip
import hashlib
import io
import json
import math
import os
import struct
import warnings
from pathlib import Path
from typing import BinaryIO, Iterator


SECTOR_SIZE = 512
SYSTEM_OFFSET = 0x0000F400 * SECTOR_SIZE
USER_OFFSET = 0x000DEC00 * SECTOR_SIZE
EXPECTED_IMAGE_BYTES = 2 * 1024 * 1024 * 1024
EXPECTED_ORIGINAL_SHA256 = (
    "7B44B5403EFBB58E6D34F676DE81D251DA6ABF9E0D1502D900E3012759DE40C7"
)
SYSTEM_TIME_PATH = "/应用/程序/中学时间.bda"
SYSTEM_PAYLOAD_PATH = "/V1GAME.BIN"
USER_DATA_DIR = "/应用/数据/游戏/LYXZ"
USER_DATA_PATH = USER_DATA_DIR + "/DataLib.dat"
USER_INDEX_PATH = USER_DATA_DIR + "/DataLibIndex.dat"
COPY_SIZE = 1024 * 1024
JOURNAL_RECORD_SIZE = 8 + SECTOR_SIZE


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(COPY_SIZE):
            digest.update(chunk)
    return digest.hexdigest().upper()


def validate_image(path: Path) -> None:
    if path.stat().st_size != EXPECTED_IMAGE_BYTES:
        raise ValueError(
            f"H2 image must be {EXPECTED_IMAGE_BYTES} bytes, got {path.stat().st_size}"
        )
    with path.open("rb") as stream:
        for name, offset in (("system", SYSTEM_OFFSET), ("user", USER_OFFSET)):
            stream.seek(offset)
            boot = stream.read(SECTOR_SIZE)
            if len(boot) != SECTOR_SIZE or boot[510:512] != b"\x55\xAA":
                raise ValueError(f"{name} partition has no FAT boot signature")
            if boot[0x36:0x3E] != b"FAT16   ":
                raise ValueError(f"{name} partition is not FAT16")
            if struct.unpack_from("<H", boot, 0x0B)[0] != SECTOR_SIZE:
                raise ValueError(f"{name} partition does not use 512-byte sectors")


def _load_pyfatfs():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            from pyfatfs.PyFatFS import PyFatFS
        except ImportError as error:
            raise SystemExit("install pyfatfs first: python -m pip install pyfatfs") from error
    return PyFatFS


@contextlib.contextmanager
def open_fat(image: Path, offset: int, *, read_only: bool):
    PyFatFS = _load_pyfatfs()
    fs = PyFatFS(
        str(image),
        encoding="gbk",
        offset=offset,
        preserve_case=True,
        read_only=read_only,
        lazy_load=True,
    )
    try:
        yield fs
    finally:
        fs.close()


def free_bytes(fs) -> int:
    return fs.fs.fat.count(0) * fs.fs.bytes_per_cluster


def hash_guest_file(fs, path: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with fs.openbin(path, "r") as stream:
        while chunk := stream.read(COPY_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest().upper()


def source_info(path: Path) -> dict[str, object]:
    return {
        "name": path.name,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def plan(image: Path, wrapper: Path, payload: Path, data: Path, index: Path) -> dict[str, object]:
    validate_image(image)
    inputs = {
        "wrapper": source_info(wrapper),
        "payload": source_info(payload),
        "data": source_info(data),
        "index": source_info(index),
    }
    with open_fat(image, SYSTEM_OFFSET, read_only=True) as system:
        if not system.isfile(SYSTEM_TIME_PATH):
            raise FileNotFoundError(f"native H2 launcher is missing: {SYSTEM_TIME_PATH}")
        native_time_size, native_time_hash = hash_guest_file(system, SYSTEM_TIME_PATH)
        system_free = free_bytes(system)
    with open_fat(image, USER_OFFSET, read_only=True) as user:
        user_free = free_bytes(user)

    required_system = payload.stat().st_size + wrapper.stat().st_size
    required_user = data.stat().st_size + index.stat().st_size + 4 * 32768
    if system_free + native_time_size < required_system:
        raise ValueError("system partition does not have enough free space")
    if user_free < required_user:
        raise ValueError("user partition does not have enough free space")
    return {
        "format": "bbk-h2-mission-install-plan-v1",
        "image": image.name,
        "image_bytes": image.stat().st_size,
        "inputs": inputs,
        "native_launcher": {
            "guest_path": SYSTEM_TIME_PATH,
            "bytes": native_time_size,
            "sha256": native_time_hash,
        },
        "partitions": {
            "system": {"offset": SYSTEM_OFFSET, "free_bytes": system_free},
            "user": {"offset": USER_OFFSET, "free_bytes": user_free},
        },
        "operations": [
            {"partition": "system", "guest_path": SYSTEM_TIME_PATH, "source": wrapper.name},
            {"partition": "system", "guest_path": SYSTEM_PAYLOAD_PATH, "source": payload.name},
            {"partition": "user", "guest_path": USER_DATA_PATH, "source": data.name},
            {"partition": "user", "guest_path": USER_INDEX_PATH, "source": index.name},
        ],
        "status": "ready",
    }


class SectorJournal:
    """Capture every image sector before its first write."""

    def __init__(self, image: Path, output: Path):
        self.image = image
        self.output = output
        self.reader = image.open("rb", buffering=0)
        self.writer = gzip.open(output, "xb", compresslevel=6)
        self.seen: set[int] = set()

    def capture(self, start: int, length: int) -> None:
        if length <= 0:
            return
        first = start // SECTOR_SIZE
        last = (start + length - 1) // SECTOR_SIZE
        for sector in range(first, last + 1):
            if sector in self.seen:
                continue
            self.reader.seek(sector * SECTOR_SIZE)
            original = self.reader.read(SECTOR_SIZE)
            if len(original) != SECTOR_SIZE:
                raise IOError(f"cannot journal sector {sector}")
            self.writer.write(struct.pack("<Q", sector))
            self.writer.write(original)
            self.seen.add(sector)

    def close(self) -> None:
        self.writer.close()
        self.reader.close()


class JournaledImage(io.BufferedRandom):
    def __init__(self, path: Path, journal: SectorJournal):
        self._journal = journal
        super().__init__(io.FileIO(path, "r+"))

    def write(self, data) -> int:
        self._journal.capture(self.tell(), len(data))
        return super().write(data)


@contextlib.contextmanager
def journal_image_opens(image: Path, journal: SectorJournal) -> Iterator[None]:
    real_open = builtins.open
    import pyfatfs.PyFat as pyfat_module

    real_pyfat_open = pyfat_module.open
    target = os.path.normcase(str(image.resolve()))

    def guarded_open(file, mode="r", *args, **kwargs):
        try:
            candidate = os.path.normcase(str(Path(file).resolve()))
        except (OSError, TypeError, ValueError):
            candidate = ""
        if candidate == target and "+" in mode:
            return JournaledImage(image, journal)
        return real_open(file, mode, *args, **kwargs)

    builtins.open = guarded_open
    # PyFat imports ``open`` into its module globals, so changing only the
    # builtins slot after PyFatFS has been imported does not intercept it.
    pyfat_module.open = guarded_open
    try:
        yield
    finally:
        pyfat_module.open = real_pyfat_open
        builtins.open = real_open


def copy_to_guest(fs, source: Path, guest_path: str) -> None:
    with source.open("rb") as input_stream, fs.openbin(guest_path, "wb") as output:
        while chunk := input_stream.read(COPY_SIZE):
            output.write(chunk)


def copy_to_guest_if_changed(fs, source: Path, guest_path: str) -> bool:
    wanted = source_info(source)
    if fs.isfile(guest_path):
        size, digest = hash_guest_file(fs, guest_path)
        if size == wanted["bytes"] and digest == wanted["sha256"]:
            return False
    else:
        fs.create(guest_path)

    # Do not use FatIO's ``wb`` truncation path here.  PyFatFS 1.1.0 frees a
    # truncated file's trailing clusters but fails to terminate the retained
    # cluster, which can cross-link the next file allocated on the volume.
    entry = fs._get_dir_entry(guest_path)
    chain = file_cluster_chain(fs, guest_path)
    needed = max(1, math.ceil(source.stat().st_size / fs.fs.bytes_per_cluster))
    eoc = fs.fs.FAT_CLUSTER_VALUES[fs.fs.fat_type]["END_OF_CLUSTER_MAX"]
    if len(chain) < needed:
        added = fs.fs.allocate_bytes(
            (needed - len(chain)) * fs.fs.bytes_per_cluster
        )
        if chain:
            fs.fs.fat[chain[-1]] = added[0]
        else:
            entry.set_cluster(added[0])
        chain.extend(added)
        fs.fs.flush_fat()
    elif len(chain) > needed:
        trailing = chain[needed:]
        fs.fs.fat[chain[needed - 1]] = eoc
        fs.fs.free_cluster_chain(trailing[0])
        fs.fs.flush_fat()
        chain = chain[:needed]

    with source.open("rb") as input_stream:
        for cluster in chain:
            chunk = input_stream.read(fs.fs.bytes_per_cluster)
            if not chunk:
                break
            fs.fs.write_data_to_cluster(
                chunk, cluster, extend_cluster=False, erase=False
            )
        if input_stream.read(1):
            raise IOError(f"FAT chain allocation was too short for {source}")
    entry.filesize = source.stat().st_size
    fs.fs.update_directory_entry(entry.get_parent_dir())
    return True


def file_cluster_chain(fs, guest_path: str) -> list[int]:
    """Return the on-disk chain for a non-empty guest file."""
    entry = fs._get_dir_entry(guest_path)
    if entry.filesize == 0 or entry.get_cluster() == 0:
        return []
    return list(fs.fs.get_cluster_chain(entry.get_cluster()))


def detach_shared_trailing_chain(
    fs, owner_path: str, protected_path: str
) -> dict[str, object] | None:
    """Repair the precise PyFatFS truncate cross-link seen in old installs.

    Older PyFatFS releases free the tail of a truncated FAT chain without
    changing the last retained cluster to EOC.  A subsequently allocated file
    can then become the apparent tail of the first file.  Only detach a tail
    when the first file's logical size ends exactly where the second file's
    complete chain begins; refuse every less specific overlap.
    """
    if not fs.isfile(owner_path) or not fs.isfile(protected_path):
        return None
    owner_entry = fs._get_dir_entry(owner_path)
    owner_chain = file_cluster_chain(fs, owner_path)
    protected_chain = file_cluster_chain(fs, protected_path)
    needed = max(1, math.ceil(owner_entry.filesize / fs.fs.bytes_per_cluster))
    overlap = set(owner_chain) & set(protected_chain)
    if not overlap:
        return None
    if (
        len(owner_chain) <= needed
        or owner_chain[needed:] != protected_chain
        or set(owner_chain[:needed]) & set(protected_chain)
    ):
        raise ValueError(
            f"refusing to repair unexpected FAT cross-link: {owner_path} and {protected_path}"
        )
    last_owned = owner_chain[needed - 1]
    old_next = fs.fs.fat[last_owned]
    fs.fs.fat[last_owned] = fs.fs.FAT_CLUSTER_VALUES[fs.fs.fat_type][
        "END_OF_CLUSTER_MAX"
    ]
    fs.fs.flush_fat()
    return {
        "owner": owner_path,
        "protected": protected_path,
        "last_owned_cluster": last_owned,
        "detached_next_cluster": old_next,
        "protected_clusters": len(protected_chain),
    }


def verify_distinct_file_chains(fs, paths: tuple[str, ...]) -> None:
    owners: dict[int, str] = {}
    for guest_path in paths:
        entry = fs._get_dir_entry(guest_path)
        chain = file_cluster_chain(fs, guest_path)
        needed = 0 if entry.filesize == 0 else max(
            1, math.ceil(entry.filesize / fs.fs.bytes_per_cluster)
        )
        if len(chain) != needed:
            raise ValueError(
                f"FAT chain length mismatch for {guest_path}: {len(chain)} clusters, expected {needed}"
            )
        for cluster in chain:
            previous = owners.setdefault(cluster, guest_path)
            if previous != guest_path:
                raise ValueError(
                    f"FAT cluster {cluster} is shared by {previous} and {guest_path}"
                )


def restore_journal(image: Path, journal: Path) -> int:
    validate_image(image)
    records = 0
    with image.open("rb+") as output, gzip.open(journal, "rb") as backup:
        while True:
            raw_sector = backup.read(8)
            if not raw_sector:
                break
            if len(raw_sector) != 8:
                raise IOError("truncated H2 Mission journal sector number")
            original = backup.read(SECTOR_SIZE)
            if len(original) != SECTOR_SIZE:
                raise IOError("truncated H2 Mission journal sector data")
            sector = struct.unpack("<Q", raw_sector)[0]
            if sector * SECTOR_SIZE >= EXPECTED_IMAGE_BYTES:
                raise ValueError(f"journal sector is outside the H2 image: {sector}")
            output.seek(sector * SECTOR_SIZE)
            output.write(original)
            records += 1
        output.flush()
        os.fsync(output.fileno())
    return records


def verify_installed(
    image: Path, wrapper: Path, payload: Path, data: Path, index: Path
) -> list[dict[str, object]]:
    expected = {
        SYSTEM_TIME_PATH: source_info(wrapper),
        SYSTEM_PAYLOAD_PATH: source_info(payload),
        USER_DATA_PATH: source_info(data),
        USER_INDEX_PATH: source_info(index),
    }
    verified: list[dict[str, object]] = []
    for offset, paths in (
        (SYSTEM_OFFSET, (SYSTEM_TIME_PATH, SYSTEM_PAYLOAD_PATH)),
        (USER_OFFSET, (USER_DATA_PATH, USER_INDEX_PATH)),
    ):
        with open_fat(image, offset, read_only=True) as fs:
            for guest_path in paths:
                size, digest = hash_guest_file(fs, guest_path)
                wanted = expected[guest_path]
                if size != wanted["bytes"] or digest != wanted["sha256"]:
                    raise ValueError(f"installed file verification failed: {guest_path}")
                verified.append(
                    {"guest_path": guest_path, "bytes": size, "sha256": digest}
                )
    return verified


def install(
    image: Path,
    wrapper: Path,
    payload: Path,
    data: Path,
    index: Path,
    journal_path: Path,
    manifest_path: Path,
    expected_sha256: str,
) -> dict[str, object]:
    report = plan(image, wrapper, payload, data, index)
    before_hash = sha256_file(image)
    if before_hash != expected_sha256.upper():
        raise ValueError(
            f"refusing to patch unexpected image SHA256 {before_hash}; expected {expected_sha256.upper()}"
        )
    if journal_path.exists() or manifest_path.exists():
        raise FileExistsError("journal and manifest outputs must not already exist")
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    journal = SectorJournal(image, journal_path)
    repairs: list[dict[str, object]] = []
    try:
        with journal_image_opens(image, journal):
            with open_fat(image, SYSTEM_OFFSET, read_only=False) as system:
                repair = detach_shared_trailing_chain(
                    system, SYSTEM_TIME_PATH, SYSTEM_PAYLOAD_PATH
                )
                if repair is not None:
                    repairs.append(repair)
                copy_to_guest_if_changed(system, wrapper, SYSTEM_TIME_PATH)
                copy_to_guest_if_changed(system, payload, SYSTEM_PAYLOAD_PATH)
                verify_distinct_file_chains(
                    system, (SYSTEM_TIME_PATH, SYSTEM_PAYLOAD_PATH)
                )
            with open_fat(image, USER_OFFSET, read_only=False) as user:
                user.makedirs(USER_DATA_DIR, recreate=True)
                for source, guest_path in ((data, USER_DATA_PATH), (index, USER_INDEX_PATH)):
                    copy_to_guest_if_changed(user, source, guest_path)
                verify_distinct_file_chains(user, (USER_DATA_PATH, USER_INDEX_PATH))
        if not journal.seen:
            raise RuntimeError("image changed without any captured journal sectors")
        journal.close()
        verified = verify_installed(image, wrapper, payload, data, index)
        after_hash = sha256_file(image)
    except BaseException:
        journal.close()
        restored = restore_journal(image, journal_path)
        if sha256_file(image) != before_hash:
            raise RuntimeError(
                f"installation failed and exact rollback failed after {restored} sectors"
            )
        raise

    report.update(
        {
            "format": "bbk-h2-mission-install-v1",
            "image_sha256_before": before_hash,
            "image_sha256_after": after_hash,
            "journal": {
                "name": journal_path.name,
                "bytes": journal_path.stat().st_size,
                "sha256": sha256_file(journal_path),
                "sectors": len(journal.seen),
                "restores_exact_original_sha256": before_hash,
            },
            "fat_repairs": repairs,
            "verified_files": verified,
            "status": "installed-and-verified",
        }
    )
    manifest_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true")
    modes.add_argument("--install", action="store_true")
    modes.add_argument("--restore", action="store_true")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--wrapper", type=Path)
    parser.add_argument("--payload", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--expected-image-sha256", default=EXPECTED_ORIGINAL_SHA256)
    args = parser.parse_args()

    image = args.image.resolve(strict=True)
    if args.restore:
        if args.journal is None:
            parser.error("--restore requires --journal")
        records = restore_journal(image, args.journal.resolve(strict=True))
        result = {
            "format": "bbk-h2-mission-restore-v1",
            "image": image.name,
            "restored_sectors": records,
            "image_sha256": sha256_file(image),
            "status": "restored",
        }
    else:
        required = {
            "wrapper": args.wrapper,
            "payload": args.payload,
            "data": args.data,
            "index": args.index,
        }
        missing = [f"--{name}" for name, value in required.items() if value is None]
        if missing:
            parser.error(f"{' and '.join(missing)} required")
        paths = {name: value.resolve(strict=True) for name, value in required.items()}
        if args.plan:
            result = plan(image, **paths)
        else:
            if args.journal is None or args.manifest is None:
                parser.error("--install requires --journal and --manifest")
            result = install(
                image,
                **paths,
                journal_path=args.journal.resolve(),
                manifest_path=args.manifest.resolve(),
                expected_sha256=args.expected_image_sha256,
            )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
