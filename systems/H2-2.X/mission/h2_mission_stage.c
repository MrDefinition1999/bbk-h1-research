/* H2 V2.2L compatibility stage for the original H1 V1 Mission payload.
 *
 * The V1 game is fixed at 0x83c00020.  On H2's 32 MiB SDRAM that aliases to
 * 0x81c00020 and overlaps the high-end allocation-record array used by the
 * native H2 heap.  Move that record array below the V1 prefix while Mission
 * runs, then restore the exact native state before returning to the desktop.
 *
 * The generic V1 ABI mapping is shared SDK source.  H2-specific addresses and
 * memory ownership remain in this file; no H1 machine image is used.
 */

#define H1_NATIVE_PREFIX_ADDRESS 0x83c30000u
#define H1_STAGE_ENTRY_SECTION ".text.h2_v1_compat_inner"
static void h2_install_input_compatibility(
    volatile unsigned int *compat,
    const volatile unsigned int *native);
#define H1_STAGE_AFTER_GUI_INSTALL(compat, native) \
    h2_install_input_compatibility((compat), (native))
#define h1_bda_main h2_v1_compat_main
#include "../../../h1-bda-sdk/examples/v2/v1_game_stage.c"
#undef h1_bda_main
#undef H1_STAGE_AFTER_GUI_INSTALL

typedef int (*h2_message_fetch_type)(volatile h1_u32 *);
static volatile h1_u32 h2_native_message_fetch_address;
static volatile h1_u32 h2_horizontal_gpio_previous;
static volatile h1_u32 h2_simulator_mode;
static volatile h1_u32 h2_wake_scan_value;
static volatile h1_u32 h2_wake_messages_remaining;

#define H2_GPIOC_PIN (*(volatile h1_u32 *)0xb0010200u)
#define H2_GPIO_LEFT_MASK (1u << 1)
#define H2_GPIO_RIGHT_MASK (1u << 3)
#define H2_GPIO_HORIZONTAL_MASK (H2_GPIO_LEFT_MASK | H2_GPIO_RIGHT_MASK)
#define H2_IDLE_INSTRUCTION (*(volatile h1_u32 *)0x804c49bcu)

static int h2_poll_horizontal_gpio(volatile h1_u32 *message)
{
    h1_u32 current = H2_GPIOC_PIN & H2_GPIO_HORIZONTAL_MASK;
    h1_u32 changed = current ^ h2_horizontal_gpio_previous;
    h1_u32 mask;

    if (message == (volatile h1_u32 *)0 || changed == 0u) {
        return 0;
    }
    mask = (changed & H2_GPIO_LEFT_MASK) != 0u
        ? H2_GPIO_LEFT_MASK : H2_GPIO_RIGHT_MASK;
    h2_horizontal_gpio_previous =
        (h2_horizontal_gpio_previous & ~mask) | (current & mask);
    message[0] = (current & mask) == 0u ? 0x10u : 0x12u;
    message[1] = mask == H2_GPIO_LEFT_MASK ? 0x69u : 0x6au;
    message[2] = 0u;
    if (h2_simulator_mode != 0u) {
        h2_wake_scan_value =
            mask == H2_GPIO_LEFT_MASK ? 0x3du : 0x3cu;
        h2_wake_messages_remaining = 2u;
    }
    trace_event(TRACE_GUI_BASE | 0x00000856u, current, changed,
        message[0], message[1], 1u);
    return 1;
}

/*
 * Mission drains its 12-byte input messages through V1 GUI+0x854.  The same
 * function family lives at H2 GUI+0x740.  Keep this H2-owned boundary explicit
 * so the seven real H2 keys can be measured and translated without inventing
 * a H1 keyboard in the machine model.
 */
