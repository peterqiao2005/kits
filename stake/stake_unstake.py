import os
import time
import json
import requests
import bittensor as bt
from dotenv import load_dotenv

from postgre_util import PgsqlStorage

load_dotenv()
sqlObject = PgsqlStorage()

network = "local"
netuid = 0
wallet_path = "~/.bittensor/wallets"
wallet_name = "taocd4_01"
stake_hotkey = "5CsvRJXuR955WojnGMdok1hbhffZyB4N5ocrv82f3p5A2zVp"
# stake_hotkey = "5G1NjW9YhXLadMWajvTkfcJy6up3yH2q1YzMXDTi6ijanChe"


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


def stake():
    # 查询余额
    balance_before = sub.get_balance(wallet.coldkeypub.ss58_address)
    print(f"wallet balance: {balance_before.tao} TAO")
    ### 执行质押
    result = sub.add_stake(wallet=wallet, hotkey_ss58=stake_hotkey, netuid=netuid, amount=balance_before)
    if result:
        print(f"Successfully stake")
        # time.sleep(24)
        # stakeInfos = sub.get_stake_for_coldkey(coldkey_ss58=wallet.coldkeypub.ss58_address)
        # for stake in stakeInfos:
        #     print(f"{wallet_name}, hotkey: {stake.hotkey_ss58}, stake: {stake.stake.tao}")
        #     result = sub.unstake(wallet=wallet, netuid=stake.netuid, hotkey_ss58=stake.hotkey_ss58,
        #                          amount=stake.stake)
        #     # print(f"{wallet_name}, stake remove result: {result}")
        #     balance_after = sub.get_balance(wallet.coldkeypub.ss58_address)
        #     message = f"[质押套利] 钱包:{wallet_name}, 余额1:{balance_before.tao:.6f}, 余额2:{balance_after.tao:.6f}"
        #     # send_wechat_message(message)
        #     print(message)


def unstake_limit_price(netuid, price, stake: bt.StakeInfo):
    subnet = sub.subnet(netuid)
    print(f"当前价格: {subnet.price.tao}")

    if subnet.price.tao > price:
        result = sub.unstake(wallet=wallet, netuid=stake.netuid, hotkey_ss58=stake.hotkey_ss58,
                             amount=stake.stake)
        balance_after = sub.get_balance(wallet.coldkeypub.ss58_address)
        message = f"[取消质押] 钱包:{wallet_name}, 余额:{balance_after.tao:.6f}"
        print(message)
        send_wechat_message(message)


if __name__ == "__main__":
    sub = bt.subtensor(network=network)
    wallet = bt.wallet(name=wallet_name, path=wallet_path)

    wallet.coldkey_file.save_password_to_env(os.getenv(wallet_name.upper()))
    wallet.unlock_coldkey()

    stake()
    
    # stakeInfos = sub.get_stake_for_coldkey(coldkey_ss58=wallet.coldkeypub.ss58_address)
    # while True:
    #     for stake in stakeInfos:
    #         unstake_limit_price(41, 0.14, stake)
    #
    #     time.sleep(2)
