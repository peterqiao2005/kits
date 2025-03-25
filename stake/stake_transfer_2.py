import os
import time
import json
import requests
import bittensor as bt
from dotenv import load_dotenv

from postgre_util import PgsqlStorage

load_dotenv()

netuid = 19
network = "local"
wallet_path = "~/.bittensor/wallets"
wallet_name = "taocd4_01"
target_wallet_name = "validator01"
target_hotkey = "5D5dF5sLt7ZAYvwVYZR2CpEmZvfXdMmKZsgmfb2CKkbBUKkd"
stake_hotkey = "5D5dF5sLt7ZAYvwVYZR2CpEmZvfXdMmKZsgmfb2CKkbBUKkd"


def send_wechat_message(content):
    url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=7ce8365c-2e9b-4af4-bc58-098c7795bf63"
    headers = {"Content-Type": "application/json"}
    data = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }
    requests.post(url, headers=headers, data=json.dumps(data))

def stake_move(wallet):
    stakeInfos = sub.get_stake_for_coldkey(wallet.coldkeypub.ss58_address)
    for stake in stakeInfos:
        if stake.hotkey_ss58 == target_hotkey:
            continue
        print(f"hotkey: {stake.hotkey_ss58}, stake: {stake.stake.tao}")
        result = sub.move_stake(wallet=wallet,
                                origin_hotkey=stake.hotkey_ss58, origin_netuid=stake.netuid,
                                destination_hotkey=target_hotkey, destination_netuid=stake.netuid,
                                amount=stake.stake)
        print(f"stake move result: {result}, stake amount: {stake.stake.tao}")

def stake(wallet):
    # 查询余额
    balance_before = sub.get_balance(wallet.coldkeypub.ss58_address)
    print(f"[开始质押] 钱包:{target_wallet_name}, 余额:{balance_before.tao}")
    ### 执行质押
    result = sub.add_stake(wallet=wallet, hotkey_ss58=target_hotkey, netuid=netuid, amount=balance_before)
    if result:
        stakeInfos = sub.get_stake_for_coldkey(wallet.coldkeypub.ss58_address)
        for stake in stakeInfos:
            if stake.hotkey_ss58 == target_hotkey:
                print(f"[质押成功] 钱包:{target_wallet_name}, 质押数量:{stake.stake.tao:.6f}")


def unstake(wallet):
    stakeInfos = sub.get_stake_for_coldkey(wallet.coldkeypub.ss58_address)
    for stake in stakeInfos:
        # if stake.hotkey_ss58 == stake_hotkey:
        if stake.netuid == 19:
            stake_amount = stake.stake;
            # stake_amount = bt.Balance.from_tao(100);
            result = sub.unstake(wallet=wallet, netuid=stake.netuid, hotkey_ss58=stake.hotkey_ss58,
                                 amount=stake_amount)
            if result:
                message = f"[取消质押] 钱包:{wallet_name}, 解压:{stake_amount.tao:.6f}"
                print(message)


def tarsfer(wallet1, wallet2, transfer_amount):
    transfer_result = sub.transfer(wallet=wallet1, dest=wallet2.coldkeypub.ss58_address,
                                   amount=bt.Balance.from_tao(transfer_amount))
    # print(f"{wallet_name}, transfer_amount: {transfer_amount} TAO, transfer_result: {transfer_result}")
    if transfer_result:
        message = f"[转账成功] 钱包:{wallet_name}, 数量:{transfer_amount:.2f}"
        print(message)


def get_unlock_wallet(name):
    wallet = bt.wallet(name=name, path=wallet_path)
    wallet.coldkey_file.save_password_to_env(os.getenv(name.upper()))
    wallet.unlock_coldkey()
    return wallet


if __name__ == "__main__":
    sub = bt.subtensor(network=network)
    original_wallet = get_unlock_wallet(wallet_name)
    target_wallet = get_unlock_wallet(target_wallet_name)

    # balance1 = sub.get_balance(original_wallet.coldkeypub.ss58_address)
    # print(f"[解压开始] 钱包:{wallet_name}, 余额:{balance1.tao:.6f}")
    # 解质押
    # unstake(original_wallet)
    # # 转账
    # balance2 = sub.get_balance(original_wallet.coldkeypub.ss58_address)
    # print(f"[转账开始] 钱包:{wallet_name}, 余额:{balance2.tao:.6f}")
    # # tarsfer(original_wallet, target_wallet, balance2.tao - balance1.tao - 0.0002)
    # tarsfer(original_wallet, target_wallet, balance2.tao - 0.0002)
    # 质押
    # unstake(target_wallet)
    # stake(target_wallet)
    stake_move(target_wallet)
