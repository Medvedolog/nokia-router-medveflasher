/*
 * Deterministic LZMA1 encoder for Airoha FIP payloads.
 *
 * The Airoha BL31/BL33 payload format is LZMA-Alone with a KNOWN
 * uncompressed size and WITHOUT the LZMA end-of-payload marker (EOPM).
 * Python lzma.FORMAT_ALONE always emits EOPM and merely rewriting the
 * 8-byte size field creates a stream that some liblzma builds reject as
 * corrupt.  LZMA_FILTER_LZMA1EXT is used here specifically to omit EOPM.
 */
#include <lzma.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static uint8_t prop_byte(uint32_t lc, uint32_t lp, uint32_t pb) {
    return (uint8_t)((pb * 5U + lp) * 9U + lc);
}

static void put32le(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)v;
    p[1] = (uint8_t)(v >> 8);
    p[2] = (uint8_t)(v >> 16);
    p[3] = (uint8_t)(v >> 24);
}

static void put64le(uint8_t *p, uint64_t v) {
    for (unsigned i = 0; i < 8; ++i)
        p[i] = (uint8_t)(v >> (8U * i));
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "usage: %s INPUT.raw OUTPUT.lzma DICT_SIZE\n", argv[0]);
        return 2;
    }

    FILE *infile = fopen(argv[1], "rb");
    if (!infile) {
        perror("open input");
        return 2;
    }
    if (fseek(infile, 0, SEEK_END) != 0) return 2;
    long input_len_long = ftell(infile);
    if (input_len_long < 0) return 2;
    if (fseek(infile, 0, SEEK_SET) != 0) return 2;
    size_t input_len = (size_t)input_len_long;
    uint8_t *input = malloc(input_len ? input_len : 1);
    if (!input) return 2;
    if (fread(input, 1, input_len, infile) != input_len) return 2;
    fclose(infile);

    uint32_t dict_size = (uint32_t)strtoul(argv[3], NULL, 0);
    lzma_options_lzma opt;
    if (lzma_lzma_preset(&opt, 6)) return 2;
    opt.dict_size = dict_size;
    opt.lc = 3;
    opt.lp = 0;
    opt.pb = 2;
    opt.mode = LZMA_MODE_NORMAL;
    opt.nice_len = 128;
    opt.mf = LZMA_MF_BT4;
    opt.depth = 0;
    opt.ext_flags = 0; /* IMPORTANT: no EOPM. */
    lzma_set_ext_size(opt, (uint64_t)input_len);

    lzma_filter filters[2] = {
        { LZMA_FILTER_LZMA1EXT, &opt },
        { LZMA_VLI_UNKNOWN, NULL }
    };

    size_t payload_capacity = input_len + input_len / 2 + 1024 * 1024;
    uint8_t *output = malloc(payload_capacity + 13);
    if (!output) return 2;
    size_t payload_len = 0;
    lzma_ret ret = lzma_raw_buffer_encode(
        filters, NULL, input, input_len,
        output + 13, &payload_len, payload_capacity);
    if (ret != LZMA_OK) {
        fprintf(stderr, "lzma_raw_buffer_encode failed: %d\n", (int)ret);
        return 3;
    }

    output[0] = prop_byte(3, 0, 2); /* 0x5d */
    put32le(output + 1, dict_size);
    put64le(output + 5, (uint64_t)input_len);

    FILE *outfile = fopen(argv[2], "wb");
    if (!outfile) {
        perror("open output");
        return 2;
    }
    if (fwrite(output, 1, payload_len + 13, outfile) != payload_len + 13)
        return 2;
    fclose(outfile);

    fprintf(stderr, "raw=%zu compressed=%zu eopm=0\n", input_len, payload_len + 13);
    free(output);
    free(input);
    return 0;
}
