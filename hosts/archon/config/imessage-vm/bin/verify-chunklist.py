#!/usr/bin/env python3
"""Verify an Apple recovery image against its .chunklist (per-chunk SHA-256)."""
import hashlib
import struct
import sys

HEADER = struct.Struct("<4sIBBBxQQQ")


def main(chunklist_path: str, image_path: str) -> int:
    data = open(chunklist_path, "rb").read()
    magic, header_size, version, chunk_method, _sig_method, count, offset, _sig_off = HEADER.unpack_from(data)
    if magic != b"CNKL" or header_size != HEADER.size or version != 1 or chunk_method != 1:
        print(f"unsupported chunklist header: {magic!r} {header_size} {version} {chunk_method}")
        return 2
    with open(image_path, "rb") as image:
        for i in range(count):
            size, digest = struct.unpack_from("<I32s", data, offset + i * 36)
            chunk = image.read(size)
            if len(chunk) != size or hashlib.sha256(chunk).digest() != digest:
                print(f"chunk {i} of {count} failed verification")
                return 1
        if image.read(1):
            print("image has trailing data beyond the chunklist")
            return 1
    print(f"OK: {count} chunks verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
