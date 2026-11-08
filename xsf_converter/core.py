"""Bounded-memory conversion. Key inference is heuristic, not universal decryption."""
from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
from typing import BinaryIO, Callable

try:
    import numpy as np
except ImportError:
    np = None

HEADER_SIZE = 1116
KEY_SIZE = 128
BLOCK_SIZE = 8 * 1024 * 1024
MAX_SF2 = 0xFFFFFFFF + 8
HEADER_PROBE_SIZE = 2048

class ConversionError(Exception):
    pass

class Cancelled(ConversionError):
    pass

def check(cancel: Callable[[], bool]) -> None:
    if cancel():
        raise Cancelled("ยกเลิกแล้ว")

def exact(f: BinaryIO, offset: int, count: int) -> bytes:
    if offset < 0 or count < 0:
        raise ConversionError("ตำแหน่งข้อมูลไม่ถูกต้อง")
    f.seek(offset)
    data = f.read(count)
    if len(data) != count:
        raise ConversionError("อ่านข้อมูลไม่ครบ ไฟล์อาจเสียหายหรือถูกเปลี่ยนระหว่างทำงาน")
    return data

def xor(data: bytes, key: bytes, offset: int = 0) -> bytes:
    """XOR with phase relative to the payload, never relative to the file."""
    if len(key) != KEY_SIZE:
        raise ConversionError("คีย์ต้องมีขนาด 128 ไบต์")
    phase = offset % KEY_SIZE
    shifted = key[phase:] + key[:phase]
    if np is not None:
        output = np.frombuffer(data, dtype=np.uint8).copy()
        k = np.frombuffer(shifted, dtype=np.uint8)
        full = len(data) // KEY_SIZE * KEY_SIZE
        np.bitwise_xor(output[:full].reshape(-1, KEY_SIZE), k,
                       out=output[:full].reshape(-1, KEY_SIZE))
        np.bitwise_xor(output[full:], k[:len(data) - full], out=output[full:])
        return output.tobytes()
    output = bytearray(len(data))
    for i, value in enumerate(shifted):
        table = bytes(x ^ value for x in range(256))
        output[i::KEY_SIZE] = data[i::KEY_SIZE].translate(table)
    return bytes(output)

@dataclass(frozen=True)
class SoundFontInfo:
    size: int
    presets: int
    instruments: int
    samples: int

@dataclass(frozen=True)
class ConversionResult:
    path: Path
    sha256: str
    info: SoundFontInfo

class Reader:
    def __init__(self, file: BinaryIO, size: int, key: bytes | None = None,
                 source_offset: int = HEADER_SIZE):
        self.file, self.size, self.key = file, size, key
        self.source_offset = source_offset
    def read(self, offset: int, count: int) -> bytes:
        if offset < 0 or count < 0 or offset + count > self.size:
            raise ConversionError("ขนาดข้อมูลอยู่นอกไฟล์ SF2")
        value = exact(self.file, offset + (self.source_offset if self.key else 0), count)
        return xor(value, self.key, offset) if self.key else value

