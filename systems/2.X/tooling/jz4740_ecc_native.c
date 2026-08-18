/* Stream JZ4740 RS parity: stdin is 2048-byte pages, stdout is 36 bytes/page. */
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#define NN 511
#define NROOTS 8
#define DATA_SYMBOLS 503
#define GF_POLY 0x211
#define PAGE_SIZE 2048
#define ECC_BLOCK_SIZE 512
#define PARITY_SIZE 9

static uint16_t alpha_to[NN + 1];
static uint16_t index_of[NN + 1];
static uint16_t terms[NN + 1][NROOTS];

static unsigned modnn(unsigned value)
{
    while (value >= NN) {
        value -= NN;
    }
    return value;
}

static void init_tables(void)
{
    uint16_t genpoly[NROOTS + 1] = { 0 };
    unsigned sr = 1;
    unsigned degree;

    index_of[0] = NN;
    for (unsigned i = 0; i < NN; i++) {
        index_of[sr] = i;
        alpha_to[i] = sr;
        sr <<= 1;
        if (sr & 0x200) {
            sr ^= GF_POLY;
        }
        sr &= NN;
    }
    alpha_to[NN] = 0;

    genpoly[0] = 1;
    for (degree = 0; degree < NROOTS; degree++) {
        unsigned root = degree + 1;
        genpoly[degree + 1] = 1;
        for (unsigned i = degree; i > 0; i--) {
            if (genpoly[i]) {
                genpoly[i] = genpoly[i - 1] ^ alpha_to[modnn(index_of[genpoly[i]] + root)];
            } else {
                genpoly[i] = genpoly[i - 1];
            }
        }
        genpoly[0] = alpha_to[modnn(index_of[genpoly[0]] + root)];
    }
    for (unsigned i = 0; i <= NROOTS; i++) {
        genpoly[i] = index_of[genpoly[i]];
    }

    memset(terms[NN], 0, sizeof(terms[NN]));
    for (unsigned feedback = 0; feedback < NN; feedback++) {
        for (unsigned i = 1; i < NROOTS; i++) {
            terms[feedback][i - 1] = alpha_to[modnn(feedback + genpoly[NROOTS - i])];
        }
        terms[feedback][NROOTS - 1] = alpha_to[modnn(feedback + genpoly[0])];
    }
}

static uint16_t input_symbol(const uint8_t *data, unsigned symbol_index)
{
    unsigned bit = symbol_index * 9;
    unsigned byte = bit >> 3;
    unsigned shift = bit & 7;
    uint32_t value = byte < ECC_BLOCK_SIZE ? data[byte] : 0;
    if (byte + 1 < ECC_BLOCK_SIZE) {
        value |= (uint32_t)data[byte + 1] << 8;
    }
    return (value >> shift) & NN;
}

static void encode_block(const uint8_t *data, uint8_t *output)
{
    uint16_t parity[NROOTS] = { 0 };
    uint16_t next[NROOTS];
    uint16_t packed[NROOTS];

    for (unsigned symbol_index = 0; symbol_index < DATA_SYMBOLS; symbol_index++) {
        uint16_t symbol = symbol_index < 456 ? input_symbol(data, symbol_index) : 0;
        unsigned feedback = index_of[symbol ^ parity[0]];
        for (unsigned i = 1; i < NROOTS; i++) {
            next[i - 1] = parity[i] ^ terms[feedback][i - 1];
        }
        next[NROOTS - 1] = terms[feedback][NROOTS - 1];
        memcpy(parity, next, sizeof(parity));
    }
    for (unsigned i = 0; i < NROOTS; i++) {
        packed[i] = parity[NROOTS - 1 - i] & NN;
    }
    uint32_t par0 = packed[7] | ((uint32_t)packed[6] << 9) |
                    ((uint32_t)packed[5] << 18) | ((uint32_t)(packed[4] & 0x1f) << 27);
    uint32_t par1 = ((packed[4] >> 5) & 0x0f) | ((uint32_t)packed[3] << 4) |
                    ((uint32_t)packed[2] << 13) | ((uint32_t)packed[1] << 22) |
                    ((uint32_t)(packed[0] & 1) << 31);
    output[0] = par0;
    output[1] = par0 >> 8;
    output[2] = par0 >> 16;
    output[3] = par0 >> 24;
    output[4] = par1;
    output[5] = par1 >> 8;
    output[6] = par1 >> 16;
    output[7] = par1 >> 24;
    output[8] = packed[0] >> 1;
}

int main(void)
{
    uint8_t page[PAGE_SIZE];
    uint8_t parity[PARITY_SIZE * (PAGE_SIZE / ECC_BLOCK_SIZE)];

#ifdef _WIN32
    _setmode(_fileno(stdin), _O_BINARY);
    _setmode(_fileno(stdout), _O_BINARY);
#endif
    init_tables();
    for (;;) {
        size_t count = fread(page, 1, sizeof(page), stdin);
        if (count == 0 && feof(stdin)) {
            break;
        }
        if (count != sizeof(page)) {
            fprintf(stderr, "short input page: %zu bytes\n", count);
            return 2;
        }
        for (unsigned block = 0; block < PAGE_SIZE / ECC_BLOCK_SIZE; block++) {
            encode_block(page + block * ECC_BLOCK_SIZE, parity + block * PARITY_SIZE);
        }
        if (fwrite(parity, 1, sizeof(parity), stdout) != sizeof(parity)) {
            fprintf(stderr, "stdout write failed: %s\n", strerror(errno));
            return 3;
        }
        fflush(stdout);
    }
    return ferror(stdin) ? 4 : 0;
}
