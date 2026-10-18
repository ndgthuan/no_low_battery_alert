"""Find who consumes the hideLowPowerAlerts default in a dyld shared cache directory.

usage: python analyze_cache.py <dsc_dir> [window_before window_after]
Prints: SpringBoard images, where the key strings live, every call site of the
selector hideLowPowerAlerts inside SpringBoard.framework, and an annotated
disassembly around each call site.
"""
import mmap
import os
import struct
import sys

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_MEM, ARM64_OP_REG

CACHE_BASE = 0x180000000
TARGET_SELECTOR = "hideLowPowerAlerts"
KEY_STRINGS = [b"SBHideLowPowerAlerts\0", b"SBLowBatteryLevel\0", b"SBHideACPower\0"]


class DscDir:
    def __init__(self, path):
        self.files = {}
        self.maps = []  # (vm_addr, size, file_name, file_off)
        for name in sorted(os.listdir(path)):
            if not name.startswith("dyld_shared_cache"):
                continue
            handle = open(os.path.join(path, name), "rb")
            mm = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
            if mm[:7] != b"dyld_v1":
                continue
            self.files[name] = mm
            map_off, map_cnt = struct.unpack("<II", mm[16:24])
            for i in range(map_cnt):
                addr, size, off, _, _ = struct.unpack("<QQQII", mm[map_off + 32 * i:map_off + 32 * i + 32])
                self.maps.append((addr, size, name, off))
        self.maps.sort()
        self.main = self.files["dyld_shared_cache_arm64e"]

    def vm_to_file(self, vm_addr):
        for addr, size, name, off in self.maps:
            if addr <= vm_addr < addr + size:
                return name, off + vm_addr - addr
        return None

    def read(self, vm_addr, length):
        hit = self.vm_to_file(vm_addr)
        if hit is None:
            return b""
        name, off = hit
        return self.files[name][off:off + length]

    def cstr(self, vm_addr):
        raw = self.read(vm_addr, 200).split(b"\0")[0]
        if raw and all(32 <= c < 127 for c in raw):
            return raw.decode("latin1")
        return None

    def ptr(self, vm_addr):
        raw = self.read(vm_addr, 8)
        if len(raw) < 8:
            return 0
        value = struct.unpack("<Q", raw)[0]
        if value >> 63:  # arm64e authenticated rebase: low 32 bits = offset from cache base
            return (value & 0xFFFFFFFF) + CACHE_BASE
        return value & 0xFFFFFFFFF


def list_images(dsc):
    """Return [(load_addr, path)] handling both the old and the new header layouts."""
    main = dsc.main
    old_off, old_cnt = struct.unpack("<II", main[0x18:0x20])
    images = []
    if old_cnt:
        for i in range(old_cnt):
            entry = main[old_off + 32 * i:old_off + 32 * i + 32]
            addr, _, _, path_off, _ = struct.unpack("<QQQII", entry)
            images.append((addr, main[path_off:path_off + 256].split(b"\0")[0].decode()))
    else:
        text_off, text_cnt = struct.unpack("<QQ", main[0x88:0x98])
        for i in range(text_cnt):
            entry = main[text_off + 32 * i:text_off + 32 * i + 32]
            _, addr, _, path_off = struct.unpack("<16sQII", entry)
            images.append((addr, main[path_off:path_off + 256].split(b"\0")[0].decode()))
    return sorted(images)


def parse_sections(dsc, base):
    header = dsc.read(base, 0x10000)
    cmd_count = struct.unpack("<I", header[16:20])[0]
    off = 32
    sections = {}
    segments = {}
    for _ in range(cmd_count):
        cmd, size = struct.unpack("<II", header[off:off + 8])
        if cmd == 0x19:
            seg_name = header[off + 8:off + 24].split(b"\0")[0].decode()
            seg_addr, seg_size = struct.unpack("<QQ", header[off + 24:off + 40])
            segments[seg_name] = (seg_addr, seg_size)
            sect_count = struct.unpack("<I", header[off + 64:off + 68])[0]
            for s in range(sect_count):
                so = off + 72 + 80 * s
                sect_name = header[so:so + 16].split(b"\0")[0].decode()
                addr, sz = struct.unpack("<QQ", header[so + 32:so + 48])
                sections[sect_name] = (addr, sz)
        off += size
    return sections, segments


def decode_adrp(word, pc):
    imm = ((word >> 5) & 0x7FFFF) << 2 | ((word >> 29) & 3)
    if imm & (1 << 20):
        imm -= 1 << 21
    return (pc & ~0xFFF) + (imm << 12)