static int h2_message_fetch(volatile h1_u32 *message)
{
    h2_message_fetch_type fetch =
        (h2_message_fetch_type)h2_native_message_fetch_address;
    int result;

    if (fetch == (h2_message_fetch_type)0) {
        return 0;
    }
    result = fetch(message);
    /* H2's original GUI occasionally loses the PC1/PC3 IRQ notification after
     * a foreign V1 application takes over its event loop.  The physical pins
     * still have the correct levels.  Poll only those two documented H2 GPIOs
     * when the native queue is empty, preserving the native pump for every
     * other message and for normal desktop operation after Mission returns. */
    if (h2_poll_horizontal_gpio(message) != 0) {
        return 1;
    }
    if (result != 0 && message != (volatile h1_u32 *)0) {
        h1_u32 original_type = message[0];
        h1_u32 original_value = message[1];
        h1_u32 type = original_type & 0xffffu;
        h1_u32 value = original_value & 0xffffu;

        /* Confirm first arrives through H2's raw keyboard slot.  Its GUI pump
         * can consume that notification without subsequently waking Mission
         * for the queued permanent-key pair, so promote CR immediately to the
         * key-down message Mission expects.  Keep raw Esc unchanged: Mission
         * handles that keyboard event itself as its global Back/exit path. */
        if (type == 0x11u && value == 0x0au) {
            message[0] = 0x10u;
            message[1] = 0x1cu;
        } else if (type == 0x10u || type == 0x12u) {
            h1_u32 mapped = 0u;

            /* GUI+0x854 returns firmware messages, not QEMU keypad numbers.
             * Mission consumes the ordinary 0x10/0x12 press/release pair and
             * compares message[1] with the common GUI scan values (Linux input
             * codes on these two firmware generations).  H2's horizontal,
             * Confirm and Back values already have the required form.  Only
             * the two volume keys need contextual remapping to Up/Down while
             * Mission owns the input boundary. */
            if (h2_wake_messages_remaining != 0u
                && value == h2_wake_scan_value) {
                --h2_wake_messages_remaining;
                message[0] = 0u;
                message[1] = 0u;
            } else switch (value) {
            case 0x69u: mapped = 0x69u; break; /* Left */
            case 0x6au: mapped = 0x6au; break; /* Right */
            case 0x1cu: mapped = 0x1cu; break; /* Confirm */
            case 0x01u: mapped = 0x01u; break; /* Back */
            case 0x3du: mapped = 0x6cu; break; /* Volume- -> Down */
            case 0x3cu: mapped = 0x67u; break; /* Volume+ -> Up */
            default: break;
            }
            if (mapped != 0u) {
                message[1] = mapped;
            }
        }
        if (message[0] != original_type || message[1] != original_value) {
            trace_event(TRACE_GUI_BASE | 0x00000855u, original_type,
                original_value, message[0], message[1], (h1_u32)result);
        }
    }
    return result;
}

static void h2_install_input_compatibility(
    volatile h1_u32 *compat,
    const volatile h1_u32 *native)
{
    h2_native_message_fetch_address = native[0x740u >> 2];
    h2_horizontal_gpio_previous = H2_GPIOC_PIN & H2_GPIO_HORIZONTAL_MASK;
    /* The raw simulator image replaces the unsupported JZ4750L WAIT with a
     * NOP.  Real H2 firmware retains the WAIT instruction, so simulator-only
     * wake-pulse suppression cannot affect physical volume-key behavior. */
    h2_simulator_mode = H2_IDLE_INSTRUCTION == 0u ? 1u : 0u;
    h2_wake_scan_value = 0u;
    h2_wake_messages_remaining = 0u;
    compat[0x854u >> 2] = (h1_u32)h2_message_fetch;
}

#define H2_HEAP_END (*(volatile h1_u32 *)0x8019f410u)
#define H2_HEAP_START (*(volatile h1_u32 *)0x8019f414u)
#define H2_HEAP_RECORD_BOTTOM (*(volatile h1_u32 *)0x8019f418u)
#define H2_HEAP_RECORD_COUNT (*(volatile h1_u32 *)0x8019f41cu)
#define H2_HEAP_CURSOR (*(volatile h1_u32 *)0x8019f420u)

