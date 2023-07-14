import json
import math
import logging
import time

from LNM import LNMarkets
from lnmarkets import rest
import config
from RPC import RPC
log = logging.getLogger()
log.setLevel(logging.DEBUG)


options = {'key': config.lnmarkets['key'],
           'secret': config.lnmarkets['secret'],
           'passphrase': config.lnmarkets['passphrase'],
           'network': 'mainnet'}

lnm = rest.LNMarketsRest(**options)
client = LNMarkets(config.lnmarkets['key'], config.lnmarkets['secret'], config.lnmarkets['passphrase'])


# ret = client.get_price()
# print(json.dumps(ret, indent=2))

# ret = client.open_market_position('long', 200)
# print(json.dumps(ret, indent=2))

# amount = 20000
# print('1')
# invoice = client.deposit_invoice(amount)
#
# print('2')
# RPC.pay_invoice(invoice)


# amount = client.get_max_withdraw_amount()
#
# label = str(round(time.time()))
# refund_invoice = RPC.invoice(amount, label)
# print(refund_invoice)
#
# print(client.withdraw(refund_invoice, amount))



invoice, hash = client.deposit_invoice(200)
print((invoice, hash,))

# RPC.pay_invoice(invoice)

while not client.get_deposit_status(hash):
    time.sleep(1.0)

print('deposit done!')

# print(client.get_deposit_status(hash))
# print(json.dumps(ret, indent=2))
