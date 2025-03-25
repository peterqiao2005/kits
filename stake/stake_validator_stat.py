import time

import bittensor as bt
from postgre_util import PgsqlStorage

sqlObject = PgsqlStorage()

network = "local"


def stake_handler(netuid, hotkey, coldkey):
    total_stake = sub.get_stake(netuid=netuid, hotkey_ss58=hotkey, coldkey_ss58=coldkey)
    print(f"{netuid}号stake:{total_stake.tao}")
    sqlObject.insert_validator_stake(hotkey, netuid, total_stake.tao)


if __name__ == '__main__':
    sub = bt.subtensor(network=network)

    while True:
        # 4号Validator
        netuid = 4
        hotkey = "5H1H6VKDRW1sGYPToyJ18idf7JEr2o6amoXswM1EEYNM3Zur"
        coldkey = "5Dhta1sjChfN5FNAFQbg2CAQLw2d1YSgK7YQnywAfxcNRe5a"
        stake_handler(netuid, hotkey, coldkey)

        # 19号Validator
        netuid = 19
        hotkey = "5D5dF5sLt7ZAYvwVYZR2CpEmZvfXdMmKZsgmfb2CKkbBUKkd"
        coldkey = "5HR3nL6eBQevq1mEeEiEdNmA4ePzkp8FJUQW7wYPeRGd6EvV"
        stake_handler(netuid, hotkey, coldkey)

        print("等待一小时!")
        time.sleep(60 * 60)
