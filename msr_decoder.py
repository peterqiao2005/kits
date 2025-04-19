#!/usr/bin/env python3

def decode_msr_tme(msr_val: int):
    result = {}
    result["TME Enabled (Bit 0)"] = bool(msr_val & (1 << 0))
    result["TME Bypass (Bit 1)"] = bool(msr_val & (1 << 1))
    result["KeyID Bits (Bits 7–12)"] = (msr_val >> 7) & 0x3F
    result["Encryption Algorithm (Bits 14–15)"] = (msr_val >> 14) & 0x3
    result["MK-TME Enabled (Bit 17)"] = bool(msr_val & (1 << 17))
    return result

def decode_msr_seamrr(msr_val: int):
    result = {}
    result["TDX Enabled (Bit 0)"] = bool(msr_val & (1 << 0))
    result["SEAM Loader Enabled (Bit 1)"] = bool(msr_val & (1 << 1))
    result["Reserved (Bits 2–11)"] = (msr_val >> 2) & 0x3FF
    base_raw = (msr_val >> 12) & ((1 << 40) - 1)
    mask_raw = (msr_val >> 52) & 0xFFF
    result["SEAMRR Base (Bits 12–51)"] = hex(base_raw << 12)
    result["SEAMRR Mask (Bits 52–63)"] = hex(mask_raw << 52)
    return result

def decode_msr_keyid(msr_val: int):
    result = {}
    base = (msr_val >> 6) & 0x3FF  # base KeyID (bit 6~15)
    mask = (msr_val >> 52) & 0xFFF  # mask (bit 52~63)
    result["KeyID Base (Bits 6–15)"] = base
    result["KeyID Mask (Bits 52–63)"] = mask
    result["KeyID Usable Range"] = f"{base} ~ {base + mask}"
    return result

def decode_msr(msr_addr: int, msr_val: int):
    result = {"MSR Address": hex(msr_addr)}
    if msr_addr == 0x982:
        result["MSR Type"] = "IA32_TME_ACTIVATE"
        result.update(decode_msr_tme(msr_val))
    elif msr_addr == 0x802:
        result["MSR Type"] = "IA32_SEAMRR"
        result.update(decode_msr_seamrr(msr_val))
    elif msr_addr == 0x1401:
        result["MSR Type"] = "IA32_TME_KEYID_CONFIGURATION"
        result.update(decode_msr_keyid(msr_val))
    else:
        result["MSR Type"] = "Unknown or unsupported MSR"
        result["Raw Value"] = hex(msr_val)
    return result

def main():
    print("MSR 解码工具，支持：0x982（TME）、0x802（SEAMRR）、0x1401（KEYID）")
    while True:
        raw_addr = input("请输入 MSR 地址（如 0x982），或输入 q 退出： ").strip()
        if raw_addr.lower() == 'q':
            break
        raw_val = input("请输入该 MSR 的十六进制值（如 0x1001780000007）： ").strip()
        try:
            msr_addr = int(raw_addr, 16)
            msr_val = int(raw_val, 16)
            decoded = decode_msr(msr_addr, msr_val)
            print("\n--- 解码结果 ---")
            for key, val in decoded.items():
                print(f"{key}: {val}")
            print("----------------\n")
        except ValueError:
            print("输入有误，请输入合法的十六进制地址和值。\n")

if __name__ == "__main__":
    main()