def validate(reader: Reader, cancel: Callable[[], bool] = lambda: False) -> SoundFontInfo:
    h = reader.read(0, 12)
    if (h[:4] != b"RIFF" or h[8:] != b"sfbk"
            or struct.unpack_from("<I", h, 4)[0] != reader.size - 8):
        raise ConversionError("ผลที่ถอดได้ไม่ใช่ SF2 ที่สมบูรณ์")
    def chunks(start: int, end: int):
        count = 0
        while start < end:
            check(cancel)
            if start + 8 > end or count >= 4096:
                raise ConversionError("โครงสร้าง chunk ไม่ถูกต้อง")
            header = reader.read(start, 8)
            length = struct.unpack_from("<I", header, 4)[0]
            next_offset = start + 8 + length + length % 2
            if next_offset > end:
                raise ConversionError("ขนาด chunk ไม่ถูกต้อง")
            yield header[:4], start + 8, length
            start, count = next_offset, count + 1
    lists = {}
    for name, pos, size in chunks(12, reader.size):
        if name == b"LIST":
            if size < 4:
                raise ConversionError("LIST ไม่สมบูรณ์")
            kind = reader.read(pos, 4)
            if kind in lists:
                raise ConversionError("LIST ซ้ำ")
            lists[kind] = (pos + 4, pos + size)
    if not all(k in lists for k in (b"INFO", b"sdta", b"pdta")):
        raise ConversionError("ข้อมูล SF2 ไม่ครบ")
    info = list(chunks(*lists[b"INFO"]))
    version = next((reader.read(p, n) for t, p, n in info if t == b"ifil" and n == 4), None)
    if version is None or struct.unpack_from("<H", version)[0] != 2:
        raise ConversionError("ไม่พบข้อมูลรุ่น SoundFont 2")
    sdta = list(chunks(*lists[b"sdta"]))
    if not any(t == b"smpl" and n % 2 == 0 for t, _, n in sdta):
        raise ConversionError("ไม่พบข้อมูลเสียงตัวอย่าง 16 บิต")
    pd = list(chunks(*lists[b"pdta"]))
    names = [b"phdr", b"pbag", b"pmod", b"pgen", b"inst", b"ibag", b"imod", b"igen", b"shdr"]
    lengths = [38, 4, 10, 4, 22, 4, 10, 4, 46]
    if len(pd) != 9 or any(t != names[i] or n < lengths[i] or n % lengths[i]
                          for i, (t, _, n) in enumerate(pd)):
        raise ConversionError("ตาราง SoundFont ไม่ถูกต้อง")
    for i, terminal in ((0, b"EOP\0"), (4, b"EOI\0"), (8, b"EOS\0")):
        _, p, n = pd[i]
        if reader.read(p + n - lengths[i], 4) != terminal:
            raise ConversionError("ตารางท้าย SoundFont ไม่ถูกต้อง")
    return SoundFontInfo(reader.size, pd[0][2] // 38 - 1,
                         pd[4][2] // 22 - 1, pd[8][2] // 46 - 1)

def find_key(file: BinaryIO, size: int, cancel: Callable[[], bool] = lambda: False,
             status: Callable[[str], None] = lambda _: None) -> tuple[bytes, SoundFontInfo, int]:
    if size < HEADER_SIZE + KEY_SIZE or exact(file, 0, 8) != b"XSTM\x01\0\0\0":
        raise ConversionError("รองรับเฉพาะ XSTM รุ่น 1 แบบที่วิเคราะห์แล้ว")
    payload = size - HEADER_SIZE
    if payload > MAX_SF2 + HEADER_PROBE_SIZE:
        raise ConversionError("เกินขนาดของ RIFF/SF2 แบบ 32 บิต (ประมาณ 4 GiB)")
    # Newer containers place extra metadata before RIFF. Keep the inference
    # origin fixed, then rotate the key when the actual payload start is found.
    probe = exact(file, HEADER_SIZE, min(HEADER_PROBE_SIZE, payload))
    for window in (100000, 65536, 1048576, 4194304):
        check(cancel)
        status(f"กำลังหาคีย์จากข้อมูลท้ายไฟล์ {min(window, payload):,} ไบต์…")
        start = max(0, payload - window)
        tail = exact(file, HEADER_SIZE + start, payload - start)
        key = bytes(Counter(tail[(i - start) % KEY_SIZE::KEY_SIZE]).most_common(1)[0][0]
                    for i in range(KEY_SIZE))
        decoded = xor(probe, key)
        positions = []
        at = decoded.find(b"RIFF")
        while at >= 0:
            if (at + 24 <= len(decoded) and decoded[at+8:at+12] == b"sfbk"
                    and struct.unpack_from("<I", decoded, at+4)[0] + 8 == payload - at):
                positions.append(at)
            at = decoded.find(b"RIFF", at + 1)
        # Known header variants also allow recovery when a statistical key
        # guess is wrong in the RIFF/INFO header. Every candidate is validated.
        for skip in dict.fromkeys(positions + [0, 16, 24]):
            check(cancel)
            length = payload - skip
            if length < 24 or length > MAX_SF2 or skip + 24 > len(probe):
                continue
            phase = skip % KEY_SIZE
            rotated = key[phase:] + key[:phase]
            anchored = bytearray(rotated)
            known = b"RIFF" + struct.pack("<I", length - 8) + b"sfbkLIST"
            cipher = probe[skip:skip+24]
            anchored[:16] = bytes(a ^ b for a, b in zip(cipher[:16], known))
            anchored[20:24] = bytes(a ^ b for a, b in zip(cipher[20:24], b"INFO"))
            for candidate in (rotated, bytes(anchored)):
                try:
                    source_offset = HEADER_SIZE + skip
                    info = validate(Reader(file, length, candidate, source_offset), cancel)
                    return candidate, info, source_offset
                except Cancelled:
                    raise
                except ConversionError:
                    pass
    raise ConversionError("หาคีย์หรือจุดเริ่ม SF2 ที่ตรวจโครงสร้างผ่านไม่ได้ "
                          "กรุณาส่งออกข้อมูลวิเคราะห์เพื่อตรวจรูปแบบเพิ่มเติม")

def convert(source: Path | str, destination: Path | str, *, overwrite: bool = False,
            cancel: Callable[[], bool] = lambda: False,
            progress: Callable[[int, int], None] = lambda *_: None,
            status: Callable[[str], None] = lambda _: None) -> ConversionResult:
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or (destination.exists() and os.path.samefile(source, destination)):
        raise ConversionError("ไฟล์ต้นทางและปลายทางต้องเป็นคนละไฟล์")
    if destination.exists() and not overwrite:
        raise ConversionError("ไฟล์ปลายทางมีอยู่แล้ว")
    temporary = None
    try:
        with source.open("rb") as file:
            before = os.fstat(file.fileno())
            key, info, source_offset = find_key(file, before.st_size, cancel, status)
            digest = hashlib.sha256()
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".xsf-", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                file.seek(source_offset)
                offset = 0
                while offset < info.size:
                    check(cancel)
                    chunk = file.read(min(BLOCK_SIZE, info.size - offset))
                    if not chunk:
                        raise ConversionError("ไฟล์ต้นทางสั้นกว่าขนาดที่ระบุ")
                    decoded = xor(chunk, key, offset)
                    output.write(decoded)
                    digest.update(decoded)
                    offset += len(decoded)
                    progress(offset, info.size)
                output.flush()
                os.fsync(output.fileno())
            after = os.fstat(file.fileno())
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ConversionError("ไฟล์ต้นทางถูกเปลี่ยนระหว่างทำงาน")
        check(cancel)
        with temporary.open("rb") as output:
            validate(Reader(output, temporary.stat().st_size), cancel)
        check(cancel)
        if overwrite:
            os.replace(temporary, destination)
        else:
            # Atomic no-clobber publication; temp is on the same filesystem.
            os.link(temporary, destination)
            temporary.unlink()
        temporary = None
        return ConversionResult(destination, digest.hexdigest(), info)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def diagnostic(source: Path | str, destination: Path | str) -> None:
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or (destination.exists() and os.path.samefile(source, destination)):
        raise ConversionError("ห้ามบันทึกข้อมูลวิเคราะห์ทับต้นทาง")
    with source.open("rb") as f:
        size = os.fstat(f.fileno()).st_size
        n = min(size, 4194304)
        data = dict(format="XSF-diagnostic-v1", name=source.name, size=size,
                    headOffset=0, headBase64=base64.b64encode(exact(f, 0, min(size, 4096))).decode(),
                    tailOffset=size-n, tailBase64=base64.b64encode(exact(f, size-n, n)).decode())
    # Exclusively create diagnostics to avoid overwriting any existing file.
    with destination.open("x", encoding="utf-8") as output:
        json.dump(data, output, ensure_ascii=False)
