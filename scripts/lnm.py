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
amount = 1000
label = str(round(time.time()))
# refund_invoice = RPC.invoice(amount, label)
refund_invoice = 'lnbc10u1pjtz58msp5z03z8x4d2pu0wuycq2sjd93d63ws9k72y2zdg3lkx7mv3pw04y5spp562ejss56548fynxpgz4wkhq8xh4hcw4sq7s9je8srxk8xahe8pvsdzuwfjkkazzda6r5grsd3shjgrhd96xsgp3xqcrqgrnv968xgrpdejzq7t0w5s8w6tvdssxyefqd35kketv0ys8yettwsssxqzjccqpjrzjqvww9ygka2m7m4npfr63d8clkev0443tm3gfzgs6hz2luhfkmvqtyrpdmsqqw8gqqqqqqqlgqqqqq2qq2q9qyysgqgsgu7s903pr3xu7hzajz3kccqv8vrafttnrlkedakwe38sen0sspl2aj2h5yvugzxetfpfewqevkve76t38dkz0sw4hkgse09etxe6qq83vm78'
print(refund_invoice)

print(client.withdraw(refund_invoice, amount))



# invoice, hash = client.deposit_invoice(200)
# print((invoice, hash,))
#
# # RPC.pay_invoice(invoice)
#
# while not client.get_deposit_status(hash):
#     time.sleep(1.0)
#
# print('deposit done!')

# print(client.get_deposit_status(hash))
# print(json.dumps(ret, indent=2))