def find_selref_addrs(dsc, sections, name):
    start, size = sections["__objc_selrefs"]
    hits = []
    for k in range(0, size, 8):
        target = dsc.ptr(start + k)
        if target and dsc.cstr(target) == name:
            hits.append(start + k)
    return hits


def find_call_sites(dsc, sections, selref_addrs):
    """Sites that load the selref (adrp+ldr) or call an objc stub built on it."""
    text_addr, text_size = sections["__text"]
    words = struct.unpack("<%dI" % (text_size // 4), dsc.read(text_addr, text_size))
    wanted = set(selref_addrs)
    wanted_pages = {(a & ~0xFFF) - k * 0x1000 for a in wanted for k in range(10)}
    stubs = {}
    if "__objc_stubs" in sections:
        stub_addr, stub_size = sections["__objc_stubs"]
        stub_words = struct.unpack("<%dI" % (stub_size // 4), dsc.read(stub_addr, stub_size))
        for i, word in enumerate(stub_words):
            if (word & 0x9F000000) == 0x90000000 and i + 1 < len(stub_words):
                reg = word & 31
                page = decode_adrp(word, stub_addr + 4 * i)
                nxt = stub_words[i + 1]
                if (nxt & 0xFFC00000) == 0xF9400000 and ((nxt >> 5) & 31) == reg:
                    if page + (((nxt >> 10) & 0xFFF) << 3) in wanted:
                        stubs[stub_addr + 4 * i] = True
    sites = []
    for i, word in enumerate(words):
        pc = text_addr + 4 * i
        if (word & 0xFC000000) == 0x94000000 and stubs:  # bl
            imm = word & 0x3FFFFFF
            if imm & (1 << 25):
                imm -= 1 << 26
            if pc + imm * 4 in stubs:
                sites.append((pc, "stub call"))
        elif (word & 0x9F000000) == 0x90000000:  # adrp whose page holds a wanted selref
            page = decode_adrp(word, pc)
            if page not in wanted_pages:
                continue
            # the compiler may reuse one adrp for many loads and may split the offset
            # into add + ldr, so follow add-immediate aliases of the page register
            known = {word & 31: page}
            for j in range(i + 1, min(i + 12, len(words))):
                nxt = words[j]
                src = (nxt >> 5) & 31
                dst = nxt & 31
                if (nxt & 0xFF800000) == 0x91000000 and src in known:  # add x, x, #imm (lsl 0 or 12)
                    shift = 12 if (nxt >> 22) & 1 else 0
                    known[dst] = known[src] + (((nxt >> 10) & 0xFFF) << shift)
                elif (nxt & 0xFFC00000) == 0xF9400000 and src in known:  # ldr x, [x, #imm]
                    if known[src] + (((nxt >> 10) & 0xFFF) << 3) in wanted:
                        sites.append((text_addr + 4 * j, "adrp(+add)+ldr selref"))
    return sites


def selector_string_addrs(dsc, name):
    """VM addresses of the selector's C string (start of string only)."""
    needle = name.encode() + b"\0"
    found = []
    for fname, mm in dsc.files.items():
        pos = mm.find(needle)
        while pos != -1:
            if pos == 0 or mm[pos - 1] == 0:
                for addr, size, mname, off in dsc.maps:
                    if mname == fname and off <= pos < off + size:
                        found.append(addr + pos - off)
                        break
            pos = mm.find(needle, pos + 1)
    return found


def find_direct_sites(dsc, sections, string_addrs):
    """Sites where adrp+add materializes the selector string address directly."""
    text_addr, text_size = sections["__text"]
    words = struct.unpack("<%dI" % (text_size // 4), dsc.read(text_addr, text_size))
    wanted = set(string_addrs)
    pages = {a & ~0xFFF for a in wanted}
    sites = []
    for i, word in enumerate(words):
        if (word & 0x9F000000) != 0x90000000:
            continue
        pc = text_addr + 4 * i
        page = decode_adrp(word, pc)
        if page not in pages:
            continue
        reg = word & 31
        for j in range(i + 1, min(i + 12, len(words))):
            nxt = words[j]
            if (nxt & 0xFF800000) == 0x91000000 and ((nxt >> 5) & 31) == reg:
                shift = 12 if (nxt >> 22) & 1 else 0
                if page + (((nxt >> 10) & 0xFFF) << shift) in wanted:
                    sites.append((text_addr + 4 * j, "adrp+add selector string"))
    return sites


def stub_selector_names(dsc, sections):
    names = {}
    if "__objc_stubs" not in sections:
        return names
    stub_addr, stub_size = sections["__objc_stubs"]
    stub_words = struct.unpack("<%dI" % (stub_size // 4), dsc.read(stub_addr, stub_size))
    for i, word in enumerate(stub_words):
        if (word & 0x9F000000) == 0x90000000 and i + 1 < len(stub_words):
            reg = word & 31
            page = decode_adrp(word, stub_addr + 4 * i)
            nxt = stub_words[i + 1]
            if (nxt & 0xFFC00000) == 0xF9400000 and ((nxt >> 5) & 31) == reg:
                ref = page + (((nxt >> 10) & 0xFFF) << 3)
                names[stub_addr + 4 * i] = dsc.cstr(dsc.ptr(ref))
    return names


def annotated_disassembly(dsc, sections, start, end):
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    md.detail = True
    stub_names = stub_selector_names(dsc, sections)
    selref_start, selref_size = sections["__objc_selrefs"]
    class_start, class_size = sections.get("__objc_classrefs", (0, 0))
    regs = {}
    lines = []
    for ins in md.disasm(dsc.read(start, end - start), start):
        ops = ins.operands
        note = ""
        if ins.mnemonic == "adrp":
            regs[ops[0].reg] = ops[1].imm
        elif (ins.mnemonic == "add" and len(ops) == 3 and ops[1].type == ARM64_OP_REG
              and ops[1].reg in regs and ops[2].type == ARM64_OP_IMM):
            value = regs[ops[1].reg] + ops[2].imm
            regs[ops[0].reg] = value
            text = dsc.cstr(value)
            if text and len(text) > 2:
                note = '; "%s"' % text
        elif ins.mnemonic == "ldr" and len(ops) > 1 and ops[1].type == ARM64_OP_MEM and ops[1].mem.base in regs:
            value = regs[ops[1].mem.base] + ops[1].mem.disp
            if selref_start <= value < selref_start + selref_size:
                note = "; sel " + str(dsc.cstr(dsc.ptr(value)))
            elif class_start <= value < class_start + class_size:
                note = "; class ref"
        elif ins.mnemonic in ("bl", "b") and ops[0].imm in stub_names:
            note = "; msgSend " + str(stub_names[ops[0].imm])
        elif ins.mnemonic in ("bl", "b"):
            note = "; -> %x" % ops[0].imm
        lines.append("%x: %s %s %s" % (ins.address, ins.mnemonic, ins.op_str, note))
    return lines


def main():
    dsc_dir = sys.argv[1]
    before = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x60
    after = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x100
    dsc = DscDir(dsc_dir)
    print("cache files:", len(dsc.files), "main size", len(dsc.main))
    images = list_images(dsc)
    print("images:", len(images))
    wanted = [(a, p) for a, p in images if "/SpringBoard" in p and p.endswith(p.split("/")[-1])
              and p.split("/")[-1].startswith("SpringBoard")]
    for addr, path in wanted:
        print("  %x %s" % (addr, path))
    starts = [a for a, _ in images]

    def owner(vm_addr):
        import bisect
        k = bisect.bisect_right(starts, vm_addr) - 1
        return images[k][1] if k >= 0 else None

    for key in KEY_STRINGS:
        for name, mm in dsc.files.items():
            pos = mm.find(key)
            while pos != -1:
                for addr, size, fname, off in dsc.maps:
                    if fname == name and off <= pos < off + size:
                        print("key %-22s in %s at %x  owner=%s" % (key[:-1].decode(), name[-3:], addr + pos - off,
                                                                  owner(addr + pos - off)))
                        break
                pos = mm.find(key, pos + 1)

    sb_path = "/System/Library/PrivateFrameworks/SpringBoard.framework/SpringBoard"
    sb = [a for a, p in images if p == sb_path]
    if not sb:
        print("SpringBoard.framework image not found")
        return
    sections, segments = parse_sections(dsc, sb[0])
    print("SpringBoard sections:", {k: (hex(v[0]), hex(v[1])) for k, v in sections.items()
                                    if k in ("__text", "__objc_selrefs", "__objc_stubs")})
    selref_addrs = find_selref_addrs(dsc, sections, TARGET_SELECTOR)
    print("selref addresses for %s: %s" % (TARGET_SELECTOR, [hex(a) for a in selref_addrs]))
    sites = find_call_sites(dsc, sections, selref_addrs)
    str_addrs = selector_string_addrs(dsc, TARGET_SELECTOR)
    print("selector string addresses:", [hex(a) for a in str_addrs])
    sites += find_direct_sites(dsc, sections, str_addrs)
    print("call sites:", [(hex(pc), kind) for pc, kind in sites])
    for pc, _ in sites:
        print("---- disassembly around %x ----" % pc)
        for line in annotated_disassembly(dsc, sections, pc - before, pc + after):
            print(line)


if __name__ == "__main__":
    main()
