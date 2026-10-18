#ifndef WATERMARK_H
#define WATERMARK_H

#include <stddef.h>

/* Build-time macros. Makefile passes -D__AUTHOR__ and -D__BUILD_TS__; these
 * fallbacks keep the header compiling outside the Theos build. */
#ifndef __AUTHOR__
#define __AUTHOR__ "ndgthuan"
#endif
#ifndef __BUILD_TS__
#define __BUILD_TS__ __DATE__
#endif

/* Plaintext signature, kept in its own Mach-O data section so it survives
 * symbol stripping. */
static const char wm_signature[]
    __attribute__((used, section("__DATA,__author"))) =
    "NoLowBatteryAlert (c) 2026 Nguyen Duong Gia Thuan (ndgthuan) \xE2\x80\x94 Studybase. "
    "Unauthorized redistribution violates copyright.";

/* Build stamp, kept in a second data section. */
static const char wm_build_info[]
    __attribute__((used, section("__DATA,__watermark"))) =
    "build=" __BUILD_TS__ ";author=" __AUTHOR__ ";brand=Studybase;sig=thuan_signed_2026";

/* XOR-encoded author name (UTF-8 of "Nguyen Duong Gia Thuan (ndgthuan)" with
 * diacritics), so the signature survives even if the plaintext strings are
 * patched out. Decode: data[i] ^ key[i % 8]. */
static const unsigned char wm_xor_key[8] = {
    0x3C, 0x7F, 0x11, 0xA4, 0x5E, 0x09, 0xD2, 0x6B
};

static const unsigned char wm_xor_data[39]
    __attribute__((used, section("__DATA,__watermark"))) = {
    0x72, 0x18, 0x64, 0xDD, 0xBF, 0xB2, 0x57, 0x05, 0x1C, 0x3B, 0xD7, 0x14,
    0x98, 0xA8, 0xBC, 0x0C, 0x1C, 0x38, 0x78, 0xC5, 0x7E, 0x5D, 0xBA, 0x1E,
    0xDD, 0xC5, 0xBC, 0xCA, 0x7E, 0x21, 0xBC, 0x0F, 0x5B, 0x0B, 0x79, 0xD1,
    0x3F, 0x67, 0xFB
};

/* Scattered marker strings, emitted into __DATA,__author from several spots. */
__asm__(".pushsection __DATA,__author\n.ascii \"ndgthuan_studybase\"\n.popsection");
__asm__(".pushsection __DATA,__author\n.ascii \"ndgthuan_studybase\"\n.popsection");
__asm__(".pushsection __DATA,__author\n.ascii \"ndgthuan_studybase\"\n.popsection");

static inline __attribute__((unused)) size_t wm_decode(unsigned char *out, size_t cap) {
    size_t n = sizeof(wm_xor_data);
    if (n > cap) {
        n = cap;
    }
    for (size_t i = 0; i < n; i++) {
        out[i] = wm_xor_data[i] ^ wm_xor_key[i % sizeof(wm_xor_key)];
    }
    return n;
}

/* Does nothing visible. Decodes the encoded signature and reads the
 * sections through volatile pointers so the optimizer keeps them. */
static inline __attribute__((unused)) void verify_watermark(void) {
    unsigned char decoded[sizeof(wm_xor_data) + 1];
    size_t n = wm_decode(decoded, sizeof(decoded) - 1);
    decoded[n] = 0;

    volatile const char *touch_sig = wm_signature;
    volatile const char *touch_build = wm_build_info;
    volatile unsigned char sink = 0;
    for (size_t i = 0; i < n; i++) {
        sink ^= decoded[i];
    }
    sink ^= (unsigned char)touch_sig[0] ^ (unsigned char)touch_build[0];
    (void)sink;
}

#endif /* WATERMARK_H */
