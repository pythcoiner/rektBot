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
#
# ret = client.open_market_position('long', 200)
# print(json.dumps(ret, indent=2))
amount = 1234

print('1')
invoice = client.deposit_invoice(amount)

print('2')
RPC.pay_invoice(invoice)

print('3')
label = str(round(time.time()))
refund_invoice = RPC.invoice(amount, label)

print('4')
client.withdraw(refund_invoice, amount)


