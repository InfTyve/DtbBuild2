#!/usr/bin/env python3
"""
pack_bootimg.py — 打包 Android boot image (header v0/v1/v2)，A-only MTK 设备用。

不依赖 AOSP 工具链，只用标准库。参数默认值取自 Vestel V TAB Z2 (EKVATOR)
原厂 boot.img 头部，其他 MT6765 设备请按实际值修改。

用法:
    python3 pack_bootimg.py --kernel Image.gz --ramdisk ramdisk.gz \
        --dtb dtb --output boot.img
"""

import argparse
import hashlib
import os
import struct
import sys

BOOT_MAGIC = b'ANDROID!'
BOOT_NAME_SIZE = 16
BOOT_ARGS_SIZE = 512
BOOT_EXTRA_ARGS_SIZE = 1024


def pad_to(data: bytes, page: int) -> bytes:
    """按 page 大小做零填充。"""
    rem = len(data) % page
    if rem == 0:
        return data
    return data + b'\0' * (page - rem)


def read_file(path: str) -> bytes:
    with open(path, 'rb') as f:
        return f.read()


def make_os_version(major: int, minor: int, patch: int, year: int, month: int) -> int:
    """组装 os_version 字段: A(7) B(7) C(7) Y(7) M(4)"""
    return ((major & 0x7F) << 25) | ((minor & 0x7F) << 18) | \
           ((patch & 0x7F) << 11) | ((year & 0x7F) << 4) | (month & 0xF)


def build_id_v2(kernel: bytes, ramdisk: bytes, second: bytes,
                recovery_dtbo: bytes, dtb: bytes) -> bytes:
    """header v2 的 id 字段: SHA1(kernel, ramdisk, second, dtbo, dtb)，每段后附长度。"""
    sha = hashlib.sha1()
    for part in (kernel, ramdisk, second, recovery_dtbo, dtb):
        if part is None:
            continue
        sha.update(part)
        sha.update(struct.pack('<I', len(part)))
    return sha.digest() + b'\0' * 12


def pack(args) -> bytes:
    kernel = read_file(args.kernel) if args.kernel else b''
    ramdisk = read_file(args.ramdisk) if args.ramdisk else b''
    second = read_file(args.second) if args.second else b''
    recovery_dtbo = read_file(args.recovery_dtbo) if args.recovery_dtbo else b''
    dtb = read_file(args.dtb) if args.dtb else b''

    page = args.page_size
    if page < 2048 or (page & (page - 1)) != 0:
        sys.exit(f'page_size 必须是 2 的幂且 >= 2048，当前 {page}')

    cmdline = args.cmdline.encode()
    if len(cmdline) > BOOT_ARGS_SIZE - 1:
        sys.exit(f'cmdline 超过 {BOOT_ARGS_SIZE - 1} 字节')
    extra = args.extra_cmdline.encode()
    if len(extra) > BOOT_EXTRA_ARGS_SIZE - 1:
        sys.exit('extra_cmdline 过长')

    header = bytearray()
    header += BOOT_MAGIC
    header += struct.pack('<I', len(kernel))
    header += struct.pack('<I', args.kernel_addr)
    header += struct.pack('<I', len(ramdisk))
    header += struct.pack('<I', args.ramdisk_addr)
    header += struct.pack('<I', len(second))
    header += struct.pack('<I', args.second_addr)
    header += struct.pack('<I', args.tags_addr)
    header += struct.pack('<I', page)
    header += struct.pack('<I', args.header_version)
    header += struct.pack('<I', args.os_version)

    name = args.name.encode()[:BOOT_NAME_SIZE - 1]
    header += name.ljust(BOOT_NAME_SIZE, b'\0')
    header += cmdline.ljust(BOOT_ARGS_SIZE, b'\0')

    if args.header_version == 0:
        # v0 的 id 只覆盖 kernel / ramdisk / second
        header += build_id_v2(kernel, ramdisk, second, b'', b'')
    else:
        header += build_id_v2(kernel, ramdisk, second, recovery_dtbo, dtb)

    header += extra.ljust(BOOT_EXTRA_ARGS_SIZE, b'\0')

    if args.header_version >= 1:
        header += struct.pack('<I', len(recovery_dtbo))
        header += struct.pack('<Q', args.recovery_dtbo_offset)
        header += struct.pack('<I', 1660)  # header_size
    if args.header_version >= 2:
        header += struct.pack('<I', len(dtb))
        header += struct.pack('<Q', args.dtb_addr)

    img = bytearray()
    img += pad_to(bytes(header), page)
    img += pad_to(kernel, page)
    img += pad_to(ramdisk, page)
    if second:
        img += pad_to(second, page)
    if recovery_dtbo:
        img += pad_to(recovery_dtbo, page)
    if dtb:
        img += pad_to(dtb, page)

    # 分区不足时填充到指定大小（部分设备要求整分区写入）
    if args.partition_size and len(img) < args.partition_size:
        img += b'\0' * (args.partition_size - len(img))

    return bytes(img)


def main():
    p = argparse.ArgumentParser(description='Android boot image packer (v0-v2)')
    p.add_argument('--kernel', required=True, help='压缩后的内核 (Image.gz)')
    p.add_argument('--ramdisk', help='ramdisk (gzip cpio)')
    p.add_argument('--second', help='second stage (通常不用)')
    p.add_argument('--recovery-dtbo', dest='recovery_dtbo')
    p.add_argument('--dtb', help='设备树 blob')
    p.add_argument('--output', '-o', default='boot.img')
    p.add_argument('--name', default='')
    p.add_argument('--cmdline', default='bootopt=64S3,32N2,64N2 buildvariant=user')
    p.add_argument('--extra-cmdline', default='')
    p.add_argument('--page-size', type=int, default=2048)
    p.add_argument('--header-version', type=int, default=2, choices=[0, 1, 2])
    p.add_argument('--os-version', type=lambda x: int(x, 0), default=0x16000157,
                   help='原厂值 0x16000157 = Android 11.0.0 / 2021-07')
    p.add_argument('--kernel-addr', type=lambda x: int(x, 0), default=0x40080000)
    p.add_argument('--ramdisk-addr', type=lambda x: int(x, 0), default=0x51B00000)
    p.add_argument('--second-addr', type=lambda x: int(x, 0), default=0x00000000)
    p.add_argument('--tags-addr', type=lambda x: int(x, 0), default=0x47880000)
    p.add_argument('--dtb-addr', type=lambda x: int(x, 0), default=0x47880000)
    p.add_argument('--recovery-dtbo-offset', type=lambda x: int(x, 0), default=0)
    p.add_argument('--partition-size', type=lambda x: int(x, 0), default=0,
                   help='填充到该大小，0 表示不填充')
    args = p.parse_args()

    img = pack(args)
    with open(args.output, 'wb') as f:
        f.write(img)

    print(f'{args.output}: {len(img)} bytes')
    print(f'  kernel   {len(read_file(args.kernel)) if args.kernel else 0}')
    if args.ramdisk:
        print(f'  ramdisk  {len(read_file(args.ramdisk))}')
    if args.dtb:
        print(f'  dtb      {len(read_file(args.dtb))}')
    if args.partition_size:
        pct = len(img) * 100 / args.partition_size
        print(f'  分区占用 {pct:.1f}% / {args.partition_size}')


if __name__ == '__main__':
    main()