#define H2_NATIVE_HEAP_END 0x81c30000u
#define H2_MISSION_HEAP_END 0x81c00000u
#define H2_HEAP_MAX_RECORDS 2048u
#define H2_HEAP_SNAPSHOT (H1_STAGE_DATA + 0x40u)
#define H2_HEAP_SNAPSHOT_MAGIC 0x48324850u

/*
 * H1 V2's game compositor submits 32-bit BGRA pixels.  H2 normally configures
 * foreground 1 as RGB565 even though its reserved frame arena is large enough
 * for 480x272x4.  Switch only the active Mission interval to the controller's
 * 18/24-bit mode and double the foreground descriptor length.  This lets every
 * native H2 drawing primitive keep its original semantics and is also valid on
 * the physical JZ4750L LCD controller.  The exact native state is restored
 * before the H2 desktop resumes.
 */
#define H2_LCD_BASE 0xb3050000u
#define H2_LCD_CTRL (*(volatile h1_u32 *)(H2_LCD_BASE + 0x030u))
#define H2_LCD_DA1 (*(volatile h1_u32 *)(H2_LCD_BASE + 0x050u))
#define H2_LCD_OSDCTRL (*(volatile h1_u32 *)(H2_LCD_BASE + 0x104u))
#define H2_LCD_ENABLE_BIT 0x00000008u
#define H2_LCD_DISABLE_BIT 0x00000010u
#define H2_LCD_BPP_MASK 0x00000007u
#define H2_LCD_BPP_18_24 0x00000005u
#define H2_SCREEN_WIDTH 480u
#define H2_SCREEN_HEIGHT 272u
#define H2_SCREEN_ARGB_WORDS (H2_SCREEN_WIDTH * H2_SCREEN_HEIGHT)
#define H2_LCD_SNAPSHOT_MAGIC 0x48324c43u

static volatile h1_u32 h2_lcd_snapshot_magic;
static volatile h1_u32 h2_lcd_saved_ctrl;
static volatile h1_u32 h2_lcd_saved_osdctrl;
static volatile h1_u32 h2_lcd_saved_da1;
static volatile h1_u32 h2_lcd_saved_command;

static int h2_enter_argb_screen(void)
{
    volatile h1_u32 *descriptor;
    h1_u32 ctrl = H2_LCD_CTRL;
    h1_u32 da1 = H2_LCD_DA1;

    if (h2_lcd_snapshot_magic == H2_LCD_SNAPSHOT_MAGIC ||
        !(ctrl & H2_LCD_ENABLE_BIT) || (ctrl & H2_LCD_DISABLE_BIT) ||
        da1 >= 0x02000000u || (da1 & 0x1fu) != 0u) {
        return 0;
    }
    descriptor = (volatile h1_u32 *)(0xa0000000u | da1);
    h2_lcd_saved_ctrl = ctrl;
    h2_lcd_saved_osdctrl = H2_LCD_OSDCTRL;
    h2_lcd_saved_da1 = da1;
    h2_lcd_saved_command = descriptor[3];
    h2_lcd_snapshot_magic = H2_LCD_SNAPSHOT_MAGIC;

    H2_LCD_CTRL = ctrl & ~H2_LCD_ENABLE_BIT;
    __asm__ volatile ("sync" ::: "memory");
    descriptor[3] = (descriptor[3] & 0xff000000u) | H2_SCREEN_ARGB_WORDS;
    H2_LCD_OSDCTRL =
        (h2_lcd_saved_osdctrl & ~H2_LCD_BPP_MASK) | H2_LCD_BPP_18_24;
    __asm__ volatile ("sync" ::: "memory");
    H2_LCD_CTRL = (ctrl & ~H2_LCD_BPP_MASK) | H2_LCD_BPP_18_24;
    __asm__ volatile ("sync" ::: "memory");
    return 1;
}

