#!/usr/bin/env python3
"""
The Tower Save Bridge & Decoder CLI Tool
"""

import sys
import os
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.save_bridge_server import pull_save_from_device, run_server, extract_calculator_inputs
from src.nrbf_reader import decode_save_bytes

def cmd_pull(args):
    print(f"Connecting to ADB and pulling save file...")
    try:
        data, dev = pull_save_from_device(args.device)
        out_file = args.output or "saves/playerInfo.dat"
        os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
        with open(out_file, "wb") as f:
            f.write(data)
        print(f"Saved {len(data)} bytes to {out_file} (from device: {dev})")

        if args.decode:
            decoded = decode_save_bytes(data)
            json_file = out_file.rsplit('.', 1)[0] + ".json"
            with open(json_file, "w", encoding="utf-8") as jf:
                json.dump(decoded, jf, indent=2, ensure_ascii=False, default=str)
            print(f"Decoded JSON written to {json_file}")
            
            extracted = extract_calculator_inputs(decoded)
            print("\nPlayer Overview:")
            print(f" - Coins: {extracted['coins']:.2e}")
            print(f" - Gems: {extracted['gems']}")
            print(f" - Stones: {extracted['stones']}")
            print(f" - Highest Coins by Tier: {extracted['highestCoinsEarnedThisTier']}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

def cmd_decode(args):
    input_file = args.file
    if not os.path.exists(input_file):
        print(f"Error: File {input_file} does not exist.")
        sys.exit(1)
    
    with open(input_file, "rb") as f:
        data = f.read()
    
    print(f"Decoding {input_file} ({len(data)} bytes)...")
    decoded = decode_save_bytes(data)
    
    out_json = args.output or (input_file.rsplit('.', 1)[0] + ".json")
    with open(out_json, "w", encoding="utf-8") as jf:
        json.dump(decoded, jf, indent=2, ensure_ascii=False, default=str)
    
    print(f"Successfully decoded! Output saved to: {out_json}")
    extracted = extract_calculator_inputs(decoded)
    print("\nPlayer Summary:")
    print(f" - Coins: {extracted['coins']}")
    print(f" - Gems: {extracted['gems']}")
    print(f" - Stones: {extracted['stones']}")

def cmd_serve(args):
    run_server(args.port)

def main():
    parser = argparse.ArgumentParser(description="The Tower Save Bridge & Decoder CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # pull
    parser_pull = subparsers.add_parser("pull", help="Pull playerInfo.dat from connected ADB emulator/device")
    parser_pull.add_argument("-d", "--device", help="Specific ADB device ID")
    parser_pull.add_argument("-o", "--output", default="saves/playerInfo.dat", help="Output file path")
    parser_pull.add_argument("--decode", action="store_true", default=True, help="Auto decode to JSON")

    # decode
    parser_decode = subparsers.add_parser("decode", help="Decode a local playerInfo.dat file to JSON")
    parser_decode.add_argument("file", help="Path to playerInfo.dat")
    parser_decode.add_argument("-o", "--output", help="Output JSON path")

    # serve
    parser_serve = subparsers.add_parser("serve", help="Run local HTTP Save Bridge server (127.0.0.1:43781)")
    parser_serve.add_argument("-p", "--port", type=int, default=43781, help="Port to listen on (default 43781)")

    args = parser.parse_args()
    if args.command == "pull":
        cmd_pull(args)
    elif args.command == "decode":
        cmd_decode(args)
    elif args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
