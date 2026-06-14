"""Wallet helpers — balance checking and x402 payment session creation."""

import logging
import os

from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from x402 import x402ClientSync
from x402.http.clients.requests import x402_requests
from x402.mechanisms.evm.exact import ExactEvmScheme

load_dotenv()

log = logging.getLogger(__name__)

USDC_ABI = [
    {
        "inputs": [{"name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
]

USDC_MAINNET = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDC_SEPOLIA = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def _network_config() -> tuple[str, str, str]:
    """Return (network_name, rpc_url, usdc_address, chain_pattern)."""
    network = os.getenv("NETWORK", "base-mainnet")
    if network == "base-mainnet":
        return "base-mainnet", "https://mainnet.base.org", USDC_MAINNET, "eip155:8453"
    return "base-sepolia", "https://sepolia.base.org", USDC_SEPOLIA, "eip155:84532"


def get_balance() -> float:
    """Return current USDC balance of WALLET_ADDRESS as a float."""
    try:
        _, rpc_url, usdc_address, _ = _network_config()
        address = os.getenv("WALLET_ADDRESS", "")
        if not address:
            log.warning("WALLET_ADDRESS not set in .env")
            return 0.0
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(usdc_address), abi=USDC_ABI
        )
        raw = contract.functions.balanceOf(Web3.to_checksum_address(address)).call()
        return raw / 1_000_000
    except Exception as e:
        log.warning("Balance check failed: %s", e)
        return 0.0


def get_x402_client():
    """Return a requests.Session that auto-handles 402 payment responses."""
    _, _, _, chain_pattern = _network_config()
    private_key = os.getenv("WALLET_PRIVATE_KEY", "")
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    account = Account.from_key(private_key)
    scheme = ExactEvmScheme(signer=account)
    client = x402ClientSync()
    client.register(chain_pattern, scheme)
    return x402_requests(client)
