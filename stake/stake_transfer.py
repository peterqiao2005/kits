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
wallet_names = "taocd4_03,taocd4_04,taocd4_05,taocd19_6,taocd19_7,taocd19_8,taocd19_9,taocd19_10,taocd19_11,taocd19_12,taocd19_13,taocd19_14,taocd19_15"
target_wallet_name = "taocd4_01"
target_hotkey = "5H1H6VKDRW1sGYPToyJ18idf7JEr2o6amoXswM1EEYNM3Zur"
stake_netuid = dict(taocd4=4, taocd19=19)


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


def get_stake_sum(wallet, netuid):
    stake = sub.get_stake(coldkey_ss58=wallet.coldkeypub.ss58_address,
                          hotkey_ss58=target_hotkey,
                          netuid=netuid)
    return stake.tao


def stake(wallet, netuid):
    # 查询余额
    balance_before = sub.get_balance(wallet.coldkeypub.ss58_address)
    print(f"[开始质押] 钱包:{target_wallet_name}, 余额:{balance_before.tao}")
    # 开始质押
    stake_before = get_stake_sum(wallet, netuid)
    ### 执行质押
    result = sub.add_stake(wallet=wallet, hotkey_ss58=target_hotkey, netuid=netuid, amount=balance_before)
    # 质押之后
    stake_after = get_stake_sum(wallet, netuid)
    # 实际质押数量
    stake_sum = stake_after - stake_before
    if stake_sum > 0:
        sqlObject.insert_stake_log(wallet_name, stake_sum, target_hotkey, stake_after)
        subnet = sub.subnet(netuid)
        message = f"[质押成功] 子网:{netuid}, 质押数量:{stake_sum:.2f}, 总质押:{stake_after:.2f}, 预估TAO:{subnet.price.tao * stake_after:.2f}"
        print(message)
        send_wechat_message(message)


def unstake(wallet):
    stakeInfos = sub.get_stake_for_coldkey(wallet.coldkeypub.ss58_address)
    for stake in stakeInfos:
        if stake.stake.tao < 10:
            continue
        stake_amount = stake.stake
        result = sub.unstake(wallet=wallet, netuid=stake.netuid, hotkey_ss58=stake.hotkey_ss58, amount=stake.stake)
        if result:
            print(f"[取消质押] 钱包:{wallet_name}, 解压:{stake_amount.tao:.2f}")


def tarsfer(wallet1, wallet2, transfer_amount):
    transfer_result = sub.transfer(wallet=wallet1, dest=wallet2.coldkeypub.ss58_address,
                                   amount=bt.Balance.from_tao(transfer_amount))
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
    target_wallet = get_unlock_wallet(target_wallet_name)

    while True:
        wallet_name_list = wallet_names.split(",")
        for wallet_name in wallet_name_list:
            original_wallet = get_unlock_wallet(wallet_name)

            balance1 = sub.get_balance(original_wallet.coldkeypub.ss58_address)
            print(f"[解压开始] 钱包:{wallet_name}, 余额:{balance1.tao:.6f}")
            # 解质押
            unstake(original_wallet)
            # 转账
            balance2 = sub.get_balance(original_wallet.coldkeypub.ss58_address)
            if balance2.tao - balance1.tao < 0.1:
                continue
            print(f"[转账开始] 钱包:{wallet_name}, 余额:{balance2.tao:.6f}")
            tarsfer(original_wallet, target_wallet, balance2.tao - balance1.tao)
            # 质押
            netuid = stake_netuid.get(wallet_name.split('_')[0])
            stake(target_wallet, netuid)

        print(f"[停止等待] 暂停:10000 秒")
        time.sleep(10000)
