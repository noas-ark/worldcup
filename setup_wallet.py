"""One-time wallet setup. Run manually once before first match.

Generates a fresh Ethereum keypair and prints the values to add to .env.
For base-sepolia testing, prints faucet URLs to get test USDC.
"""

import os
import sys

from dotenv import load_dotenv
from eth_account import Account

load_dotenv()


def main():
    network = os.getenv("NETWORK", "base-mainnet")
    print(f"Generating new Ethereum wallet for {network}...\n")

    account = Account.create()
    address = account.address
    private_key = account.key.hex()
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    print("=" * 60)
    print("Add these to your .env file:")
    print("=" * 60)
    print(f"WALLET_ADDRESS={address}")
    print(f"WALLET_PRIVATE_KEY={private_key}")
    print("=" * 60)
    print()

    if network == "base-sepolia":
        print("TESTNET SETUP — fund your wallet with test USDC:")
        print(f"  Address: {address}")
        print()
        print("  1. Get test ETH (for gas) from:")
        print("     https://www.coinbase.com/faucets/base-ethereum-goerli-faucet")
        print()
        print("  2. Get test USDC from:")
        print("     https://faucet.circle.com/  (select Base Sepolia)")
        print()
        print("  USDC contract on Base Sepolia:")
        print("  0x036CbD53842c5426634e7929541eC2318f3dCF7e")
    else:
        print("MAINNET SETUP — fund your wallet with real USDC on Base:")
        print(f"  Address: {address}")
        print()
        print("  Transfer USDC to this address on Base mainnet.")
        print("  Minimum recommended balance: $2.00 USDC")
        print()
        print("  USDC contract on Base mainnet:")
        print("  0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

    print()
    print("WARNING: Store your private key securely. Never commit .env to git.")


if __name__ == "__main__":
    main()
