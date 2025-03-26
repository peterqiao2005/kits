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
wallet_path = "~/.bittensor/wallets"
wallet_names = "miner,miner4101"

taocd1 = "5H1H6VKDRW1sGYPToyJ18idf7JEr2o6amoXswM1EEYNM3Zur"
taocd2 = "5D5dF5sLt7ZAYvwVYZR2CpEmZvfXdMmKZsgmfb2CKkbBUKkd"

tao5 = "5CsvRJXuR955WojnGMdok1hbhffZyB4N5ocrv82f3p5A2zVp"
rizzo = "5F2CsUDVbRbVMXTh9fAzF9GacjVX7UapvRxidrxe7z8BYckQ"
yuma = "5HEo565WAy4Dbq3Sv271SAi7syBSofyfhhwRNjFNSM2gP9M2"
g1nj = "5G1NjW9YhXLadMWajvTkfcJy6up3yH2q1YzMXDTi6ijanChe"
northTensor = "5Fq5v71D4LX8Db1xsmRSy6udQThcZ8sFDqxQFwnUZ1BuqY5A"
TAO_Miner = "5DQ2Geab6G25wiZ4jGH6wJM8fekrm1QhV9hrRuntjBVxxKZm"

stake_hotkey = dict(miner41=tao5, miner=tao5)


def send_wechat_message(content):
    # url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=7ce8365c-4af4-bc58-098c7795bf63"
    headers = {"Content-Type": "application/json"}
    data = {
        "msgtype": "text",
        "text": {
            "content": content
        }
    }
    requests.post(url, headers=headers, data=json.dumps(data))

if __name__ == "__main__":
    sub = bt.subtensor(network=network)
    wallet_name_list = wallet_names.split(",")
    while True:
        for wallet_name in wallet_name_list:
            print(f"{wallet_name}, start wallet stake move")

            wallet = bt.wallet(name=wallet_name, path=wallet_path)
            wallet.coldkey_file.save_password_to_env(os.getenv(wallet_name.upper()))
            wallet.unlock_coldkey()

            stakeInfos = sub.get_stake_for_coldkey(wallet.coldkeypub.ss58_address)

            wallet_total_amount = 0
            netuid = 0
            target_hotkey = stake_hotkey.get(wallet_name.split('_')[0])

            for stake in stakeInfos:
                if stake.netuid == 0:
                    continue
                if stake.stake.tao < 0.1:
                    continue
                if stake.hotkey_ss58 == target_hotkey:
                    continue
                print(f"{wallet_name}, hotkey: {stake.hotkey_ss58}, stake: {stake.stake.tao}")
                result = sub.move_stake(wallet=wallet,
                                        origin_hotkey=stake.hotkey_ss58, origin_netuid=stake.netuid,
                                        destination_hotkey=target_hotkey, destination_netuid=0,
                                        amount=stake.stake)
                print(f"{wallet_name}, stake move result: {result}, stake amount: {stake.stake.tao}")
                if result:
                    wallet_total_amount = wallet_total_amount + stake.stake.tao

                netuid = stake.netuid

            if wallet_total_amount > 0:
                total_stake = sub.get_stake(coldkey_ss58=wallet.coldkeypub.ss58_address,
                                        hotkey_ss58=target_hotkey,
                                        netuid=netuid)

                subnet = sub.subnet(netuid)
                sqlObject.insert_stake_log(wallet_name, wallet_total_amount, target_hotkey, total_stake.tao)
                message = f"[质押成功] 钱包:{wallet_name}, 数量:{wallet_total_amount:.2f}, 总质押:{total_stake.tao:.2f}, 预估TAO:{subnet.price.tao * total_stake.tao:.2f}"
                # send_wechat_message(message)

        print("10000秒后 等待下一轮")
        time.sleep(10000)
