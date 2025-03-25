import bittensor as bt

network = "local"
wallet_path = "~/.bittensor/wallets"
wallet_names = "taocd4_01"

if __name__ == "__main__":
    sub = bt.subtensor(network=network)
    wallet_name_list = wallet_names.split(",")
    total = 0
    for wallet_name in wallet_name_list:
        wallet = bt.wallet(name=wallet_name, path=wallet_path)
        stakeInfos = sub.get_stake_for_coldkey(wallet.coldkeypub.ss58_address)
        for stake in stakeInfos:
            amount = stake.stake.tao
            print(f"子网: {stake.netuid}, 质押金额: {amount}")