static void h2_restore_native_screen(void)
{
    volatile h1_u32 *descriptor;

    if (h2_lcd_snapshot_magic != H2_LCD_SNAPSHOT_MAGIC) {
        return;
    }
    descriptor = (volatile h1_u32 *)(0xa0000000u | h2_lcd_saved_da1);
    H2_LCD_CTRL = H2_LCD_CTRL & ~H2_LCD_ENABLE_BIT;
    __asm__ volatile ("sync" ::: "memory");
    descriptor[3] = h2_lcd_saved_command;
    H2_LCD_OSDCTRL = h2_lcd_saved_osdctrl;
    __asm__ volatile ("sync" ::: "memory");
    H2_LCD_CTRL = h2_lcd_saved_ctrl;
    h2_lcd_snapshot_magic = 0u;
    __asm__ volatile ("sync" ::: "memory");
}

static int h2_relocate_heap_records(void)
{
    volatile h1_u32 *snapshot = H2_HEAP_SNAPSHOT;
    volatile h1_u32 *old_records;
    volatile h1_u32 *new_records;
    h1_u32 old_end = H2_HEAP_END;
    h1_u32 old_bottom = H2_HEAP_RECORD_BOTTOM;
    h1_u32 count = H2_HEAP_RECORD_COUNT;
    h1_u32 words;

    if (old_end != H2_NATIVE_HEAP_END || count > H2_HEAP_MAX_RECORDS) {
        return 0;
    }
    words = count * 2u;
    if (old_bottom != old_end - words * 4u) {
        return 0;
    }
    if (H2_HEAP_CURSOR >= H2_MISSION_HEAP_END - words * 4u) {
        return 0;
    }

    snapshot[0] = H2_HEAP_SNAPSHOT_MAGIC;
    snapshot[1] = old_end;
    snapshot[2] = H2_HEAP_START;
    snapshot[3] = old_bottom;
    snapshot[4] = count;
    snapshot[5] = H2_HEAP_CURSOR;
    old_records = (volatile h1_u32 *)old_bottom;
    copy_words(snapshot + 8u, old_records, words);

    new_records = (volatile h1_u32 *)(H2_MISSION_HEAP_END - words * 4u);
    copy_words(new_records, old_records, words);
    H2_HEAP_END = H2_MISSION_HEAP_END;
    H2_HEAP_RECORD_BOTTOM = (h1_u32)new_records;
    __asm__ volatile ("sync" ::: "memory");
    return 1;
}

static void h2_restore_heap_records(void)
{
    volatile h1_u32 *snapshot = H2_HEAP_SNAPSHOT;
    volatile h1_u32 *old_records;
    h1_u32 words;

    if (snapshot[0] != H2_HEAP_SNAPSHOT_MAGIC) {
        return;
    }
    words = snapshot[4] * 2u;
    old_records = (volatile h1_u32 *)snapshot[3];
    copy_words(old_records, snapshot + 8u, words);
    H2_HEAP_START = snapshot[2];
    H2_HEAP_END = snapshot[1];
    H2_HEAP_RECORD_BOTTOM = snapshot[3];
    H2_HEAP_RECORD_COUNT = snapshot[4];
    H2_HEAP_CURSOR = snapshot[5];
    snapshot[0] = 0u;
    __asm__ volatile ("sync" ::: "memory");
}

__attribute__((section(".text.h1_bda_entry"), used))
int h1_bda_main(const h1_u8 *game_source, h1_u32 game_size)
{
    int result;

    if (!h2_relocate_heap_records()) {
        return -2;
    }
    if (!h2_enter_argb_screen()) {
        h2_restore_heap_records();
        return -3;
    }
    result = h2_v1_compat_main(game_source, game_size);
    h2_restore_native_screen();
    h2_restore_heap_records();
    return result;
}
